from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix

from ..BackgroundTasks import taskMeshes, taskScheduler
from . import booleanCollections, booleanNodes, booleanRequest


PROP_TARGET = "helpersBooleanTarget"
PROP_SETTINGS = "helpersBooleanSettings"
PROP_SIGNATURE = "helpersBooleanSignature"

WORKER_PATH = Path(__file__).with_name("booleanWorker.py")
MAXIMUM_NOTE_LINES = 6

REPAIR_LABELS = (
    ("merged", "doubled vertices merged"),
    ("loose", "loose vertices removed"),
    ("open", "open edges filled"),
    ("flipped", "faces flipped"),
)


@dataclass(slots=True)
class BooleanJobContext:
    resultMatrix: Matrix
    isForced: bool


class BooleanState:
    def __init__(self):
        self.noteLines = {}
        self.isIgnoringUpdates = False


_state = BooleanState()


def addBooleanHandlers():
    removeBooleanHandlers()
    bpy.app.handlers.load_post.append(handleFileLoad)
    bpy.app.timers.register(_syncAfterRegister, first_interval=0.0, persistent=True)


def removeBooleanHandlers():
    removeBooleanUpdateHandler()
    _removeHandlersByName(bpy.app.handlers.load_post, "handleFileLoad")


def addBooleanUpdateHandler():
    if handleDepsgraphUpdate not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(handleDepsgraphUpdate)


def removeBooleanUpdateHandler():
    _removeHandlersByName(bpy.app.handlers.depsgraph_update_post, "handleDepsgraphUpdate")
    _clearUpdateState()


def syncBooleanHandlers():
    generatorObjects = [blendObject for blendObject in bpy.data.objects if isGeneratorObject(blendObject)]

    if not generatorObjects:
        return

    addBooleanUpdateHandler()

    for generatorObject in generatorObjects:
        _scheduler.schedule(generatorObject.name, isImmediate=True)


def _syncAfterRegister():
    syncBooleanHandlers()
    return None


@persistent
def handleFileLoad(_filePath):
    _clearUpdateState()
    syncBooleanHandlers()


@persistent
def handleDepsgraphUpdate(scene, depsgraph):
    if _state.isIgnoringUpdates:
        return

    generatorObjects = [blendObject for blendObject in scene.objects if isGeneratorObject(blendObject)]

    if not generatorObjects:
        if not any(isGeneratorObject(blendObject) for blendObject in bpy.data.objects):
            removeBooleanUpdateHandler()

        return

    changedIds = _collectChangedIds(depsgraph)

    for generatorObject in generatorObjects:
        modifierValues = booleanNodes.readModifierValues(generatorObject)

        if not modifierValues[booleanNodes.SOCKET_INTERACTIVE]:
            _setProperty(generatorObject, PROP_SETTINGS, "")
            continue

        areSettingsChanged = (
            generatorObject in changedIds
            and generatorObject.get(PROP_SETTINGS) != booleanRequest.getSettingsSignature(modifierValues)
        )

        if areSettingsChanged or _areSourcesChanged(generatorObject, modifierValues, changedIds):
            _scheduler.schedule(generatorObject.name)


def createGeneratorObject(context, targetObject, cutterCollection):
    if booleanCollections.isSceneCollection(cutterCollection):
        raise ValueError("Scene Collection cannot be used as cutters source")

    generatorName = f"{targetObject.name} Boolean Generator"
    generatorObject = bpy.data.objects.new(generatorName, bpy.data.meshes.new(generatorName))
    generatorObject.display_type = "TEXTURED"
    generatorObject[PROP_TARGET] = targetObject.name
    _linkObject(generatorObject, context.scene.collection)

    booleanNodes.createModifier(
        context,
        generatorObject,
        "Boolean Generator",
        {booleanNodes.SOCKET_TARGET: targetObject, booleanNodes.SOCKET_CUTTERS: cutterCollection},
    )

    addBooleanUpdateHandler()
    _scheduler.schedule(generatorObject.name, isImmediate=True)

    context.view_layer.objects.active = generatorObject
    generatorObject.select_set(True)

    return generatorObject


def isGeneratorObject(blendObject):
    return blendObject is not None and PROP_TARGET in blendObject


def refreshGeneratorObject(generatorObject):
    _scheduler.runNow(generatorObject.name)


def getStatus(generatorObject):
    return _scheduler.getStatus(generatorObject.name)


def getErrorLines(generatorObject):
    return _scheduler.getErrorLines(generatorObject.name)


def getNotes(generatorObject):
    return _state.noteLines.get(generatorObject.name, [])


def _clearUpdateState():
    _scheduler.clear()
    _state.noteLines.clear()


@contextmanager
def _ignoringOwnUpdates():
    _state.isIgnoringUpdates = True

    try:
        yield
    finally:
        bpy.context.evaluated_depsgraph_get()
        _state.isIgnoringUpdates = False


def _canProcess(objectName):
    generatorObject = bpy.data.objects.get(objectName)
    return generatorObject is None or generatorObject.mode != "EDIT"


@_ignoringOwnUpdates()
def _prepareTask(objectName, isForced):
    generatorObject = bpy.data.objects.get(objectName)

    if not isGeneratorObject(generatorObject):
        return None

    modifierValues = booleanNodes.readModifierValues(generatorObject)

    if not (isForced or modifierValues[booleanNodes.SOCKET_INTERACTIVE]):
        return None

    _setProperty(generatorObject, PROP_SETTINGS, booleanRequest.getSettingsSignature(modifierValues))
    targetObject = modifierValues[booleanNodes.SOCKET_TARGET]
    cutterCollection = modifierValues[booleanNodes.SOCKET_CUTTERS]

    if targetObject is None or cutterCollection is None or targetObject.type != "MESH":
        _clearGeneratorMesh(generatorObject)
        return None

    _setProperty(generatorObject, PROP_TARGET, targetObject.name)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    cutterObjects = booleanRequest.getCutterObjects(cutterCollection, (generatorObject, targetObject))
    requestData = booleanRequest.buildRequest(targetObject, cutterObjects, modifierValues, depsgraph)
    resultMatrix = generatorObject.matrix_world.inverted() @ targetObject.matrix_world
    signature = booleanRequest.getRequestSignature(requestData, resultMatrix)

    if generatorObject.get(PROP_SIGNATURE) == signature:
        return None

    _state.noteLines.pop(objectName, None)

    return taskScheduler.TaskRequest(signature, requestData, BooleanJobContext(resultMatrix, isForced))


@_ignoringOwnUpdates()
def _applyResult(objectName, job, responseHeader, payload):
    generatorObject = bpy.data.objects.get(objectName)

    if not isGeneratorObject(generatorObject):
        return

    modifierValues = booleanNodes.readModifierValues(generatorObject)

    if not (job.context.isForced or modifierValues[booleanNodes.SOCKET_INTERACTIVE]):
        _setProperty(generatorObject, PROP_SETTINGS, "")
        return

    resultMesh = generatorObject.data
    resultMesh.materials.clear()
    taskMeshes.fillMesh(resultMesh, responseHeader["mesh"], payload)
    resultMesh.transform(job.context.resultMatrix)
    targetObject = modifierValues[booleanNodes.SOCKET_TARGET]

    if targetObject is not None:
        for material in targetObject.data.materials:
            resultMesh.materials.append(material)

    _setProperty(generatorObject, PROP_SIGNATURE, job.signature)
    _state.noteLines[objectName] = _getReportNotes(responseHeader["report"])


def _clearGeneratorMesh(generatorObject):
    generatorObject.data.clear_geometry()
    generatorObject.data.update()
    _setProperty(generatorObject, PROP_SIGNATURE, "")


def _getReportNotes(report):
    noteLines = []

    for displayName, repairStats in report["repaired"].items():
        details = ", ".join(f"{repairStats[key]} {label}" for key, label in REPAIR_LABELS if repairStats.get(key))
        noteLines.append(f"Repaired {displayName}: {details}")

    if report["resultOpenEdges"]:
        noteLines.append(f"Result has {report['resultOpenEdges']} open edges")

    return noteLines[:MAXIMUM_NOTE_LINES]


def _collectChangedIds(depsgraph):
    changedIds = {}

    for update in depsgraph.updates:
        originalId = update.id.original
        isChanged = update.is_updated_geometry or update.is_updated_transform
        changedIds[originalId] = changedIds.get(originalId, False) or isChanged

    return changedIds


def _areSourcesChanged(generatorObject, modifierValues, changedIds):
    targetObject = modifierValues[booleanNodes.SOCKET_TARGET]
    cutterCollection = modifierValues[booleanNodes.SOCKET_CUTTERS]

    if targetObject is None or cutterCollection is None:
        return False

    if cutterCollection in changedIds:
        return True

    cutterObjects = booleanRequest.getCutterObjects(cutterCollection, (generatorObject, targetObject))

    return any(
        changedIds.get(sourceObject) or changedIds.get(sourceObject.data)
        for sourceObject in (targetObject, *cutterObjects)
    )


def _removeHandlersByName(handlers, handlerName):
    for handler in tuple(handlers):
        isBooleanHandler = (
            getattr(handler, "__name__", "") == handlerName
            and (getattr(handler, "__module__", None) or "").endswith(".booleanRuntime")
        )

        if isBooleanHandler:
            handlers.remove(handler)


def _setProperty(blendObject, propertyName, value):
    if blendObject.get(propertyName) != value:
        blendObject[propertyName] = value


def _linkObject(blendObject, collection):
    collection.objects.link(blendObject)
    spaceData = bpy.context.space_data

    if spaceData is not None and spaceData.type == "VIEW_3D" and spaceData.local_view is not None:
        blendObject.local_view_set(spaceData, True)


_scheduler = taskScheduler.TaskScheduler(
    WORKER_PATH,
    prepareTask=_prepareTask,
    applyResult=_applyResult,
    canProcess=_canProcess,
)

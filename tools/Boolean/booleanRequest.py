import hashlib

from mathutils import Matrix

from ..BackgroundTasks import taskMeshes, taskTransfer
from . import booleanNodes


MATRIX_BAKE_TOLERANCE = 1e-5
SIGNATURE_MATRIX_PRECISION = 6
SIGNATURE_DISTANCE_PRECISION = 9


def getCutterObjects(cutterCollection, excludedObjects):
    cutterObjects = [
        blendObject
        for blendObject in cutterCollection.all_objects
        if blendObject.type == "MESH" and blendObject not in excludedObjects and len(blendObject.data.polygons) > 0
    ]
    cutterObjects.sort(key=lambda blendObject: blendObject.name)

    return cutterObjects


def getWorkerSettings(modifierValues):
    return {
        "operation": booleanNodes.getChoice(booleanNodes.OPERATIONS, modifierValues[booleanNodes.SOCKET_OPERATION]),
        "solver": booleanNodes.getChoice(booleanNodes.SOLVERS, modifierValues[booleanNodes.SOCKET_SOLVER]),
        "selfIntersection": bool(modifierValues[booleanNodes.SOCKET_SELF_INTERSECTION]),
        "holeTolerant": bool(modifierValues[booleanNodes.SOCKET_HOLE_TOLERANT]),
        "repair": bool(modifierValues[booleanNodes.SOCKET_REPAIR]),
        "repairDistance": float(modifierValues[booleanNodes.SOCKET_REPAIR_DISTANCE]),
    }


def getSettingsSignature(modifierValues):
    targetObject = modifierValues[booleanNodes.SOCKET_TARGET]
    cutterCollection = modifierValues[booleanNodes.SOCKET_CUTTERS]
    workerSettings = getWorkerSettings(modifierValues)
    workerSettings["repairDistance"] = round(workerSettings["repairDistance"], SIGNATURE_DISTANCE_PRECISION)

    return repr(
        (
            targetObject.name if targetObject else "",
            cutterCollection.name if cutterCollection else "",
            tuple(sorted(workerSettings.items())),
        )
    )


def getRequestSignature(requestData, resultMatrix):
    roundedMatrix = tuple(round(value, SIGNATURE_MATRIX_PRECISION) for row in resultMatrix for value in row)
    signatureHash = hashlib.sha1(requestData)
    signatureHash.update(repr(roundedMatrix).encode())

    return signatureHash.hexdigest()


def buildRequest(targetObject, cutterObjects, modifierValues, depsgraph):
    payloadWriter = taskTransfer.PayloadWriter()
    namedObjects = (("Target", targetObject), *((f"Cutter {index}", cutter) for index, cutter in enumerate(cutterObjects)))
    sources = [
        _packSource(sourceName, sourceObject, depsgraph, payloadWriter) for sourceName, sourceObject in namedObjects
    ]
    header = {"settings": getWorkerSettings(modifierValues), "sources": sources}

    return taskTransfer.encodeFrame(header, payloadWriter)


def _packSource(sourceName, sourceObject, depsgraph, payloadWriter):
    evaluatedObject = sourceObject.evaluated_get(depsgraph)
    worldMatrix = sourceObject.matrix_world

    try:
        return {
            "name": sourceName,
            "displayName": sourceObject.name,
            "matrix": [list(row) for row in worldMatrix],
            "isMatrixBaked": _hasShear(worldMatrix),
            "mesh": taskMeshes.packMesh(evaluatedObject.to_mesh(), payloadWriter),
        }
    finally:
        evaluatedObject.to_mesh_clear()


def _hasShear(worldMatrix):
    rebuiltMatrix = Matrix.LocRotScale(*worldMatrix.decompose())
    deviation = max(
        abs(rebuiltValue - originalValue)
        for rebuiltRow, originalRow in zip(rebuiltMatrix, worldMatrix)
        for rebuiltValue, originalValue in zip(rebuiltRow, originalRow)
    )

    return deviation > MATRIX_BAKE_TOLERANCE

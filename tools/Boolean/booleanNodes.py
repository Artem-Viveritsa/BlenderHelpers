import hashlib

import bpy
from bpy.types import ID, GeometryNodeTree, NodesModifier


NODE_GROUP_NAME = "Helpers Boolean Generator"
SCHEMA_KEY = "helpersBooleanSchema"
SCHEMA_FINGERPRINT_VERSION = 1

SOCKET_TARGET = "Target"
SOCKET_CUTTERS = "Cutters"
SOCKET_INTERACTIVE = "Interactive"
SOCKET_OPERATION = "Operation"
SOCKET_SOLVER = "Solver"
SOCKET_SELF_INTERSECTION = "Self Intersection"
SOCKET_HOLE_TOLERANT = "Hole Tolerant"
SOCKET_REPAIR = "Repair"
SOCKET_REPAIR_DISTANCE = "Repair Distance"

DEFAULT_OPERATION = 0
DEFAULT_SOLVER = 0
DEFAULT_SELF_INTERSECTION = False
DEFAULT_HOLE_TOLERANT = False
DEFAULT_REPAIR = True
DEFAULT_REPAIR_DISTANCE = 0.0001

OPERATIONS = (
    ("DIFFERENCE", "Difference", "Subtract the cutters from the target"),
    ("UNION", "Union", "Add the cutters to the target"),
    ("INTERSECT", "Intersect", "Keep only the part of the target that is inside the cutters"),
)
SOLVERS = (
    ("EXACT", "Exact", "Most accurate, works with overlapping and self-intersecting cutters"),
    ("MANIFOLD", "Manifold", "Fast, requires closed meshes without self-intersections"),
    ("FLOAT", "Float", "Fastest, least accurate"),
)

SOCKETS = (
    (SOCKET_TARGET, "NodeSocketObject", None, None, None, "Mesh object to cut, it stays unchanged"),
    (SOCKET_CUTTERS, "NodeSocketCollection", None, None, None, "Collection of objects to subtract from the target"),
    (
        SOCKET_INTERACTIVE,
        "NodeSocketBool",
        True,
        None,
        None,
        (
            "Update the geometry automatically when the sources change, "
            "turn off to pause updates while editing heavy objects and update with Refresh"
        ),
    ),
    (
        SOCKET_OPERATION,
        "NodeSocketInt",
        DEFAULT_OPERATION,
        0,
        len(OPERATIONS) - 1,
        "Boolean operation applied to the target and the cutters",
    ),
    (
        SOCKET_SOLVER,
        "NodeSocketInt",
        DEFAULT_SOLVER,
        0,
        len(SOLVERS) - 1,
        "Boolean solver, Exact is the only one that handles overlapping cutters",
    ),
    (
        SOCKET_SELF_INTERSECTION,
        "NodeSocketBool",
        DEFAULT_SELF_INTERSECTION,
        None,
        None,
        "Allow every cutter object to intersect itself, needed for cutters made of overlapping parts, slower",
    ),
    (
        SOCKET_HOLE_TOLERANT,
        "NodeSocketBool",
        DEFAULT_HOLE_TOLERANT,
        None,
        None,
        "Better results for meshes with holes or other defects, slower",
    ),
    (
        SOCKET_REPAIR,
        "NodeSocketBool",
        DEFAULT_REPAIR,
        None,
        None,
        (
            "Fix the target and the cutters before the operation: merge doubled vertices, "
            "remove loose geometry, fill holes and make normals consistent. The originals stay unchanged"
        ),
    ),
    (
        SOCKET_REPAIR_DISTANCE,
        "NodeSocketFloat",
        DEFAULT_REPAIR_DISTANCE,
        0.0,
        1000.0,
        "Vertices closer than this distance are merged during the repair",
    ),
)


def getChoice(items, index):
    return items[min(max(int(index), 0), len(items) - 1)][0]


def getDefaultValues():
    return {socket[0]: socket[2] for socket in SOCKETS}


def _getNodeGroupFingerprint():
    fingerprintData = repr((SCHEMA_FINGERPRINT_VERSION, SOCKETS)).encode()
    return hashlib.sha1(fingerprintData).hexdigest()


def _isNodeGroupCurrent(nodeGroup):
    return nodeGroup.get(SCHEMA_KEY) == _getNodeGroupFingerprint()


def getSocketIdentifiers(nodeGroup):
    if nodeGroup is None:
        return {}

    return {
        interfaceItem.name: interfaceItem.identifier
        for interfaceItem in nodeGroup.interface.items_tree
        if getattr(interfaceItem, "item_type", None) == "SOCKET" and interfaceItem.in_out == "INPUT"
    }


def getSocketValue(generatorModifier, socketIdentifiers, socketName, fallbackValue):
    socketIdentifier = socketIdentifiers.get(socketName)

    if socketIdentifier:
        return generatorModifier.get(socketIdentifier, fallbackValue)

    return fallbackValue


def findGeneratorModifier(generatorObject):
    for objectModifier in generatorObject.modifiers:
        isGeneratorModifier = (
            objectModifier.type == "NODES"
            and objectModifier.node_group
            and objectModifier.node_group.name.startswith(NODE_GROUP_NAME)
        )

        if isGeneratorModifier:
            return objectModifier

    return None


def readModifierValues(generatorObject):
    modifierValues = getDefaultValues()
    generatorModifier = findGeneratorModifier(generatorObject)

    if generatorModifier is None:
        return modifierValues

    if not _isNodeGroupCurrent(generatorModifier.node_group):
        generatorModifier.node_group = ensureNodeGroup()

    socketIdentifiers = getSocketIdentifiers(generatorModifier.node_group)

    for socketName, defaultValue in tuple(modifierValues.items()):
        socketIdentifier = socketIdentifiers.get(socketName)

        if socketIdentifier:
            modifierValues[socketName] = _coerceSocketValue(
                generatorModifier.get(socketIdentifier, defaultValue), defaultValue
            )

    return modifierValues


def ensureNodeGroup():
    nodeGroup = bpy.data.node_groups.get(NODE_GROUP_NAME)

    if nodeGroup is not None and _isNodeGroupCurrent(nodeGroup):
        nodeGroup.is_modifier = True
        return nodeGroup

    if nodeGroup is None:
        nodeGroup = bpy.data.node_groups.new(NODE_GROUP_NAME, "GeometryNodeTree")
        return _buildNodeGroup(nodeGroup)

    savedModifierValues = _collectModifierValues(nodeGroup)
    _buildNodeGroup(nodeGroup)
    defaultValues = getDefaultValues()

    for savedModifier, savedValues in savedModifierValues:
        _applyModifierValues(savedModifier, defaultValues | savedValues)

    return nodeGroup


def _buildNodeGroup(nodeGroup):
    nodeGroup.nodes.clear()

    for interfaceItem in tuple(nodeGroup.interface.items_tree):
        nodeGroup.interface.remove(interfaceItem)

    nodeGroup.is_modifier = True
    nodeGroup[SCHEMA_KEY] = _getNodeGroupFingerprint()

    _newSocket(nodeGroup, "Geometry", "OUTPUT", "NodeSocketGeometry")
    _newSocket(nodeGroup, "Geometry", "INPUT", "NodeSocketGeometry")

    for socketName, socketType, defaultValue, minimumValue, maximumValue, description in SOCKETS:
        _newSocket(nodeGroup, socketName, "INPUT", socketType, defaultValue, minimumValue, maximumValue, description)

    groupInputNode = nodeGroup.nodes.new("NodeGroupInput")
    groupInputNode.location = (-220, 0)

    groupOutputNode = nodeGroup.nodes.new("NodeGroupOutput")
    groupOutputNode.location = (120, 0)

    nodeGroup.links.new(groupInputNode.outputs["Geometry"], groupOutputNode.inputs["Geometry"])
    return nodeGroup


def createModifier(context, generatorObject, modifierName, modifierValues):
    previousActiveObject = context.view_layer.objects.active
    previousSelection = [item for item in context.selected_objects if item is not generatorObject]

    for item in previousSelection:
        item.select_set(False)

    generatorObject.select_set(True)
    context.view_layer.objects.active = generatorObject

    try:
        bpy.ops.node.new_geometry_nodes_modifier()
        generatorModifier = generatorObject.modifiers[-1]
        generatorModifier.name = modifierName
        temporaryNodeGroup = generatorModifier.node_group
        generatorModifier.node_group = ensureNodeGroup()

        if temporaryNodeGroup is not None and temporaryNodeGroup.users == 0:
            bpy.data.node_groups.remove(temporaryNodeGroup)
    except Exception:
        hasNodesModifier = (
            generatorObject.modifiers
            and generatorObject.modifiers[-1].type == "NODES"
            and generatorObject.modifiers[-1].node_group is not None
        )

        if hasNodesModifier:
            generatorObject.modifiers.remove(generatorObject.modifiers[-1])
        raise
    finally:
        for item in previousSelection:
            item.select_set(True)

        if previousActiveObject is not None:
            try:
                context.view_layer.objects.active = previousActiveObject
            except TypeError:
                pass

    generatorModifier.show_group_selector = False
    _applyModifierValues(generatorModifier, getDefaultValues() | modifierValues)

    return generatorModifier


def _applyModifierValues(generatorModifier, modifierValues):
    socketIdentifiers = getSocketIdentifiers(generatorModifier.node_group)

    for socketName, value in modifierValues.items():
        socketIdentifier = socketIdentifiers.get(socketName)

        if socketIdentifier and value is not None:
            _setModifierValue(generatorModifier, socketIdentifier, value)

    generatorModifier.id_data.update_tag()
    generatorModifier.node_group.update_tag()


def _collectModifierValues(nodeGroup):
    socketIdentifiers = getSocketIdentifiers(nodeGroup)
    collectedValues = []

    for blendObject in bpy.data.objects:
        for objectModifier in blendObject.modifiers:
            if objectModifier.type == "NODES" and objectModifier.node_group is nodeGroup:
                modifierValues = {
                    socketName: objectModifier[socketIdentifier]
                    for socketName, socketIdentifier in socketIdentifiers.items()
                    if socketIdentifier in objectModifier
                }
                collectedValues.append((objectModifier, modifierValues))

    return collectedValues


def _setModifierValue(generatorModifier, socketIdentifier, value):
    try:
        generatorModifier[socketIdentifier] = value
    except TypeError:
        if socketIdentifier in generatorModifier:
            del generatorModifier[socketIdentifier]

        try:
            generatorModifier[socketIdentifier] = value
        except TypeError:
            if not isinstance(value, ID):
                raise


def _coerceSocketValue(value, fallbackValue):
    try:
        if isinstance(fallbackValue, bool):
            return bool(value)
        if isinstance(fallbackValue, int):
            return int(value)
        if isinstance(fallbackValue, float):
            return float(value)
    except (TypeError, ValueError):
        return fallbackValue

    return value


def _newSocket(nodeGroup, socketName, direction, socketType, defaultValue=None, minimumValue=None, maximumValue=None, description=""):
    socket = nodeGroup.interface.new_socket(
        name=socketName, in_out=direction, socket_type=socketType, description=description
    )

    if direction == "INPUT" and hasattr(socket, "hide_in_modifier"):
        socket.hide_in_modifier = True

    for attributeName, value in (
        ("default_value", defaultValue),
        ("min_value", minimumValue),
        ("max_value", maximumValue),
    ):
        if value is not None and hasattr(socket, attributeName):
            setattr(socket, attributeName, value)

    return socket

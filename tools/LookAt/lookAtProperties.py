import bpy
from bpy.props import BoolProperty, PointerProperty
from bpy.types import PropertyGroup


def updateLookAtEnabled(self, context):
    from . import lookAtRuntime

    lookAtRuntime.clearLookAtAnimation()


def pollLookAtTargetObject(self, targetObject):
    return targetObject.type == "MESH"


class HelpersLookAtSceneSettings(PropertyGroup):
    isLookAtEnabled: BoolProperty(
        name="Look At",
        description="Keep the camera perpendicular to the face under the snapped object",
        default=False,
        update=updateLookAtEnabled,
    )
    constrainOrbit: BoolProperty(
        name="Constraint Orbit",
        description="Keep the orbit aligned to the world Z axis while Look At is controlling the camera",
        default=False,
        update=updateLookAtEnabled,
    )
    targetObject: PointerProperty(
        name="Target Object",
        description="Limit Look At alignment to faces of this mesh object",
        type=bpy.types.Object,
        poll=pollLookAtTargetObject,
        update=updateLookAtEnabled,
    )
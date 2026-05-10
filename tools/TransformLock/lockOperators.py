from bpy.props import BoolProperty, EnumProperty
from bpy.types import Operator

from . import lockProperties


class ObjectHelpersSetTransformLockOperator(Operator):
    bl_label = "Set Transform Channel Lock"
    bl_description = "Lock or unlock the selected transform channel on all selected objects"
    bl_idname = "object.helpers_set_transform_lock"
    bl_options = {"REGISTER", "UNDO"}

    transformChannel: EnumProperty(
        name="Transform Channel",
        description="Choose which transform channel to lock or unlock",
        items=(
            ("LOCATION", "Location", "Lock or unlock all location axes"),
            ("ROTATION", "Rotation", "Lock or unlock all rotation axes"),
            ("SCALE", "Scale", "Lock or unlock all scale axes"),
        ),
        options={"SKIP_SAVE"},
    )
    shouldLock: BoolProperty(
        name="Enable Lock",
        description="Enable the selected lock instead of clearing it",
        options={"SKIP_SAVE"},
    )

    def execute(self, context):
        lockProperties.setSelectedObjectsTransformChannelLockState(
            context, self.transformChannel, self.shouldLock
        )

        return {"FINISHED"}

from bpy.types import Panel


class View3DHelpersTransformLockPanel(Panel):
    bl_label = "Transform Lock"
    bl_category = "Helpers"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_context = "objectmode"

    def draw_header(self, context):
        windowManagerSettings = context.window_manager.helpersTransformLockSettings
        self.layout.prop(windowManagerSettings, "showTransformLockOverlay", text="")

    def draw(self, context):
        sceneSettings = context.scene.helpersTransformLockSettings
        windowManagerSettings = context.window_manager.helpersTransformLockSettings
        lockActions = (
            ("Location", "LOCATION"),
            ("Rotation", "ROTATION"),
            ("Scale", "SCALE"),
        )

        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        row = layout.row()
        column = row.column(heading="Overlay")
        column.active = windowManagerSettings.showTransformLockOverlay
        column.prop(sceneSettings, "showLocationLocksInOverlay", text="Location (Horizontal)")
        column.prop(sceneSettings, "showRotationLocksInOverlay", text="Rotation (Diagonal)")
        column.prop(sceneSettings, "showScaleLocksInOverlay", text="Scale (Vertical)")

        layout.separator(factor=0.1)

        row = layout.row()
        row.prop(sceneSettings, "transformLockOverlayOpacity", text="Opacity")

        layout.separator(factor=0.1)

        row = layout.row()
        column = row.column(heading="Actions")

        for label, transformChannel in lockActions:
            row = column.row(align=True)

            lockOperator = row.operator(
                "object.helpers_set_transform_lock", text=label, icon="LOCKED"
            )
            lockOperator.transformChannel = transformChannel
            lockOperator.shouldLock = True

            unlockOperator = row.operator(
                "object.helpers_set_transform_lock", text=label, icon="UNLOCKED"
            )
            unlockOperator.transformChannel = transformChannel
            unlockOperator.shouldLock = False

        layout.separator(factor=0.1)

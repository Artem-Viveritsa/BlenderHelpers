from bpy.types import Panel


class View3DHelpersLookAtPanel(Panel):
    bl_label = "Look At"
    bl_category = "Helpers"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_context = "objectmode"

    def draw_header(self, context):
        sceneSettings = context.scene.helpersLookAtSettings
        self.layout.prop(sceneSettings, "isLookAtEnabled", text="")

    def draw(self, context):
        sceneSettings = context.scene.helpersLookAtSettings

        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        column = layout.column()
        column.active = sceneSettings.isLookAtEnabled

        if hasattr(sceneSettings, "constrainOrbit"):
            column.prop(sceneSettings, "constrainOrbit", text="Constraint Orbit")

        if hasattr(sceneSettings, "targetObject"):
            column.prop(sceneSettings, "targetObject", text="Target Object")
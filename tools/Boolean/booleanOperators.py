import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from . import booleanCollections, booleanRuntime


class ObjectHelpersAddBooleanGeneratorOperator(Operator):
    bl_label = "Boolean Generator"
    bl_description = (
        "Create an auto-updating copy of the target object with the objects of a collection subtracted from it, "
        "the target stays unchanged"
    )
    bl_idname = "object.helpers_add_boolean_generator"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    targetObjectName: StringProperty(
        name="Target",
        description="Mesh object to cut",
    )
    cutterCollectionName: StringProperty(
        name="Cutters",
        description="Collection of objects to subtract from the target",
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop_search(self, "targetObjectName", bpy.data, "objects")
        layout.prop_search(self, "cutterCollectionName", bpy.data, "collections")

    def execute(self, context):
        targetObject = bpy.data.objects.get(self.targetObjectName)
        cutterCollection = booleanCollections.getCollectionByName(self.cutterCollectionName)

        if targetObject is None or targetObject.type != "MESH":
            self.report({"ERROR"}, "Target mesh object must be specified")
            return {"CANCELLED"}

        if cutterCollection is None:
            self.report({"ERROR"}, "Cutters collection must be specified")
            return {"CANCELLED"}

        try:
            booleanRuntime.createGeneratorObject(context, targetObject, cutterCollection)
        except ValueError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

        self.report({"INFO"}, "Created boolean generator")
        return {"FINISHED"}

    def invoke(self, context, event):
        activeObject = context.object

        if activeObject is not None and activeObject.type == "MESH":
            self.targetObjectName = activeObject.name

        activeCollection = booleanCollections.getActiveCollection(context)

        if activeCollection is not None and (activeObject is None or activeObject.name not in activeCollection.objects):
            self.cutterCollectionName = activeCollection.name

        return context.window_manager.invoke_props_dialog(self)


class ObjectHelpersRefreshBooleanGeneratorOperator(Operator):
    bl_label = "Refresh"
    bl_description = "Update the generated geometry"
    bl_idname = "object.helpers_refresh_boolean_generator"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return booleanRuntime.isGeneratorObject(context.object)

    def execute(self, context):
        booleanRuntime.refreshGeneratorObject(context.object)
        return {"FINISHED"}

from bpy.types import Panel

from . import booleanNodes, booleanRuntime


class View3DHelpersBooleanPanel(Panel):
    bl_label = "Boolean"
    bl_category = "Helpers"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_context = "objectmode"

    def draw(self, context):
        self.layout.operator("object.helpers_add_boolean_generator", text="Boolean Generator", icon="MOD_BOOLEAN")


class PropertiesHelpersBooleanGeneratorPanel(Panel):
    bl_label = "Boolean Generator"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "modifier"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        activeObject = context.object
        return activeObject is not None and booleanNodes.findGeneratorModifier(activeObject) is not None

    def draw_header(self, context):
        generatorModifier = booleanNodes.findGeneratorModifier(context.object)
        socketIdentifiers = booleanNodes.getSocketIdentifiers(generatorModifier.node_group)
        socketIdentifier = socketIdentifiers.get(booleanNodes.SOCKET_INTERACTIVE)

        if socketIdentifier and socketIdentifier in generatorModifier:
            self.layout.prop(generatorModifier, f'["{socketIdentifier}"]', text="Interactive")

    def draw(self, context):
        generatorObject = context.object
        generatorModifier = booleanNodes.findGeneratorModifier(generatorObject)
        socketIdentifiers = booleanNodes.getSocketIdentifiers(generatorModifier.node_group)

        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        isInteractive = booleanNodes.getSocketValue(
            generatorModifier, socketIdentifiers, booleanNodes.SOCKET_INTERACTIVE, True
        )

        if not isInteractive:
            layout.operator("object.helpers_refresh_boolean_generator", icon="FILE_REFRESH")

        status = booleanRuntime.getStatus(generatorObject)

        if status is not None:
            layout.label(text=status[0], icon=status[1])

        for errorIndex, errorLine in enumerate(booleanRuntime.getErrorLines(generatorObject)):
            layout.label(text=errorLine, icon="ERROR" if errorIndex == 0 else "NONE")

        for noteLine in booleanRuntime.getNotes(generatorObject):
            layout.label(text=noteLine, icon="INFO")

        self._drawSocket(layout, generatorModifier, socketIdentifiers, booleanNodes.SOCKET_TARGET)
        self._drawSocket(layout, generatorModifier, socketIdentifiers, booleanNodes.SOCKET_CUTTERS)
        layout.separator()
        self._drawEnumSocket(
            layout, generatorModifier, socketIdentifiers, booleanNodes.SOCKET_OPERATION, booleanNodes.OPERATIONS
        )
        self._drawEnumSocket(
            layout, generatorModifier, socketIdentifiers, booleanNodes.SOCKET_SOLVER, booleanNodes.SOLVERS
        )

        solverIndex = booleanNodes.getSocketValue(
            generatorModifier, socketIdentifiers, booleanNodes.SOCKET_SOLVER, booleanNodes.DEFAULT_SOLVER
        )

        if booleanNodes.getChoice(booleanNodes.SOLVERS, solverIndex) == "EXACT":
            layout.separator()
            self._drawSocket(layout, generatorModifier, socketIdentifiers, booleanNodes.SOCKET_SELF_INTERSECTION)
            self._drawSocket(layout, generatorModifier, socketIdentifiers, booleanNodes.SOCKET_HOLE_TOLERANT)

        layout.separator()
        self._drawSocket(layout, generatorModifier, socketIdentifiers, booleanNodes.SOCKET_REPAIR)

        if booleanNodes.getSocketValue(
            generatorModifier, socketIdentifiers, booleanNodes.SOCKET_REPAIR, booleanNodes.DEFAULT_REPAIR
        ):
            self._drawSocket(layout, generatorModifier, socketIdentifiers, booleanNodes.SOCKET_REPAIR_DISTANCE)

    @staticmethod
    def _drawSocket(layout, generatorModifier, socketIdentifiers, socketName):
        socketIdentifier = socketIdentifiers.get(socketName)

        if socketIdentifier and socketIdentifier in generatorModifier:
            layout.prop(generatorModifier, f'["{socketIdentifier}"]', text=socketName)

    @staticmethod
    def _drawEnumSocket(layout, generatorModifier, socketIdentifiers, socketName, enumItems):
        socketIdentifier = socketIdentifiers.get(socketName)

        if not socketIdentifier or socketIdentifier not in generatorModifier:
            return

        uiData = generatorModifier.id_properties_ui(socketIdentifier)

        if [item[0] for item in uiData.as_dict().get("items", ())] != [item[0] for item in enumItems]:
            uiData.update(items=enumItems)

        layout.prop(generatorModifier, f'["{socketIdentifier}"]', text=socketName)

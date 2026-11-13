import bpy

from .. import moduleReload


booleanModuleNames = (
    "booleanNodes",
    "booleanCollections",
    "booleanRequest",
    "booleanRuntime",
    "booleanOperators",
    "booleanPanel",
)
(
    booleanNodes,
    booleanCollections,
    booleanRequest,
    booleanRuntime,
    booleanOperators,
    booleanPanel,
) = moduleReload.loadModules(__name__, booleanModuleNames, locals())


registeredClasses = (
    booleanOperators.ObjectHelpersAddBooleanGeneratorOperator,
    booleanOperators.ObjectHelpersRefreshBooleanGeneratorOperator,
    booleanPanel.View3DHelpersBooleanPanel,
    booleanPanel.PropertiesHelpersBooleanGeneratorPanel,
)


def register():
    for blenderClass in registeredClasses:
        bpy.utils.register_class(blenderClass)

    booleanRuntime.addBooleanHandlers()


def unregister():
    booleanRuntime.removeBooleanHandlers()

    for blenderClass in reversed(registeredClasses):
        try:
            bpy.utils.unregister_class(blenderClass)
        except RuntimeError:
            pass

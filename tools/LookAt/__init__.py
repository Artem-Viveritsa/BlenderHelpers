import bpy
from bpy.props import PointerProperty

from .. import moduleReload


lookAtModuleNames = (
    "lookAtRuntime",
    "lookAtProperties",
    "lookAtPanel",
)
(
    lookAtRuntime,
    lookAtProperties,
    lookAtPanel,
) = moduleReload.loadModules(__name__, lookAtModuleNames, locals())


registeredClasses = (
    lookAtProperties.HelpersLookAtSceneSettings,
    lookAtPanel.View3DHelpersLookAtPanel,
)


def register():
    for blenderClass in registeredClasses:
        bpy.utils.register_class(blenderClass)

    bpy.types.Scene.helpersLookAtSettings = PointerProperty(
        type=lookAtProperties.HelpersLookAtSceneSettings
    )
    lookAtRuntime.addLookAtHandler()


def unregister():
    lookAtRuntime.removeLookAtHandler()

    if hasattr(bpy.types.Scene, "helpersLookAtSettings"):
        del bpy.types.Scene.helpersLookAtSettings

    for blenderClass in reversed(registeredClasses):
        try:
            bpy.utils.unregister_class(blenderClass)
        except RuntimeError:
            pass
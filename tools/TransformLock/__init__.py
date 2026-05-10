import bpy
from bpy.props import PointerProperty

from .. import moduleReload


transformLockModuleNames = (
    "lockOverlay",
    "lockProperties",
    "lockOperators",
    "lockPanel",
)
(
    lockOverlay,
    lockProperties,
    lockOperators,
    lockPanel,
) = moduleReload.loadModules(__name__, transformLockModuleNames, locals())


registeredClasses = (
    lockProperties.HelpersTransformLockWindowManagerSettings,
    lockProperties.HelpersTransformLockSceneSettings,
    lockOperators.ObjectHelpersSetTransformLockOperator,
    lockPanel.View3DHelpersTransformLockPanel,
)


def register():
    for blenderClass in registeredClasses:
        bpy.utils.register_class(blenderClass)

    bpy.types.WindowManager.helpersTransformLockSettings = PointerProperty(
        type=lockProperties.HelpersTransformLockWindowManagerSettings
    )
    bpy.types.Scene.helpersTransformLockSettings = PointerProperty(
        type=lockProperties.HelpersTransformLockSceneSettings
    )
    lockOverlay.addOverlayHandler()


def unregister():
    lockOverlay.removeOverlayHandler()

    if hasattr(bpy.types.Scene, "helpersTransformLockSettings"):
        del bpy.types.Scene.helpersTransformLockSettings
    if hasattr(bpy.types.WindowManager, "helpersTransformLockSettings"):
        del bpy.types.WindowManager.helpersTransformLockSettings

    for blenderClass in reversed(registeredClasses):
        try:
            bpy.utils.unregister_class(blenderClass)
        except RuntimeError:
            pass

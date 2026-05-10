if "moduleReload" in locals():
    import importlib

    importlib.reload(moduleReload)
else:
    from . import moduleReload


toolPackageNames = ("TransformLock",)
toolPackages = moduleReload.loadModules(__name__, toolPackageNames, locals())


def register():
    for toolPackage in toolPackages:
        toolPackage.register()


def unregister():
    for toolPackage in reversed(toolPackages):
        toolPackage.unregister()

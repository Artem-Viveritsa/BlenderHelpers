import importlib


def loadModules(packageName, moduleNames, moduleGlobals):
    loadedModules = []

    for moduleName in moduleNames:
        existingModule = moduleGlobals.get(moduleName)

        if existingModule is None:
            loadedModule = importlib.import_module(f".{moduleName}", packageName)
        else:
            loadedModule = importlib.reload(existingModule)

        moduleGlobals[moduleName] = loadedModule
        loadedModules.append(loadedModule)

    return tuple(loadedModules)
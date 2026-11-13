import atexit

from .. import moduleReload


backgroundTaskModuleNames = (
    "taskTransfer",
    "taskMeshes",
    "taskJobs",
    "taskScheduler",
)
(
    taskTransfer,
    taskMeshes,
    taskJobs,
    taskScheduler,
) = moduleReload.loadModules(__name__, backgroundTaskModuleNames, locals())


def register():
    atexit.register(taskJobs.killActiveJobs)


def unregister():
    taskJobs.killActiveJobs()
    atexit.unregister(taskJobs.killActiveJobs)

# Blender Helpers

Blender Helpers is a Blender add-on that groups a small set of workflow tools under a single `Helpers` panel in the 3D Viewport. The add-on currently ships with three tool groups:

- Transform Lock: applies transform channel locks to selected objects and visualizes locked channels with viewport stripes.
- Look At: keeps the camera and 3D viewport aligned to the face under the snapped active object.
- Boolean: creates an auto-updating boolean result of a target object and a collection of cutters.

## Installation

1. Install the add-on from Blender's add-on manager or by copying this repository into Blender's add-ons folder.
2. Enable the `Helpers` add-on in Blender Preferences.
3. Open the 3D Viewport sidebar and use the `Helpers` tab.

## Available Tools

### Transform Lock

The Transform Lock tool applies or clears location, rotation, and scale locks on all selected objects. It also draws a striped overlay in the 3D Viewport to make locked channels visible at a glance.

What it does in practice:

- Adds a scene-wide toggle for the viewport overlay.
- Stores overlay preferences in the Window Manager and scene settings.
- Draws lock stripes only for mesh objects that actually have locked channels.
- Supports both regular objects and instanced objects in the viewport.
- Redraws the viewport whenever overlay visibility or display options change.

UI controls:

- `Transform Lock Overlay`: master switch for the striped overlay.
- `Location`, `Rotation`, `Scale`: choose which locked channels are shown in the overlay.
- `Opacity`: controls the visibility of the overlay stripes.
- `Location`, `Rotation`, `Scale` action buttons: lock or unlock the selected channel on all selected objects.

### Look At

The Look At tool keeps the camera pointed at the face hit by the active object when face snapping is enabled. It uses the active object's transform updates as the trigger, then searches nearby mesh objects for the closest face hit. When a valid hit is found, the tool aligns the scene camera and any visible 3D Viewport navigation views toward that target.

What it does in practice:

- Watches the active object's transform changes through a persistent depsgraph handler.
- Requires face snapping to be enabled in the scene tool settings.
- Optionally limits the search to a specific target mesh object.
- Can constrain orbit so the camera/view keeps a world-Z-aligned orbit.
- Stops and clears its animation state when the setting is disabled, when manual camera/view control is detected, or when no valid face target is found.

UI controls:

- `Look At`: master enable switch.
- `Constraint Orbit`: keeps the orbit aligned to world Z while the tool is active.
- `Target Object`: optional mesh object used as the only alignment target.

### Boolean

The Boolean tool creates a generator object: an auto-updating copy of a target mesh with the objects of a collection subtracted from it (or added / intersected). The target and the cutters stay unchanged. The boolean runs in a separate background Blender process that receives the meshes through a pipe and returns the result the same way, so the viewport stays responsive while heavy meshes are being cut and no temporary files are created.

What it does in practice:

- Adds a `Boolean Generator` button to the `Boolean` panel that asks for the target object and the cutters collection.
- Creates a new object with a geometry nodes modifier that stores the generator settings.
- Recomputes the result when the target, the cutters or the settings change, and restores the result after a file is loaded.
- Can repair the target and the cutters before the operation (merge doubled vertices, remove loose geometry, fill holes, fix normals) without touching the originals.

UI controls (Properties editor, Modifiers tab, `Boolean Generator` panel):

- `Interactive`: update automatically; when off, use the `Refresh` button to update manually.
- `Target`, `Cutters`: the mesh object and the collection of cutter objects.
- `Operation`: Difference, Union or Intersect.
- `Solver`: Exact, Manifold or Float. Exact also offers `Self Intersection` and `Hole Tolerant`.
- `Repair`, `Repair Distance`: pre-process the sources before the operation.

## Background Tasks

`tools/BackgroundTasks` runs heavy operations in a separate background Blender process, so the interface stays responsive. It has no UI of its own and is used by other tools.

A tool provides three things:

- A task script with `run(header, payload)`. It runs in a clean factory-startup Blender, can `import taskTransfer` and `import taskMeshes`, and returns `(responseHeader, payloadWriter)`. Any exception is returned to the main process and shown as error lines.
- `prepareTask(key, isForced)`: called on the main thread; returns `TaskRequest(signature, requestData, context)` built with `taskTransfer.encodeFrame`, or `None` when nothing has to run.
- `applyResult(key, job, responseHeader, payload)`: called on the main thread when the result is ready; `job.context` is the context from the request.

```python
scheduler = taskScheduler.TaskScheduler(taskScriptPath, prepareTask=prepareTask, applyResult=applyResult, canProcess=canProcess)
scheduler.schedule(key)
scheduler.runNow(key)
scheduler.getStatus(key)
scheduler.getErrorLines(key)
scheduler.clear()
```

Updates of the same key are debounced, a newer request cancels the running job of that key, the number of parallel processes is limited, and all processes are killed when Blender quits. `canProcess(key)` returning `False` postpones both the start and the result of that key, for example while the object is in Edit Mode. Results should be written into existing datablocks: creating or removing datablocks from a timer is not safe for undo and the outliner.

## How The Add-On Is Structured

The repository is organized into small, focused modules:

- `tools/TransformLock/lockProperties.py`: scene and Window Manager settings for overlay behavior and lock actions.
- `tools/TransformLock/lockOperators.py`: operator that toggles transform locks on selected objects.
- `tools/TransformLock/lockOverlay.py`: custom GPU overlay drawing for locked channels.
- `tools/TransformLock/lockPanel.py`: 3D Viewport UI for Transform Lock.
- `tools/LookAt/lookAtRuntime.py`: runtime logic, depsgraph handler, animation state, and camera/view alignment calculations.
- `tools/LookAt/lookAtProperties.py`: scene properties and validation for the Look At tool.
- `tools/LookAt/lookAtPanel.py`: 3D Viewport UI for Look At.
- `tools/Boolean/booleanNodes.py`: geometry nodes group, sockets and modifier values of the generator.
- `tools/Boolean/booleanCollections.py`: collection lookup helpers.
- `tools/Boolean/booleanRequest.py`: request building for the worker, cutter collection, and update signatures.
- `tools/Boolean/booleanRuntime.py`: depsgraph/load handlers, task preparation and result application on top of `BackgroundTasks`.
- `tools/Boolean/booleanWorker.py`: background task script with `run(header, payload)` that performs the boolean.
- `tools/Boolean/booleanOperators.py`: add and refresh operators.
- `tools/Boolean/booleanPanel.py`: 3D Viewport panel and the generator modifier panel.
- `tools/BackgroundTasks/taskScheduler.py`: debounced, keyed scheduler of background tasks with parallel limit, cancellation, status and error lines.
- `tools/BackgroundTasks/taskJobs.py`: background Blender processes, pipe communication and worker error extraction.
- `tools/BackgroundTasks/taskWorkerHost.py`: entry script of the background Blender process that loads a task script and returns its result through the pipe.
- `tools/BackgroundTasks/taskTransfer.py`: binary frames with a JSON header and a raw payload, shared by both processes.
- `tools/BackgroundTasks/taskMeshes.py`: packing and filling of meshes (geometry and attributes) for the payload, shared by both processes.
- `tools/moduleReload.py`: helper for reloading submodules during development.

The package entry points are:

- `__init__.py`: registers the add-on package.
- `tools/__init__.py`: registers and unregisters all tool groups.
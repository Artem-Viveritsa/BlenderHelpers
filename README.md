# Blender Helpers

Blender Helpers is a Blender add-on that groups a small set of workflow tools under a single `Helpers` panel in the 3D Viewport. The add-on currently ships with two tool groups:

- Transform Lock: applies transform channel locks to selected objects and visualizes locked channels with viewport stripes.
- Look At: keeps the camera and 3D viewport aligned to the face under the snapped active object.

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

## How The Add-On Is Structured

The repository is organized into small, focused modules:

- `tools/LookAt/lookAtRuntime.py`: runtime logic, depsgraph handler, animation state, and camera/view alignment calculations.
- `tools/LookAt/lookAtProperties.py`: scene properties and validation for the Look At tool.
- `tools/LookAt/lookAtPanel.py`: 3D Viewport UI for Look At.
- `tools/TransformLock/lockProperties.py`: scene and Window Manager settings for overlay behavior and lock actions.
- `tools/TransformLock/lockOperators.py`: operator that toggles transform locks on selected objects.
- `tools/TransformLock/lockOverlay.py`: custom GPU overlay drawing for locked channels.
- `tools/TransformLock/lockPanel.py`: 3D Viewport UI for Transform Lock.
- `tools/moduleReload.py`: helper for reloading submodules during development.

The package entry points are:

- `__init__.py`: registers the add-on package.
- `tools/__init__.py`: registers and unregisters both tool groups.
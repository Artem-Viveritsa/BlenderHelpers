from bpy.props import BoolProperty, FloatProperty
from bpy.types import PropertyGroup


def updateTransformLockOverlayVisibility(self, context):
    from . import lockOverlay

    lockOverlay.syncOverlayHandlerVisibility(self, context)


def updateTransformLockOverlayDisplay(self, context):
    tagView3DAreasForRedraw(context)


def setSelectedObjectsTransformChannelLockState(context, transformChannel, shouldLock):
    for selectedObject in context.selected_objects:
        if transformChannel == "LOCATION":
            selectedObject.lock_location = (shouldLock, shouldLock, shouldLock)
        elif transformChannel == "ROTATION":
            selectedObject.lock_rotation = (shouldLock, shouldLock, shouldLock)
            if selectedObject.lock_rotations_4d:
                selectedObject.lock_rotation_w = shouldLock
        elif transformChannel == "SCALE":
            selectedObject.lock_scale = (shouldLock, shouldLock, shouldLock)
        else:
            raise ValueError(f"Unsupported transform channel: {transformChannel}")

    tagView3DAreasForRedraw(context)


def tagView3DAreasForRedraw(context):
    screen = context.screen

    if screen is not None:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


class HelpersTransformLockWindowManagerSettings(PropertyGroup):
    showTransformLockOverlay: BoolProperty(
        name="Transform Lock Overlay",
        description="Display transform lock stripes in the 3D Viewport",
        default=True,
        update=updateTransformLockOverlayVisibility,
    )


class HelpersTransformLockSceneSettings(PropertyGroup):
    showLocationLocksInOverlay: BoolProperty(
        name="Location",
        description="Show horizontal stripes for objects with locked location axes",
        default=True,
        update=updateTransformLockOverlayDisplay,
    )
    showRotationLocksInOverlay: BoolProperty(
        name="Rotation",
        description="Show diagonal stripes for objects with locked rotation axes",
        default=True,
        update=updateTransformLockOverlayDisplay,
    )
    showScaleLocksInOverlay: BoolProperty(
        name="Scale",
        description="Show vertical stripes for objects with locked scale axes",
        default=True,
        update=updateTransformLockOverlayDisplay,
    )
    transformLockOverlayOpacity: FloatProperty(
        name="Overlay Opacity",
        description="Set the opacity of transform lock stripes in the 3D Viewport",
        default=0.25,
        min=0.1,
        max=0.5,
        precision=2,
        subtype="FACTOR",
        update=updateTransformLockOverlayDisplay,
    )

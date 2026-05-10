import bpy
import gpu
from gpu_extras.batch import batch_for_shader


_overlayHandler = None
_overlayShader = None

_lockOverlayColor = (0.0, 0.0, 0.0)
_hatchSpacing = 18.0
_stripeWidth = 4.0
_depthOffset = 1e-4


def addOverlayHandler():
    global _overlayHandler

    if _overlayHandler is None:
        _overlayHandler = bpy.types.SpaceView3D.draw_handler_add(
            _drawOverlay, (), "WINDOW", "POST_VIEW"
        )


def removeOverlayHandler():
    global _overlayHandler

    if _overlayHandler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_overlayHandler, "WINDOW")
        _overlayHandler = None


def _tagView3DAreasForRedraw(context):
    screen = getattr(context, "screen", None)

    if screen is not None:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()


def syncOverlayHandlerVisibility(windowManagerSettings, context):
    if windowManagerSettings.showTransformLockOverlay:
        addOverlayHandler()
    else:
        removeOverlayHandler()

    _tagView3DAreasForRedraw(context)


def _getOverlayShader():
    global _overlayShader

    if _overlayShader is None:
        shaderInfo = gpu.types.GPUShaderCreateInfo()
        shaderInfo.push_constant("MAT4", "viewProjectionMatrix")
        shaderInfo.push_constant("FLOAT", "depthOffset")
        shaderInfo.push_constant("VEC3", "color")
        shaderInfo.push_constant("FLOAT", "opacity")
        shaderInfo.push_constant("FLOAT", "useLocation")
        shaderInfo.push_constant("FLOAT", "useRotation")
        shaderInfo.push_constant("FLOAT", "useScale")
        shaderInfo.push_constant("FLOAT", "stripeSpacing")
        shaderInfo.push_constant("FLOAT", "stripeWidth")
        shaderInfo.vertex_in(0, "VEC3", "pos")
        shaderInfo.fragment_out(0, "VEC4", "fragColor")
        shaderInfo.vertex_source(
            """
            void main()
            {
                vec4 position = viewProjectionMatrix * vec4(pos, 1.0);
                position.z -= depthOffset * position.w;
                gl_Position = position;
            }
            """
        )
        shaderInfo.fragment_source(
            """
            bool stripe_hit(vec2 direction)
            {
                float directionCount = useLocation + useRotation + useScale;
                float localSpacing = stripeSpacing;

                if (directionCount > 2.5 && abs(direction.x) > 0.0 && abs(direction.y) > 0.0) {
                    localSpacing *= 1.41421356237;
                }

                float coord = dot(gl_FragCoord.xy, normalize(direction));
                float halfSpacing = localSpacing * 0.5;
                float stripeDistance = abs(mod(coord + halfSpacing, localSpacing) - halfSpacing);
                return stripeDistance <= stripeWidth * 0.5;
            }

            void main()
            {
                bool visible = false;

                if (useLocation > 0.5) {
                    visible = stripe_hit(vec2(0.0, 1.0));
                }

                if (!visible && useRotation > 0.5) {
                    visible = stripe_hit(vec2(1.0, -1.0));
                }

                if (!visible && useScale > 0.5) {
                    visible = stripe_hit(vec2(1.0, 0.0));
                }

                if (!visible) {
                    discard;
                }

                fragColor = vec4(color, opacity);
            }
            """
        )
        _overlayShader = gpu.shader.create_from_info(shaderInfo)

    return _overlayShader


def _buildMeshBatch(shader, depsgraph, transformSource, sourceObject):
    evaluatedObject = sourceObject.evaluated_get(depsgraph)
    mesh = evaluatedObject.to_mesh()

    if mesh is None:
        return None

    try:
        mesh.transform(transformSource.matrix_world)
        mesh.calc_loop_triangles()

        if len(mesh.vertices) == 0 or len(mesh.loop_triangles) == 0:
            return None

        vertexPositions = [vertex.co[:] for vertex in mesh.vertices]
        triangleIndices = [tuple(loopTriangle.vertices) for loopTriangle in mesh.loop_triangles]

        return batch_for_shader(shader, "TRIS", {"pos": vertexPositions}, indices=triangleIndices)
    finally:
        evaluatedObject.to_mesh_clear()


def _drawOverlayStripes(shader, batch, opacity, activeLockFlags):
    shader.uniform_float("color", _lockOverlayColor)
    shader.uniform_float("opacity", opacity)
    shader.uniform_float("useLocation", 1.0 if activeLockFlags[0] else 0.0)
    shader.uniform_float("useRotation", 1.0 if activeLockFlags[1] else 0.0)
    shader.uniform_float("useScale", 1.0 if activeLockFlags[2] else 0.0)
    batch.draw(shader)


def _getActiveLockFlags(selectedObject, sceneSettings):
    return (
        sceneSettings.showLocationLocksInOverlay and _hasLocationLock(selectedObject),
        sceneSettings.showRotationLocksInOverlay and _hasRotationLock(selectedObject),
        sceneSettings.showScaleLocksInOverlay and _hasScaleLock(selectedObject),
    )


def _hasLocationLock(selectedObject):
    return any(selectedObject.lock_location)


def _hasRotationLock(selectedObject):
    return any(selectedObject.lock_rotation) or (
        selectedObject.lock_rotations_4d and selectedObject.lock_rotation_w
    )


def _hasScaleLock(selectedObject):
    return any(selectedObject.lock_scale)


def _iterateOverlayObjects(context, depsgraph, sceneSettings):
    activeLockFlagsByObjectId = {}

    for visibleObject in context.visible_objects:
        originalObject = visibleObject.original

        if originalObject.type != "MESH":
            continue

        activeLockFlags = _getActiveLockFlags(originalObject, sceneSettings)

        if not any(activeLockFlags):
            continue

        activeLockFlagsByObjectId[originalObject.as_pointer()] = activeLockFlags
        yield visibleObject, originalObject, activeLockFlags

    for objectInstance in depsgraph.object_instances:
        if not objectInstance.is_instance or objectInstance.instance_object is None:
            continue

        originalObject = objectInstance.instance_object.original

        if originalObject.type != "MESH":
            continue

        objectId = originalObject.as_pointer()
        activeLockFlags = activeLockFlagsByObjectId.get(objectId)

        if activeLockFlags is None:
            activeLockFlags = _getActiveLockFlags(originalObject, sceneSettings)

            if not any(activeLockFlags):
                continue

            activeLockFlagsByObjectId[objectId] = activeLockFlags

        parentObject = objectInstance.parent.original if objectInstance.parent is not None else None
        if parentObject is not None and not parentObject.visible_get():
            continue

        yield objectInstance, originalObject, activeLockFlags


def _drawOverlay():
    context = bpy.context
    spaceData = context.space_data

    if spaceData is None or spaceData.type != "VIEW_3D":
        return

    if not spaceData.overlay.show_overlays:
        return

    region3d = spaceData.region_3d
    if region3d is None:
        return

    scene = context.scene
    if scene is None or not hasattr(scene, "helpersTransformLockSettings"):
        return

    sceneSettings = scene.helpersTransformLockSettings
    if not (
        sceneSettings.showLocationLocksInOverlay
        or sceneSettings.showRotationLocksInOverlay
        or sceneSettings.showScaleLocksInOverlay
    ):
        return

    depsgraph = context.evaluated_depsgraph_get()
    shader = _getOverlayShader()

    gpu.state.blend_set("ALPHA")
    gpu.state.depth_mask_set(False)
    gpu.state.depth_test_set("LESS_EQUAL")

    try:
        shader.bind()
        shader.uniform_float("viewProjectionMatrix", region3d.perspective_matrix)
        shader.uniform_float("depthOffset", _depthOffset)
        shader.uniform_float("stripeSpacing", _hatchSpacing)
        shader.uniform_float("stripeWidth", _stripeWidth)

        for transformSource, sourceObject, activeLockFlags in _iterateOverlayObjects(
            context, depsgraph, sceneSettings
        ):
            batch = _buildMeshBatch(shader, depsgraph, transformSource, sourceObject)

            if batch is not None:
                _drawOverlayStripes(
                    shader,
                    batch,
                    sceneSettings.transformLockOverlayOpacity,
                    activeLockFlags,
                )
    finally:
        gpu.state.blend_set("NONE")
        gpu.state.depth_test_set("NONE")
        gpu.state.depth_mask_set(True)
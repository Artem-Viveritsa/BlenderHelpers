import bpy
import time
from bpy.app.handlers import persistent
from mathutils import Matrix, Vector


# Constants
MINIMUM_CAMERA_DISTANCE = 0.1
MINIMUM_SEARCH_DISTANCE = 0.05
DEFAULT_SEARCH_DISTANCE = 1.0
SEARCH_DISTANCE_OBJECT_SCALE = 1.5
SMOOTHING_TIME = 0.1
CONTROL_RELEASE_DELAY = 0.5
CONTROL_RELEASE_TIMER_INTERVAL = 1.0 / 60.0
MINIMUM_UPDATE_TIME_DELTA = 1.0 / 60.0
MAXIMUM_UPDATE_TIME_DELTA = 1.0 / 30.0
MANUAL_LOCATION_TOLERANCE = 1e-4
MANUAL_ROTATION_TOLERANCE = 1e-4
MANUAL_DISTANCE_TOLERANCE = 1e-4
EPSILON = 1e-12
SMALL_EPSILON = 1e-6
WORLD_X_VECTOR = Vector((1.0, 0.0, 0.0))
WORLD_Y_VECTOR = Vector((0.0, 1.0, 0.0))
WORLD_UP_VECTOR = Vector((0.0, 0.0, 1.0))
VIEW_FORWARD_VECTOR = Vector((0.0, 0.0, -1.0))


# Runtime state
_isUpdatingLookAt = False
_lookAtAnimation = None


def addLookAtHandler():
    removeLookAtHandler()
    bpy.app.handlers.depsgraph_update_post.append(_handleDepsgraphUpdate)


def removeLookAtHandler():
    clearLookAtAnimation()

    depsgraphHandlers = bpy.app.handlers.depsgraph_update_post

    for depsgraphHandler in tuple(depsgraphHandlers):
        if _isLookAtHandler(depsgraphHandler):
            depsgraphHandlers.remove(depsgraphHandler)


def clearLookAtAnimation():
    global _lookAtAnimation

    _lookAtAnimation = None
    _removeControlReleaseTimer()


@persistent
def _handleDepsgraphUpdate(scene, depsgraph):
    if _isUpdatingLookAt:
        return

    context = bpy.context
    activeObject = _getActiveObject(context)
    if activeObject is None:
        return

    if not _hasActiveObjectTransformUpdate(depsgraph, activeObject):
        return

    sceneSettings = getattr(scene, "helpersLookAtSettings", None)
    if sceneSettings is None or not sceneSettings.isLookAtEnabled:
        clearLookAtAnimation()
        return

    if not _isFaceSnapEnabled(scene):
        clearLookAtAnimation()
        return

    nearestFaceHit = _findNearestFaceHit(
        context,
        scene,
        depsgraph,
        activeObject,
        getattr(sceneSettings, "targetObject", None),
    )
    if nearestFaceHit is None:
        clearLookAtAnimation()
        return

    targetLocation, faceNormal = nearestFaceHit
    cameraSideNormal = _chooseCameraSideNormal(context, scene, targetLocation, faceNormal)
    _startLookAtAnimation(
        context,
        scene,
        targetLocation,
        cameraSideNormal,
        getattr(sceneSettings, "constrainOrbit", False),
    )


def _isLookAtHandler(depsgraphHandler):
    return (
        getattr(depsgraphHandler, "__module__", "") == __name__
        and getattr(depsgraphHandler, "__name__", "") == "_handleDepsgraphUpdate"
    )


def _startLookAtAnimation(
    context,
    scene,
    targetLocation,
    cameraSideNormal,
    shouldConstrainOrbit,
):
    global _lookAtAnimation

    currentTime = time.perf_counter()
    cameraState = _createCameraAnimationState(
        scene,
        targetLocation,
        cameraSideNormal,
        shouldConstrainOrbit,
    )
    viewStates = _createViewAnimationStates(
        context,
        targetLocation,
        cameraSideNormal,
        shouldConstrainOrbit,
    )

    if cameraState is None and len(viewStates) == 0:
        clearLookAtAnimation()
        return

    if _lookAtAnimation is not None:
        timeDelta = _calculateUpdateTimeDelta(currentTime)
        _lookAtAnimation["lastUpdateTime"] = currentTime
        _lookAtAnimation["lastControlTime"] = currentTime
        _retargetLookAtAnimation(cameraState, viewStates)
        _lookAtAnimation["cameraSideNormal"] = cameraSideNormal.copy()
        _applyLookAtInterpolationFactor(_calculateSmoothingFactor(timeDelta))
        _ensureControlReleaseTimer()
        return

    _lookAtAnimation = {
        "lastUpdateTime": currentTime,
        "lastControlTime": currentTime,
        "cameraState": cameraState,
        "viewStates": viewStates,
        "cameraSideNormal": cameraSideNormal.copy(),
    }
    _applyLookAtInterpolationFactor(_calculateSmoothingFactor(MINIMUM_UPDATE_TIME_DELTA))
    _ensureControlReleaseTimer()


def _retargetLookAtAnimation(cameraState, viewStates):
    existingCameraState = _lookAtAnimation["cameraState"]

    if existingCameraState is None or cameraState is None:
        _lookAtAnimation["cameraState"] = cameraState
    elif existingCameraState["cameraObject"] == cameraState["cameraObject"]:
        existingCameraState["targetLocation"] = cameraState["targetLocation"]
        existingCameraState["targetRotation"] = cameraState["targetRotation"]
        existingCameraState["scale"] = cameraState["scale"]
    else:
        _lookAtAnimation["cameraState"] = cameraState

    existingViewStatesByPointer = {}

    for existingViewState in _lookAtAnimation["viewStates"]:
        try:
            existingViewStatesByPointer[
                existingViewState["region3d"].as_pointer()
            ] = existingViewState
        except ReferenceError:
            continue

    retargetedViewStates = []

    for viewState in viewStates:
        try:
            existingViewState = existingViewStatesByPointer.get(
                viewState["region3d"].as_pointer()
            )
        except ReferenceError:
            continue

        if existingViewState is None:
            retargetedViewStates.append(viewState)
            continue

        existingViewState["targetLocation"] = viewState["targetLocation"]
        existingViewState["targetRotation"] = viewState["targetRotation"]
        existingViewState["targetDistance"] = viewState["targetDistance"]
        retargetedViewStates.append(existingViewState)

    _lookAtAnimation["viewStates"] = retargetedViewStates


def _ensureControlReleaseTimer():
    if not bpy.app.timers.is_registered(_continueLookAtAfterMove):
        bpy.app.timers.register(
            _continueLookAtAfterMove,
            first_interval=CONTROL_RELEASE_TIMER_INTERVAL,
        )


def _removeControlReleaseTimer():
    try:
        if bpy.app.timers.is_registered(_continueLookAtAfterMove):
            bpy.app.timers.unregister(_continueLookAtAfterMove)
    except ValueError:
        pass


def _continueLookAtAfterMove():
    if _lookAtAnimation is None:
        return None

    currentTime = time.perf_counter()
    if _hasManualControlChange():
        clearLookAtAnimation()
        return None

    if currentTime - _lookAtAnimation["lastControlTime"] >= CONTROL_RELEASE_DELAY:
        _applyLookAtInterpolationFactor(1.0)
        clearLookAtAnimation()
        return None

    timeDelta = _calculateUpdateTimeDelta(currentTime)
    _lookAtAnimation["lastUpdateTime"] = currentTime
    _applyLookAtInterpolationFactor(_calculateSmoothingFactor(timeDelta))

    return CONTROL_RELEASE_TIMER_INTERVAL


def _applyLookAtInterpolationFactor(interpolationFactor):
    global _isUpdatingLookAt

    if _lookAtAnimation is None:
        return

    _isUpdatingLookAt = True
    try:
        _animateCameraState(
            _lookAtAnimation["cameraState"], interpolationFactor
        )
        _animateViewStates(
            _lookAtAnimation["viewStates"], interpolationFactor
        )
    finally:
        _isUpdatingLookAt = False


def _calculateSmoothingFactor(timeDelta):
    if timeDelta <= 0.0:
        return 0.0

    normalizedStep = min(timeDelta / max(SMOOTHING_TIME, SMALL_EPSILON), 1.0)
    return normalizedStep * normalizedStep * (3.0 - 2.0 * normalizedStep)


def _calculateUpdateTimeDelta(currentTime):
    timeDelta = currentTime - _lookAtAnimation["lastUpdateTime"]
    return min(max(timeDelta, MINIMUM_UPDATE_TIME_DELTA), MAXIMUM_UPDATE_TIME_DELTA)


def _createCameraAnimationState(
    scene,
    targetLocation,
    cameraSideNormal,
    shouldConstrainOrbit,
):
    cameraObject = scene.camera
    if cameraObject is None or cameraObject.type != "CAMERA":
        return None

    cameraDistance = _calculateCameraDistance(cameraObject, targetLocation, cameraSideNormal)
    cameraLocation = targetLocation + cameraSideNormal * cameraDistance
    cameraRotation = _calculateLookAtRotation(
        targetLocation - cameraLocation,
        cameraObject.matrix_world.to_quaternion(),
        shouldConstrainOrbit,
    )
    if cameraRotation is None:
        return None

    return {
        "cameraObject": cameraObject,
        "targetLocation": cameraLocation,
        "targetRotation": cameraRotation,
        "scale": cameraObject.matrix_world.to_scale(),
    }


def _createViewAnimationStates(
    context,
    targetLocation,
    cameraSideNormal,
    shouldConstrainOrbit,
):
    screen = getattr(context, "screen", None)
    if screen is None:
        return []

    viewDirection = -cameraSideNormal
    if viewDirection.length_squared < EPSILON:
        return []

    viewStates = []

    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue

        for space in area.spaces:
            if space.type != "VIEW_3D" or space.region_3d is None:
                continue

            region3d = space.region_3d
            if region3d.view_perspective == "CAMERA":
                continue

            targetRotation = _calculateLookAtRotation(
                viewDirection,
                region3d.view_rotation,
                shouldConstrainOrbit,
            )
            if targetRotation is None:
                continue

            viewStates.append(
                {
                    "area": area,
                    "region3d": region3d,
                    "targetLocation": targetLocation.copy(),
                    "targetRotation": targetRotation,
                    "targetDistance": max(region3d.view_distance, MINIMUM_CAMERA_DISTANCE),
                }
            )

    return viewStates


def _animateCameraState(cameraState, interpolationFactor):
    if cameraState is None:
        return

    try:
        cameraObject = cameraState["cameraObject"]
        currentLocation = cameraObject.matrix_world.translation.copy()
        currentRotation = cameraObject.matrix_world.to_quaternion()
        targetLocation = cameraState["targetLocation"]
        targetRotation = cameraState["targetRotation"]
        cameraLocation = currentLocation.lerp(targetLocation, interpolationFactor)
        cameraRotation = currentRotation.slerp(targetRotation, interpolationFactor)
        cameraObject.matrix_world = Matrix.LocRotScale(
            cameraLocation, cameraRotation, cameraState["scale"]
        )
        cameraState["lastAppliedLocation"] = cameraLocation.copy()
        cameraState["lastAppliedRotation"] = cameraRotation.copy()
    except ReferenceError:
        return


def _animateViewStates(viewStates, interpolationFactor):
    for viewState in viewStates:
        try:
            region3d = viewState["region3d"]
            currentLocation = region3d.view_location.copy()
            currentRotation = region3d.view_rotation.copy()
            currentDistance = region3d.view_distance
            targetLocation = viewState["targetLocation"]
            targetRotation = viewState["targetRotation"]
            targetDistance = viewState["targetDistance"]

            region3d.view_location = currentLocation.lerp(
                targetLocation, interpolationFactor
            )
            region3d.view_rotation = currentRotation.slerp(
                targetRotation, interpolationFactor
            )
            region3d.view_distance = currentDistance + (
                targetDistance - currentDistance
            ) * interpolationFactor
            viewState["lastAppliedLocation"] = region3d.view_location.copy()
            viewState["lastAppliedRotation"] = region3d.view_rotation.copy()
            viewState["lastAppliedDistance"] = region3d.view_distance

            viewState["area"].tag_redraw()
        except ReferenceError:
            continue


def _hasManualControlChange():
    return _hasManualCameraChange(_lookAtAnimation["cameraState"]) or _hasManualViewChange(
        _lookAtAnimation["viewStates"]
    )


def _hasManualCameraChange(cameraState):
    if cameraState is None or "lastAppliedLocation" not in cameraState:
        return False

    try:
        cameraObject = cameraState["cameraObject"]
        return not _isTransformCloseEnough(
            cameraObject.matrix_world.translation,
            cameraState["lastAppliedLocation"],
            cameraObject.matrix_world.to_quaternion(),
            cameraState["lastAppliedRotation"],
        )
    except ReferenceError:
        return True


def _hasManualViewChange(viewStates):
    for viewState in viewStates:
        if "lastAppliedLocation" not in viewState:
            continue

        try:
            region3d = viewState["region3d"]
            hasTransformChange = not _isTransformCloseEnough(
                region3d.view_location,
                viewState["lastAppliedLocation"],
                region3d.view_rotation,
                viewState["lastAppliedRotation"],
            )
            hasDistanceChange = (
                abs(region3d.view_distance - viewState["lastAppliedDistance"])
                > MANUAL_DISTANCE_TOLERANCE
            )

            if hasTransformChange or hasDistanceChange:
                return True
        except ReferenceError:
            return True

    return False


def _isTransformCloseEnough(currentLocation, expectedLocation, currentRotation, expectedRotation):
    return (
        (currentLocation - expectedLocation).length <= MANUAL_LOCATION_TOLERANCE
        and currentRotation.rotation_difference(expectedRotation).angle <= MANUAL_ROTATION_TOLERANCE
    )


def _isFaceSnapEnabled(scene):
    toolSettings = getattr(scene, "tool_settings", None)
    if toolSettings is None or not getattr(toolSettings, "use_snap", False):
        return False

    snapElements = getattr(toolSettings, "snap_elements", None)
    if snapElements is None:
        snapElement = getattr(toolSettings, "snap_element", "")
        return "FACE" in snapElement

    return any("FACE" in snapElement for snapElement in snapElements)


def _getActiveObject(context):
    viewLayer = getattr(context, "view_layer", None)
    if viewLayer is None:
        return None

    activeObject = viewLayer.objects.active
    if activeObject is None:
        return None

    if activeObject.type == "CAMERA" or getattr(activeObject, "mode", "OBJECT") != "OBJECT":
        return None

    return activeObject


def _hasActiveObjectTransformUpdate(depsgraph, activeObject):
    for depsgraphUpdate in depsgraph.updates:
        updatedId = depsgraphUpdate.id

        originalId = getattr(updatedId, "original", None)
        if updatedId != activeObject and originalId != activeObject:
            continue

        if getattr(depsgraphUpdate, "is_updated_transform", False):
            return True

    return False


def _findNearestFaceHit(context, scene, depsgraph, activeObject, targetObject):
    sourceLocation = activeObject.matrix_world.translation.copy()
    searchDistance = _calculateSearchDistance(activeObject)
    nearestFaceHit = None

    for candidateObject in _iterateTargetMeshObjects(context, scene, activeObject, targetObject):
        faceHit = _findClosestFaceHitOnObject(
            candidateObject, depsgraph, sourceLocation, searchDistance
        )

        if faceHit is None:
            continue

        if nearestFaceHit is None or faceHit[2] < nearestFaceHit[2]:
            nearestFaceHit = faceHit

    if nearestFaceHit is None:
        return None

    return nearestFaceHit[0], nearestFaceHit[1]


def _iterateTargetMeshObjects(context, scene, activeObject, targetObject):
    viewLayer = getattr(context, "view_layer", None)

    if targetObject is not None:
        if (
            targetObject.type == "MESH"
            and targetObject != activeObject
            and _isObjectVisibleInViewLayer(targetObject, viewLayer)
        ):
            yield targetObject

        return

    selectedObjectPointers = {
        selectedObject.as_pointer()
        for selectedObject in getattr(context, "selected_objects", ())
    }
    candidateObjects = viewLayer.objects if viewLayer is not None else scene.objects

    for candidateObject in candidateObjects:
        if (
            candidateObject.type != "MESH"
            or candidateObject == activeObject
            or candidateObject.as_pointer() in selectedObjectPointers
            or not _isObjectVisibleInViewLayer(candidateObject, viewLayer)
        ):
            continue

        yield candidateObject


def _isObjectVisibleInViewLayer(candidateObject, viewLayer):
    try:
        return candidateObject.visible_get(view_layer=viewLayer)
    except TypeError:
        pass
    except RuntimeError:
        return False

    try:
        return candidateObject.visible_get()
    except RuntimeError:
        return False


def _findClosestFaceHitOnObject(candidateObject, depsgraph, sourceLocation, searchDistance):
    evaluatedObject = candidateObject.evaluated_get(depsgraph)
    worldToLocalMatrix = evaluatedObject.matrix_world.inverted_safe()
    localSourceLocation = worldToLocalMatrix @ sourceLocation
    localSearchDistance = _calculateLocalSearchDistance(worldToLocalMatrix, searchDistance)

    try:
        didHit, localHitLocation, localHitNormal, faceIndex = evaluatedObject.closest_point_on_mesh(
            localSourceLocation, distance=localSearchDistance
        )
    except RuntimeError:
        return None

    if not didHit or faceIndex < 0:
        return None

    worldHitLocation = evaluatedObject.matrix_world @ localHitLocation
    worldDistance = (worldHitLocation - sourceLocation).length
    if worldDistance > searchDistance:
        return None

    normalMatrix = evaluatedObject.matrix_world.to_3x3().inverted_safe().transposed()
    worldNormal = normalMatrix @ localHitNormal
    if worldNormal.length_squared < EPSILON:
        return None

    return worldHitLocation, worldNormal.normalized(), worldDistance


def _calculateSearchDistance(activeObject):
    objectSize = max(activeObject.dimensions) if activeObject.dimensions.length > 0.0 else 0.0

    if objectSize <= 0.0:
        objectSize = DEFAULT_SEARCH_DISTANCE

    return max(objectSize * SEARCH_DISTANCE_OBJECT_SCALE, MINIMUM_SEARCH_DISTANCE)


def _calculateLocalSearchDistance(worldToLocalMatrix, searchDistance):
    worldToLocalBasis = worldToLocalMatrix.to_3x3()
    localScale = max(
        (worldToLocalBasis @ WORLD_X_VECTOR).length,
        (worldToLocalBasis @ WORLD_Y_VECTOR).length,
        (worldToLocalBasis @ WORLD_UP_VECTOR).length,
    )

    return searchDistance * max(localScale, SMALL_EPSILON)


def _chooseCameraSideNormal(context, scene, targetLocation, faceNormal):
    previousCameraSideNormal = _getPreviousCameraSideNormal()
    if previousCameraSideNormal is not None:
        normalDot = faceNormal.dot(previousCameraSideNormal)

        if abs(normalDot) > SMALL_EPSILON:
            return faceNormal if normalDot > 0.0 else -faceNormal

    cameraObject = scene.camera
    sideReferenceOffset = None

    if cameraObject is not None:
        sideReferenceOffset = cameraObject.matrix_world.translation - targetLocation
    else:
        sideReferenceOffset = _getFirstView3DOffset(context, targetLocation)

    if sideReferenceOffset is not None and sideReferenceOffset.length_squared > EPSILON:
        if faceNormal.dot(sideReferenceOffset) < 0.0:
            return -faceNormal

    return faceNormal


def _getPreviousCameraSideNormal():
    if _lookAtAnimation is None:
        return None

    previousCameraSideNormal = _lookAtAnimation.get("cameraSideNormal")
    if previousCameraSideNormal is None or previousCameraSideNormal.length_squared < EPSILON:
        return None

    return previousCameraSideNormal.normalized()


def _getFirstView3DOffset(context, targetLocation):
    screen = getattr(context, "screen", None)
    if screen is None:
        return None

    for area in screen.areas:
        if area.type != "VIEW_3D":
            continue

        for space in area.spaces:
            if space.type != "VIEW_3D" or space.region_3d is None:
                continue

            region3d = space.region_3d
            viewDirection = region3d.view_rotation @ VIEW_FORWARD_VECTOR
            viewLocation = region3d.view_location - viewDirection * region3d.view_distance
            return viewLocation - targetLocation

    return None


def _calculateLookAtRotation(viewDirection, referenceRotation, shouldConstrainOrbit):
    if viewDirection.length_squared < EPSILON:
        return None

    normalizedViewDirection = viewDirection.normalized()
    upReferenceVector = WORLD_UP_VECTOR

    if not shouldConstrainOrbit and referenceRotation is not None:
        upReferenceVector = referenceRotation @ WORLD_Y_VECTOR

    return _calculateRotationFromUpVector(normalizedViewDirection, upReferenceVector)


def _calculateRotationFromUpVector(viewDirection, upReferenceVector):
    projectedUpVector = upReferenceVector - viewDirection * upReferenceVector.dot(viewDirection)

    if projectedUpVector.length_squared < EPSILON:
        projectedUpVector = WORLD_UP_VECTOR - viewDirection * viewDirection.z

    if projectedUpVector.length_squared < EPSILON:
        projectedUpVector = WORLD_Y_VECTOR - viewDirection * viewDirection.y

    if projectedUpVector.length_squared < EPSILON:
        return viewDirection.to_track_quat("-Z", "Y")

    upAxis = projectedUpVector.normalized()
    rightAxis = viewDirection.cross(upAxis)

    if rightAxis.length_squared < EPSILON:
        return viewDirection.to_track_quat("-Z", "Y")

    rightAxis.normalize()
    upAxis = rightAxis.cross(viewDirection).normalized()
    return Matrix((rightAxis, upAxis, -viewDirection)).transposed().to_quaternion()


def _calculateCameraDistance(cameraObject, targetLocation, cameraSideNormal):
    currentCameraOffset = cameraObject.matrix_world.translation - targetLocation
    projectedDistance = currentCameraOffset.dot(cameraSideNormal)

    if projectedDistance > MINIMUM_CAMERA_DISTANCE:
        return projectedDistance

    return max(currentCameraOffset.length, MINIMUM_CAMERA_DISTANCE)
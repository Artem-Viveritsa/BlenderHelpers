import bpy


def isSceneCollection(collection):
    return any(scene.collection == collection for scene in bpy.data.scenes)


def getCollectionByName(collectionName):
    collection = bpy.data.collections.get(collectionName) if collectionName else None

    if collection is not None and isSceneCollection(collection):
        return None

    return collection


def getActiveCollection(context):
    if context.collection is not None and not isSceneCollection(context.collection):
        return context.collection

    activeLayerCollection = context.view_layer.active_layer_collection

    if activeLayerCollection is not None and not isSceneCollection(activeLayerCollection.collection):
        return activeLayerCollection.collection

    activeObject = context.object

    if activeObject is not None:
        for objectCollection in activeObject.users_collection:
            if not isSceneCollection(objectCollection):
                return objectCollection

    return None

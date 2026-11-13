import bmesh
import bpy
import taskMeshes
import taskTransfer
from mathutils import Matrix


def run(header, payload):
    settings = header["settings"]

    sourceObjects = []
    displayNames = {}

    for source in header["sources"]:
        sourceMesh = taskMeshes.fillMesh(bpy.data.meshes.new(source["name"]), source["mesh"], payload)
        sourceObject = bpy.data.objects.new(source["name"], sourceMesh)
        sourceMatrix = Matrix(source["matrix"])

        if source["isMatrixBaked"]:
            sourceMesh.transform(sourceMatrix)

            if sourceMatrix.determinant() < 0:
                sourceMesh.flip_normals()
        else:
            sourceObject.matrix_world = sourceMatrix

        bpy.context.scene.collection.objects.link(sourceObject)
        sourceObjects.append(sourceObject)
        displayNames[source["name"]] = source["displayName"]

    targetObject, *cutterObjects = sourceObjects
    report = {"repaired": {}, "resultOpenEdges": 0}

    if settings["repair"]:
        for sourceObject in sourceObjects:
            repairStats = _repairMesh(sourceObject.data, settings["repairDistance"])

            if any(repairStats.values()):
                report["repaired"][displayNames[sourceObject.name]] = repairStats

    isExactSolver = settings["solver"] == "EXACT"

    for cutterObject in cutterObjects:
        booleanModifier = targetObject.modifiers.new(cutterObject.name, "BOOLEAN")
        booleanModifier.operation = settings["operation"]
        booleanModifier.operand_type = "OBJECT"
        booleanModifier.solver = settings["solver"]
        booleanModifier.object = cutterObject

        if isExactSolver:
            booleanModifier.use_self = settings["selfIntersection"]
            booleanModifier.use_hole_tolerant = settings["holeTolerant"]

    depsgraph = bpy.context.evaluated_depsgraph_get()
    resultMesh = bpy.data.meshes.new_from_object(targetObject.evaluated_get(depsgraph), depsgraph=depsgraph)
    report["resultOpenEdges"] = _countOpenEdges(resultMesh)

    payloadWriter = taskTransfer.PayloadWriter()
    responseHeader = {"report": report, "mesh": taskMeshes.packMesh(resultMesh, payloadWriter)}

    return responseHeader, payloadWriter


def _repairMesh(mesh, mergeDistance):
    meshBuffer = bmesh.new()
    meshBuffer.from_mesh(mesh)

    vertexCount = len(meshBuffer.verts)
    bmesh.ops.remove_doubles(meshBuffer, verts=meshBuffer.verts, dist=mergeDistance)
    mergedVertexCount = vertexCount - len(meshBuffer.verts)

    bmesh.ops.dissolve_degenerate(meshBuffer, dist=mergeDistance, edges=meshBuffer.edges)

    looseVertices = [vertex for vertex in meshBuffer.verts if not vertex.link_faces]
    bmesh.ops.delete(meshBuffer, geom=looseVertices, context="VERTS")

    boundaryEdges = [edge for edge in meshBuffer.edges if edge.is_boundary]

    if boundaryEdges:
        bmesh.ops.holes_fill(meshBuffer, edges=boundaryEdges, sides=0)

    meshBuffer.normal_update()
    originalNormals = [face.normal.copy() for face in meshBuffer.faces]
    bmesh.ops.recalc_face_normals(meshBuffer, faces=meshBuffer.faces)
    meshBuffer.normal_update()
    flippedFaceCount = sum(
        1 for face, originalNormal in zip(meshBuffer.faces, originalNormals) if face.normal.dot(originalNormal) < 0.0
    )

    repairStats = {
        "merged": mergedVertexCount,
        "loose": len(looseVertices),
        "open": len(boundaryEdges),
        "flipped": flippedFaceCount,
    }

    if any(repairStats.values()):
        meshBuffer.to_mesh(mesh)
        mesh.update()

    meshBuffer.free()

    return repairStats


def _countOpenEdges(mesh):
    meshBuffer = bmesh.new()
    meshBuffer.from_mesh(mesh)
    openEdgeCount = sum(1 for edge in meshBuffer.edges if edge.is_boundary)
    meshBuffer.free()

    return openEdgeCount

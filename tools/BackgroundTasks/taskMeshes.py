import numpy as np


ATTRIBUTE_LAYOUTS = {
    "FLOAT": ("value", np.float32, 1),
    "INT": ("value", np.int32, 1),
    "INT8": ("value", np.int8, 1),
    "BOOLEAN": ("value", np.bool_, 1),
    "FLOAT_VECTOR": ("vector", np.float32, 3),
    "FLOAT2": ("vector", np.float32, 2),
    "FLOAT_COLOR": ("color", np.float32, 4),
    "BYTE_COLOR": ("color", np.float32, 4),
}
ATTRIBUTE_DOMAINS = ("POINT", "EDGE", "FACE", "CORNER")


def packMesh(mesh, payloadWriter):
    vertexCount = len(mesh.vertices)
    edgeCount = len(mesh.edges)
    polygonCount = len(mesh.polygons)
    loopCount = len(mesh.loops)
    domainCounts = _getDomainCounts(vertexCount, edgeCount, polygonCount, loopCount)

    arrays = {
        "co": payloadWriter.add(_readArray(mesh.vertices, "co", np.float32, vertexCount * 3)),
        "edgeVertices": payloadWriter.add(_readArray(mesh.edges, "vertices", np.int32, edgeCount * 2)),
        "loopVertex": payloadWriter.add(_readArray(mesh.loops, "vertex_index", np.int32, loopCount)),
        "loopEdge": payloadWriter.add(_readArray(mesh.loops, "edge_index", np.int32, loopCount)),
        "polygonStart": payloadWriter.add(_readArray(mesh.polygons, "loop_start", np.int32, polygonCount)),
    }
    attributes = []

    for attribute in mesh.attributes:
        layout = ATTRIBUTE_LAYOUTS.get(attribute.data_type)

        if attribute.name.startswith(".") or attribute.name == "position":
            continue

        if layout is None or attribute.domain not in ATTRIBUTE_DOMAINS:
            continue

        dataKey, dataType, componentCount = layout
        values = _readArray(attribute.data, dataKey, dataType, domainCounts[attribute.domain] * componentCount)
        attributes.append(
            {
                "name": attribute.name,
                "domain": attribute.domain,
                "type": attribute.data_type,
                "offset": payloadWriter.add(values),
            }
        )

    return {"counts": [vertexCount, edgeCount, polygonCount, loopCount], "arrays": arrays, "attributes": attributes}


def fillMesh(mesh, descriptor, payload):
    vertexCount, edgeCount, polygonCount, loopCount = descriptor["counts"]
    domainCounts = _getDomainCounts(vertexCount, edgeCount, polygonCount, loopCount)
    arrays = descriptor["arrays"]

    mesh.clear_geometry()
    mesh.vertices.add(vertexCount)
    mesh.edges.add(edgeCount)
    mesh.loops.add(loopCount)
    mesh.polygons.add(polygonCount)

    mesh.vertices.foreach_set("co", _viewArray(payload, arrays["co"], np.float32, vertexCount * 3))
    mesh.edges.foreach_set("vertices", _viewArray(payload, arrays["edgeVertices"], np.int32, edgeCount * 2))
    mesh.loops.foreach_set("vertex_index", _viewArray(payload, arrays["loopVertex"], np.int32, loopCount))
    mesh.loops.foreach_set("edge_index", _viewArray(payload, arrays["loopEdge"], np.int32, loopCount))
    mesh.polygons.foreach_set("loop_start", _viewArray(payload, arrays["polygonStart"], np.int32, polygonCount))
    mesh.update()

    for entry in descriptor["attributes"]:
        dataKey, dataType, componentCount = ATTRIBUTE_LAYOUTS[entry["type"]]
        attribute = mesh.attributes.get(entry["name"])

        if attribute is None:
            attribute = mesh.attributes.new(entry["name"], entry["type"], entry["domain"])

        values = _viewArray(payload, entry["offset"], dataType, domainCounts[entry["domain"]] * componentCount)
        attribute.data.foreach_set(dataKey, values)

    mesh.update()

    return mesh


def _getDomainCounts(vertexCount, edgeCount, polygonCount, loopCount):
    return {"POINT": vertexCount, "EDGE": edgeCount, "FACE": polygonCount, "CORNER": loopCount}


def _readArray(collection, dataKey, dataType, size):
    values = np.empty(size, dtype=dataType)
    collection.foreach_get(dataKey, values)

    return values


def _viewArray(payload, offset, dataType, size):
    return np.frombuffer(payload, dtype=dataType, count=size, offset=offset)

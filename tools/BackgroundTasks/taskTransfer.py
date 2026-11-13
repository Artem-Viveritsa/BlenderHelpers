import json
import struct

import numpy as np


FRAME_MARKER = b"\x00HELPERS-BACKGROUND-TASK\x00"
FRAME_LENGTHS = struct.Struct("<QQ")


class PayloadWriter:
    def __init__(self):
        self.chunks = []
        self.size = 0

    def add(self, array):
        chunkBytes = np.ascontiguousarray(array).tobytes()
        offset = self.size
        self.chunks.append(chunkBytes)
        self.size += len(chunkBytes)
        return offset


def encodeFrame(header, payloadWriter):
    headerBytes = json.dumps(header).encode()
    lengthBytes = FRAME_LENGTHS.pack(len(headerBytes), payloadWriter.size)
    return b"".join((FRAME_MARKER, lengthBytes, headerBytes, *payloadWriter.chunks))


def decodeFrame(data):
    markerStart = data.find(FRAME_MARKER)

    if markerStart < 0:
        raise ValueError("Background worker returned no data")

    lengthsStart = markerStart + len(FRAME_MARKER)
    headerSize, payloadSize = FRAME_LENGTHS.unpack_from(data, lengthsStart)
    headerStart = lengthsStart + FRAME_LENGTHS.size
    payloadStart = headerStart + headerSize

    if len(data) < payloadStart + payloadSize:
        raise ValueError("Background worker returned incomplete data")

    header = json.loads(data[headerStart:payloadStart])
    payload = memoryview(data)[payloadStart : payloadStart + payloadSize]

    return header, payload


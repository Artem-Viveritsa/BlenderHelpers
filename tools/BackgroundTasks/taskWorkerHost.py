import importlib.util
import os
import sys
import traceback
from pathlib import Path

import bpy


def main():
    hostDirectory, taskScriptPath = sys.argv[sys.argv.index("--") + 1 :][:2]
    sys.path.insert(0, hostDirectory)
    import taskTransfer

    outputDescriptor = os.dup(1)
    os.dup2(2, 1)

    if sys.platform == "win32":
        import msvcrt

        msvcrt.setmode(0, os.O_BINARY)
        msvcrt.setmode(outputDescriptor, os.O_BINARY)

    outputStream = os.fdopen(outputDescriptor, "wb")

    try:
        requestHeader, payload = taskTransfer.decodeFrame(sys.stdin.buffer.read())
        bpy.ops.wm.read_factory_settings(use_empty=True)
        responseHeader, payloadWriter = _loadTaskModule(Path(taskScriptPath)).run(requestHeader, payload)
    except Exception:
        responseHeader = {"error": traceback.format_exc()}
        payloadWriter = taskTransfer.PayloadWriter()

    outputStream.write(taskTransfer.encodeFrame(responseHeader, payloadWriter))
    outputStream.flush()


def _loadTaskModule(taskScriptPath):
    moduleSpec = importlib.util.spec_from_file_location(taskScriptPath.stem, taskScriptPath)
    taskModule = importlib.util.module_from_spec(moduleSpec)
    moduleSpec.loader.exec_module(taskModule)

    return taskModule


main()

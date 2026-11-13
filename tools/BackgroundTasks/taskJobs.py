import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic

import bpy

from . import taskTransfer


WORKER_HOST_PATH = Path(__file__).with_name("taskWorkerHost.py")
IGNORED_ERROR_PREFIXES = ("Error: script failed", "Blender quit")
MAXIMUM_ERROR_LINES = 3
MAXIMUM_CONSOLE_ERROR_LENGTH = 4000

_activeJobs = set()


class BackgroundTaskError(Exception):
    def __init__(self, errorLines):
        super().__init__(errorLines[-1])
        self.errorLines = errorLines


@dataclass(slots=True, eq=False)
class BackgroundJob:
    process: subprocess.Popen
    thread: threading.Thread
    output: dict
    signature: str
    context: object
    startTime: float = field(default_factory=monotonic)

    @property
    def isFinished(self):
        return not self.thread.is_alive()

    def discard(self):
        self.process.kill()
        self.process.wait()
        _activeJobs.discard(self)

    def readResponse(self):
        _activeJobs.discard(self)

        try:
            responseHeader, payload = taskTransfer.decodeFrame(self.output.get("stdout", b""))
        except ValueError:
            errorText = self.output.get("stderr", b"").decode(errors="replace") or self.output.get("error", "")
            raise BackgroundTaskError(_extractErrorLines(errorText, self.process.returncode)) from None

        if "error" in responseHeader:
            raise BackgroundTaskError(_extractErrorLines(responseHeader["error"], self.process.returncode))

        return responseHeader, payload


def startJob(taskScriptPath, requestData, signature, context=None):
    if not bpy.app.binary_path:
        raise ValueError("Blender executable not found")

    process = subprocess.Popen(
        [
            bpy.app.binary_path,
            "--background",
            "--factory-startup",
            "--python-exit-code",
            "1",
            "--python",
            str(WORKER_HOST_PATH),
            "--",
            str(WORKER_HOST_PATH.parent),
            str(taskScriptPath),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = {}
    thread = threading.Thread(target=_communicate, args=(process, requestData, output), daemon=True)
    thread.start()

    job = BackgroundJob(process, thread, output, signature, context)
    _activeJobs.add(job)

    return job


def killActiveJobs():
    for job in tuple(_activeJobs):
        job.process.kill()

    _activeJobs.clear()


def _communicate(process, requestData, output):
    try:
        output["stdout"], output["stderr"] = process.communicate(requestData)
    except Exception as error:
        output["error"] = str(error)


def _extractErrorLines(errorText, returnCode):
    print(f"Background task failed (exit code {returnCode}):\n{errorText[-MAXIMUM_CONSOLE_ERROR_LENGTH:]}")
    errorLines = [
        line.strip()
        for line in errorText.splitlines()
        if line.strip() and not line.startswith(IGNORED_ERROR_PREFIXES)
    ]

    return errorLines[-MAXIMUM_ERROR_LINES:] or [f"Failed: worker exited with code {returnCode}"]

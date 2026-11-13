import os
import traceback
from dataclasses import dataclass
from time import monotonic

import bpy

from . import taskJobs


DEFAULT_UPDATE_DELAY = 0.3
DEFAULT_POLL_INTERVAL = 0.2
DEFAULT_MAXIMUM_PARALLEL_JOBS = max(1, min(4, (os.cpu_count() or 2) // 2))


@dataclass(slots=True)
class TaskRequest:
    signature: str
    requestData: bytes
    context: object = None


class TaskScheduler:
    def __init__(
        self,
        taskScriptPath,
        prepareTask,
        applyResult,
        canProcess=None,
        updateDelay=DEFAULT_UPDATE_DELAY,
        pollInterval=DEFAULT_POLL_INTERVAL,
        maximumParallelJobs=DEFAULT_MAXIMUM_PARALLEL_JOBS,
    ):
        self.taskScriptPath = taskScriptPath
        self.prepareTask = prepareTask
        self.applyResult = applyResult
        self.canProcess = canProcess or (lambda key: True)
        self.updateDelay = updateDelay
        self.pollInterval = pollInterval
        self.maximumParallelJobs = maximumParallelJobs
        self.pendingUpdates = {}
        self.runningJobs = {}
        self.errorLines = {}
        self._forcedKeys = set()
        self._lastRedrawSecond = None
        self._timerFunction = self._handleTimerTick

    def schedule(self, key, isImmediate=False):
        self.pendingUpdates[key] = monotonic() - (self.updateDelay if isImmediate else 0.0)
        self._ensureTimer()

    def runNow(self, key):
        self.pendingUpdates.pop(key, None)

        if self.canProcess(key):
            self._runSafely(key, self._startTask, key, True)
        else:
            self._forcedKeys.add(key)
            self.schedule(key, isImmediate=True)

        self._ensureTimer()
        _redrawAreas()

    def clear(self):
        if bpy.app.timers.is_registered(self._timerFunction):
            bpy.app.timers.unregister(self._timerFunction)

        for job in self.runningJobs.values():
            job.discard()

        self.pendingUpdates.clear()
        self.runningJobs.clear()
        self.errorLines.clear()
        self._forcedKeys.clear()

    def getStatus(self, key):
        job = self.runningJobs.get(key)

        if job is not None:
            return f"Updating... {monotonic() - job.startTime:.0f} s", "TIME"

        if key in self.pendingUpdates:
            return "Updating...", "TIME"

        return None

    def getErrorLines(self, key):
        return self.errorLines.get(key, [])

    def _ensureTimer(self):
        if not bpy.app.timers.is_registered(self._timerFunction):
            bpy.app.timers.register(self._timerFunction, first_interval=self.pollInterval)

    def _handleTimerTick(self):
        currentTime = monotonic()
        finishedKeys = [key for key, job in self.runningJobs.items() if job.isFinished and self.canProcess(key)]

        for key in finishedKeys:
            self._runSafely(key, self._finishTask, key, self.runningJobs.pop(key))

        readyKeys = [
            key
            for key in sorted(self.pendingUpdates, key=self.pendingUpdates.get)
            if currentTime - self.pendingUpdates[key] >= self.updateDelay and self.canProcess(key)
        ]

        for key in readyKeys:
            if len(self.runningJobs) >= self.maximumParallelJobs:
                break

            del self.pendingUpdates[key]
            self._runSafely(key, self._startTask, key, key in self._forcedKeys)
            self._forcedKeys.discard(key)

        if finishedKeys or readyKeys or int(currentTime) != self._lastRedrawSecond:
            self._lastRedrawSecond = int(currentTime)
            _redrawAreas()

        if not self.pendingUpdates and not self.runningJobs:
            return None

        return self.pollInterval

    def _startTask(self, key, isForced):
        taskRequest = self.prepareTask(key, isForced)
        runningJob = self.runningJobs.get(key)

        if runningJob is not None:
            if taskRequest is not None and runningJob.signature == taskRequest.signature:
                return

            self.runningJobs.pop(key).discard()

        if taskRequest is None:
            return

        self.errorLines.pop(key, None)
        self.runningJobs[key] = taskJobs.startJob(
            self.taskScriptPath, taskRequest.requestData, taskRequest.signature, taskRequest.context
        )

    def _finishTask(self, key, job):
        responseHeader, payload = job.readResponse()
        self.applyResult(key, job, responseHeader, payload)

    def _runSafely(self, key, taskFunction, *arguments):
        try:
            taskFunction(*arguments)
        except taskJobs.BackgroundTaskError as error:
            self.errorLines[key] = error.errorLines
        except Exception as error:
            traceback.print_exc()
            self.errorLines[key] = [f"Failed: {error}"]


def _redrawAreas():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()

"""Run slow work (training, export, downloads, loading the models) on a background thread.

Rules that keep the window safe:

* The function you pass never touches widgets. It only reports progress through the callback it gets.
* The callbacks you pass (``on_progress``, ``on_done`` ...) always run on the GUI thread, so they may update
  widgets. This is guaranteed here: a signal connected straight to a lambda would run on the worker thread.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from ..core.train import Cancelled
from ..logs import get_logger

log = get_logger("jobs")

ProgressFn = Callable[[str, float], None]
JobFn = Callable[[ProgressFn, Callable[[], bool]], Any]

_running: set[JobHandle] = set()  # keeps jobs alive until they are finished


class _JobThread(QThread):
    """Runs the function once and ends (no event loop), reporting through signals."""

    progress = Signal(str, float)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn: JobFn):
        super().__init__()
        self._fn = fn
        self.cancel_requested = False

    def run(self) -> None:
        try:
            result = self._fn(lambda msg, f: self.progress.emit(msg, float(f)), lambda: self.cancel_requested)
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:
            log.exception("Background job failed")
            self.failed.emit(str(e) or e.__class__.__name__)
        else:
            self.succeeded.emit(result)


class JobHandle(QObject):
    """Returned by :func:`run_job`. Lives on the GUI thread and passes the job's signals on to your callbacks."""

    def __init__(self, fn: JobFn, on_progress, on_done, on_error, on_cancel):
        super().__init__()  # no parent: it must outlive a closing window until its thread has stopped
        self._callbacks = (on_progress, on_done, on_error, on_cancel)
        self._thread = _JobThread(fn)
        # Connected to methods of this object, which lives on the GUI thread, so they are queued there.
        self._thread.progress.connect(self._progress)
        self._thread.succeeded.connect(self._done)
        self._thread.failed.connect(self._error)
        self._thread.cancelled.connect(self._cancelled)

    def start(self) -> None:
        _running.add(self)
        self._thread.start()

    def cancel(self) -> None:
        self._thread.cancel_requested = True

    def wait(self, timeout_ms: int) -> bool:
        """Block until the job's thread has ended (True) or the time is up (False)."""
        return self._thread.wait(timeout_ms)

    @Slot(str, float)
    def _progress(self, message: str, fraction: float) -> None:
        if self._callbacks[0]:
            self._callbacks[0](message, fraction)

    @Slot(object)
    def _done(self, result: Any) -> None:
        self._finish(1, result)

    @Slot(str)
    def _error(self, message: str) -> None:
        self._finish(2, message)

    @Slot()
    def _cancelled(self) -> None:
        self._finish(3)

    def _finish(self, which: int, *args: Any) -> None:
        self._thread.wait()  # the function has returned, so this is instant
        callback = self._callbacks[which]
        try:
            if callback:
                callback(*args)
        finally:
            # Let go of this job on a later turn of the event loop, never while Qt is still inside one of its slots.
            QTimer.singleShot(0, partial(_running.discard, self))


def run_job(
    fn: JobFn,
    *,
    on_progress: ProgressFn | None = None,
    on_done: Callable[[Any], None] | None = None,
    on_error: Callable[[str], None] | None = None,
    on_cancel: Callable[[], None] | None = None,
) -> JobHandle:
    """Run ``fn(progress, is_cancelled)`` on a new thread; afterwards exactly one of the end callbacks is called.

    ``progress(message, fraction)`` reports progress. ``is_cancelled()`` turns true after ``handle.cancel()``;
    ``fn`` should then raise ``core.train.Cancelled``.
    """
    handle = JobHandle(fn, on_progress, on_done, on_error, on_cancel)
    handle.start()
    return handle


def running_jobs() -> int:
    return sum(1 for handle in _running if not handle.wait(0))


def stop_all(timeout_ms: int = 10_000) -> None:
    """Ask every running job to stop and wait for them (called when the window closes)."""
    for handle in list(_running):
        handle.cancel()
    for handle in list(_running):
        if not handle.wait(timeout_ms):
            log.warning("A background job did not stop within %d ms", timeout_ms)

"""Run slow jobs (training, export, downloads) off the GUI thread."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QThread, Signal

from ..core.train import Cancelled


class Job(QObject):
    progress = Signal(str, float)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, fn: Callable[..., Any]):
        super().__init__()
        self._fn = fn
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def is_cancelled(self) -> bool:
        return self._cancel

    def run(self) -> None:
        try:
            result = self._fn(lambda msg, f: self.progress.emit(msg, float(f)), self.is_cancelled)
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:  # shown to the user
            traceback.print_exc()
            self.failed.emit(str(e) or e.__class__.__name__)
        else:
            self.finished.emit(result)


def start_job(parent: QObject, fn: Callable[..., Any]) -> tuple[Job, QThread]:
    """``fn(progress, is_cancelled)`` runs in a new thread. Keep the returned objects alive."""
    thread = QThread(parent)
    job = Job(fn)
    job.moveToThread(thread)
    thread.started.connect(job.run)
    for sig in (job.finished, job.failed, job.cancelled):
        sig.connect(thread.quit)
    thread.finished.connect(job.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return job, thread

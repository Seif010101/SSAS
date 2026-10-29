"""Background jobs must call back on the GUI thread (a lambda slot would run on the worker thread)."""

import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _run(app, fn):
    from ssas_studio.ui.workers import run_job

    events = []

    def record(name):
        return lambda *a: events.append((name, threading.current_thread(), a))

    run_job(
        fn, on_progress=record("progress"), on_done=record("done"), on_error=record("error"), on_cancel=record("cancel")
    )
    end = time.time() + 10
    while not any(e[0] in ("done", "error", "cancel") for e in events) and time.time() < end:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return events


def test_progress_and_result_arrive_on_the_gui_thread(app):
    def work(progress, cancelled):
        progress("half", 0.5)
        return 42

    events = _run(app, work)
    assert [e[0] for e in events] == ["progress", "done"]
    assert events[0][2] == ("half", 0.5) and events[1][2] == (42,)
    assert all(e[1] is threading.main_thread() for e in events)


def test_errors_arrive_on_the_gui_thread(app):
    def work(progress, cancelled):
        raise ValueError("boom")

    events = _run(app, work)
    assert [(e[0], e[2]) for e in events] == [("error", ("boom",))]
    assert events[0][1] is threading.main_thread()


def test_cancel_arrives_on_the_gui_thread(app):
    from ssas_studio.core.train import Cancelled

    def work(progress, cancelled):
        raise Cancelled()

    events = _run(app, work)
    assert [e[0] for e in events] == ["cancel"] and events[0][1] is threading.main_thread()


def test_stop_all_works_without_the_event_loop(app):
    """Closing the window blocks the GUI thread; running jobs must still be able to end."""
    from ssas_studio.core.train import Cancelled
    from ssas_studio.ui.workers import run_job, running_jobs, stop_all

    def slow(progress, cancelled):
        for _ in range(200):
            if cancelled():
                raise Cancelled()
            time.sleep(0.01)

    run_job(slow)
    assert running_jobs() == 1
    started = time.time()
    stop_all(timeout_ms=5000)
    assert time.time() - started < 1.0  # cancelled at once, not after 2 s
    assert running_jobs() == 0
    app.processEvents()

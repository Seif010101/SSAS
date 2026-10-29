"""A log file and a last-resort error dialog.

The packaged program has no console, so without this a failure in a background job or a crash would be
invisible. Everything is written to ``studio.log`` in the program's data folder.
"""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import time
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .resources import app_data_dir

LOGGER_NAME = "ssas"
_crash_file = None  # kept open for faulthandler


def log_path() -> Path:
    return app_data_dir() / "studio.log"


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def install() -> None:
    """Start logging to a file, record hard crashes, and show unexpected errors instead of dying silently."""
    global _crash_file
    log = logging.getLogger(LOGGER_NAME)
    if log.handlers:
        return
    log.setLevel(logging.INFO)
    handler = RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    try:
        _crash_file = open(log_path().with_name("crash.log"), "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(_crash_file)
    except OSError:
        pass

    def on_error(exc_type, exc, tb):
        log.error("Unhandled error", exc_info=(exc_type, exc, tb))
        _show_error("".join(traceback.format_exception_only(exc_type, exc)).strip())

    def on_thread_error(args):
        log.error(
            "Unhandled error in a background thread", exc_info=(args.exc_type, args.exc_value, args.exc_traceback)
        )

    sys.excepthook = on_error
    threading.excepthook = on_thread_error
    log.info("SSAS Studio started")


_dialog = {"open": False, "last": "", "at": 0.0}


def _show_error(message: str) -> None:
    """Show the error once: not while another error dialog is open, and not the same one twice within a minute."""
    now = time.monotonic()
    if _dialog["open"] or (message == _dialog["last"] and now - _dialog["at"] < 60):
        return
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is None or threading.current_thread() is not threading.main_thread():
            return
        _dialog.update(open=True, last=message, at=now)
        QMessageBox.critical(
            None,
            "SSAS Studio",
            f"Something went wrong:\n\n{message}\n\nDetails were saved in:\n{log_path()}",
        )
    except Exception:  # never let the error dialog itself raise
        pass
    finally:
        _dialog["open"] = False

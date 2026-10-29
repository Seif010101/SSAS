"""Main window with one tab per step."""

from __future__ import annotations

import os

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from .. import __version__
from .capture import CaptureTab
from .classes_tab import ClassesTab
from .common import confirm, muted
from .context import AppContext
from .export_tab import ExportTab
from .schedule_tab import ScheduleTab
from .settings_tab import SettingsTab
from .theme import app_icon
from .train_tab import TrainTab
from .workers import run_job, running_jobs, stop_all


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(f"SSAS Studio {__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1280, 820)

        central = QWidget()
        lay = QVBoxLayout(central)
        head = QHBoxLayout()
        self.school_label = QLabel()
        self.school_label.setProperty("title", True)
        head.addWidget(self.school_label)
        head.addStretch(1)
        self.data_label = muted()
        head.addWidget(self.data_label)
        lay.addLayout(head)

        self.tabs = QTabWidget()
        self.classes = ClassesTab(ctx)
        self.capture = CaptureTab(ctx)
        self.train = TrainTab(ctx)
        self.schedule = ScheduleTab(ctx)
        self.export = ExportTab(ctx)
        self.settings = SettingsTab(ctx)
        for w, name in (
            (self.classes, "1  Classes"),
            (self.capture, "2  Capture"),
            (self.train, "3  Train"),
            (self.schedule, "4  Schedule"),
            (self.export, "5  Export to USB"),
            (self.settings, "Settings"),
        ):
            self.tabs.addTab(w, name)
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        ctx.settings_changed.connect(self.refresh_header)
        self.refresh_header()

    def refresh_header(self):
        self.school_label.setText(f"SSAS Studio — {self.ctx.school.name}")
        self.data_label.setText(f"Data: {self.ctx.data_dir}")

    def first_run_check(self):
        if self.ctx.models_ready:
            # Load the face models in the background now, so "Start camera" and "Train" start at once later.
            run_job(lambda _progress, _cancelled: self.ctx.engine())
            return
        self.tabs.setCurrentWidget(self.settings)
        QMessageBox.information(
            self,
            "SSAS Studio",
            "Welcome! SSAS Studio needs its face models once (about 200 MB).\n"
            "Click “Download models” in the Settings tab (internet needed only for this).",
        )

    def closeEvent(self, event):
        if running_jobs() and not os.environ.get("SSAS_SMOKE_TEST"):
            busy = any(tab.job is not None for tab in (self.train, self.export, self.settings))
            if busy and not confirm(self, "A task is still running (training, export or download). Stop it and close?"):
                event.ignore()
                return
        self.capture.shutdown()
        stop_all()
        super().closeEvent(event)

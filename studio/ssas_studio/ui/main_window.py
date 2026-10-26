"""Main window with one tab per step."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QMessageBox, QTabWidget, QVBoxLayout, QWidget

from .. import __version__
from .capture_tab import CaptureTab
from .classes_tab import ClassesTab
from .common import muted
from .context import AppContext
from .export_tab import ExportTab
from .schedule_tab import ScheduleTab
from .settings_tab import SettingsTab
from .theme import app_icon
from .train_tab import TrainTab


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
        for w, name in ((self.classes, "1  Classes"), (self.capture, "2  Capture"), (self.train, "3  Train"),
                        (self.schedule, "4  Schedule"), (self.export, "5  Export to USB"), (self.settings, "Settings")):
            self.tabs.addTab(w, name)
        lay.addWidget(self.tabs, 1)
        self.setCentralWidget(central)

        ctx.settings_changed.connect(self.refresh_header)
        self.refresh_header()

    def refresh_header(self):
        self.school_label.setText(f"SSAS Studio — {self.ctx.school.name}")
        self.data_label.setText(f"Data: {self.ctx.data_dir}")

    def first_run_check(self):
        if not self.ctx.models_ready:
            self.tabs.setCurrentWidget(self.settings)
            QMessageBox.information(
                self, "SSAS Studio",
                "Welcome! SSAS Studio needs its face models once (about 200 MB).\n"
                "Click “Download models” in the Settings tab (internet needed only for this).",
            )

    def closeEvent(self, event):
        self.capture.shutdown()
        super().closeEvent(event)

"""Live demo: the laptop plays the smart screen, so SSAS can be shown with no screen and no server.

The laptop camera recognises the people of a trained group, "Take attendance" decides like a screen (same rules,
core/attendance.py) in about 15 seconds, and the tab shows the text a screen would send to the server.
Nothing is saved and no picture leaves the laptop.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime

import cv2
from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core import groupmodel
from ..core.attendance import AttendanceAggregator, FrameObservation, frame_health
from ..core.live import DEMO_SHOTS_S, GroupMatcher, analyse, payload_text, result_payload
from ..logs import get_logger
from . import theme
from .capture.worker import CameraProbe, camera_backend
from .common import GroupPicker, error, muted, primary, title
from .context import AppContext

log = get_logger("demo")
SIDE_PANEL_WIDTH = 380
STATUS_TEXT = {"present": "Present ✓", "absent": "Absent", "needs_review": "Needs review", "no_data": "No data"}
STATUS_COLOUR = {"present": theme.OK, "absent": theme.BAD, "needs_review": theme.WARN, "no_data": theme.BAD}
KNOWN, UNKNOWN = QColor("#22c55e"), QColor("#f59e0b")


class DemoWorker(QThread):
    """Reads the laptop camera, recognises faces in every frame, and takes attendance when asked."""

    frame = Signal(QImage, list)  # mirrored picture, [(box, label, known)]
    progress = Signal(int, int)  # pictures taken, pictures planned
    attendance = Signal(object)  # the ssas.result dict a screen would send
    stopped = Signal(str)  # why the camera stopped (emitted last)

    def __init__(self, ctx: AppContext, camera_index: int, group_code: str, model: dict, shots: list[int]):
        super().__init__()
        self.ctx, self.camera_index, self.group_code, self.model, self.shots = (
            ctx,
            camera_index,
            group_code,
            model,
            shots,
        )
        self.min_valid_frames = ctx.org.settings.min_valid_frames
        self._running = True
        self._take = threading.Event()

    def stop(self) -> None:
        self._running = False

    def take_attendance(self) -> None:
        self._take.set()

    def run(self) -> None:
        reason = "Camera stopped"
        try:
            reason = self._loop() or reason
        except Exception as e:
            log.exception("The live demo loop failed")
            reason = f"The camera stopped because of an error: {e}"
        finally:
            self.stopped.emit(reason)

    def _loop(self) -> str | None:
        try:
            engine = self.ctx.engine()
        except Exception as e:
            log.exception("Could not load the face models")
            return f"Could not load the face models: {e}"
        matcher = GroupMatcher(self.model)
        cap = cv2.VideoCapture(self.camera_index, camera_backend())
        if not cap.isOpened():
            return f"Camera {self.camera_index} could not be opened. Choose another camera."
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        agg, started, t0, shot, signature = None, None, 0.0, 0, None
        try:
            while self._running:
                ok, img = cap.read()
                if not ok or img is None:
                    return "The camera stopped sending pictures."
                obs, scores, seen = analyse(engine, matcher, img)
                if self._take.is_set():
                    self._take.clear()
                    agg = AttendanceAggregator(len(matcher.people), self.min_valid_frames)
                    started, t0, shot = datetime.now(), time.monotonic(), 0
                    self.progress.emit(0, len(self.shots))
                if agg is not None and time.monotonic() - t0 >= self.shots[shot]:
                    healthy, _reason, signature = frame_health(img, signature)
                    agg.add(obs if healthy else FrameObservation(valid=False), scores if healthy else None)
                    shot += 1
                    self.progress.emit(shot, len(self.shots))
                    if shot >= len(self.shots) or (agg.all_present() and agg.valid_frames >= 1):
                        self.attendance.emit(result_payload(matcher, self.group_code, agg.result(), started))
                        agg = None
                self._emit_frame(img, seen)
        finally:
            cap.release()
        return None

    def _emit_frame(self, img, seen) -> None:
        mirrored = cv2.flip(img, 1)  # like a mirror
        h, w = mirrored.shape[:2]
        rgb = cv2.cvtColor(mirrored, cv2.COLOR_BGR2RGB)
        picture = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        faces = [([w - f.box[2], f.box[1], w - f.box[0], f.box[3]], f.name, f.person is not None) for f in seen]
        self.frame.emit(picture, faces)


class LiveView(QWidget):
    """The (mirrored) camera picture with a box and a name on every face."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(560, 420)
        self.image: QImage | None = None
        self.faces: list = []
        self.show_names = True

    def show_frame(self, image: QImage, faces: list) -> None:
        self.image, self.faces = image, faces
        self.update()

    def clear(self) -> None:
        self.image, self.faces = None, []
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#0b1220"))
        if self.image is None:
            p.setPen(QColor("#94a3b8"))
            p.setFont(QFont(self.font().family(), 13))
            p.drawText(
                self.rect(),
                Qt.AlignCenter,
                "Choose a trained group and press “Start camera”.\nThis laptop plays the smart screen.",
            )
            return
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        w, h = self.image.width() * scale, self.image.height() * scale
        picture = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        p.drawImage(picture, self.image)
        p.setFont(QFont(self.font().family(), 12, QFont.Bold))
        for (x1, y1, x2, y2), name, known in self.faces:
            colour = KNOWN if known else UNKNOWN
            rect = QRectF(picture.x() + x1 * scale, picture.y() + y1 * scale, (x2 - x1) * scale, (y2 - y1) * scale)
            p.setPen(QPen(colour, 3))
            p.drawRect(rect)
            if self.show_names:
                label = name if known else "unknown"
                tag = QRectF(rect.x(), rect.y() - 26, max(rect.width(), 12.0 * len(label) + 16), 24)
                p.fillRect(tag, colour)
                p.setPen(QColor("#0b1220"))
                p.drawText(tag, Qt.AlignCenter, label)


class DemoTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.worker: DemoWorker | None = None
        self.probe: CameraProbe | None = None
        self._probed = False
        self._stop_reason = ""
        root = QHBoxLayout(self)
        self.view = LiveView()
        root.addWidget(self.view, 1)
        root.addWidget(self._build_side_panel())

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(SIDE_PANEL_WIDTH)
        side = QVBoxLayout(panel)
        side.setContentsMargins(0, 0, 0, 0)
        side.addWidget(title("Live demo"))
        side.addWidget(
            muted(
                "This laptop plays the smart screen: its camera recognises the people of a trained group, and "
                "“Take attendance” decides like a screen does (same rules), in about 15 seconds. "
                "Nothing is saved and no picture leaves the laptop."
            )
        )
        cameras = QHBoxLayout()
        self.camera_box = QComboBox()
        saved = int(self.ctx.qsettings.value("camera_index", 0))
        self.camera_box.addItem(f"Camera {saved}", saved)
        self.refresh_cams = QPushButton("Refresh")
        self.refresh_cams.clicked.connect(self.find_cameras)
        cameras.addWidget(self.camera_box, 1)
        cameras.addWidget(self.refresh_cams)
        side.addLayout(cameras)
        self.group_box = GroupPicker(self.ctx)
        side.addWidget(self.group_box)
        self.names = QCheckBox("Show names on the faces (a real screen shows boxes only)")
        self.names.setChecked(True)
        self.names.toggled.connect(self._names_toggled)
        side.addWidget(self.names)
        self.real_timing = QCheckBox("Real screen timing (up to 4 minutes)")
        side.addWidget(self.real_timing)

        self.start_btn = primary("Start camera")
        self.start_btn.clicked.connect(self.toggle)
        side.addWidget(self.start_btn)
        self.take_btn = QPushButton("Take attendance (like the screen)")
        self.take_btn.setEnabled(False)
        self.take_btn.clicked.connect(self.take_attendance)
        side.addWidget(self.take_btn)
        self.bar = QProgressBar()
        self.bar.setFormat("%v / %m pictures")
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        side.addWidget(self.bar)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        side.addWidget(self.summary)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Name", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        side.addWidget(self.table, 2)
        side.addWidget(muted("What the screen would send to the server (text only, no pictures):"))
        self.payload = QPlainTextEdit()
        self.payload.setReadOnly(True)
        self.payload.setFont(QFont("Consolas", 9))
        side.addWidget(self.payload, 1)
        return panel

    # ----- cameras -----
    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._probed:
            self._probed = True
            self.find_cameras()

    def find_cameras(self) -> None:
        if self.worker or (self.probe and self.probe.isRunning()):
            return
        self.refresh_cams.setEnabled(False)
        self.probe = CameraProbe()
        self.probe.found.connect(self._on_cameras_found)
        self.probe.start()

    def _on_cameras_found(self, cameras: list) -> None:
        self.refresh_cams.setEnabled(True)
        if not cameras:
            return
        wanted = self.camera_box.currentData()
        self.camera_box.clear()
        for number, label in cameras:
            self.camera_box.addItem(label, number)
        self.camera_box.setCurrentIndex(max(0, self.camera_box.findData(wanted)))

    def _names_toggled(self, on: bool) -> None:
        self.view.show_names = on
        self.view.update()

    # ----- start / stop -----
    def toggle(self) -> None:
        if self.worker:
            self.worker.stop()
            return
        if not self.ctx.models_ready:
            return error(
                self, "The face models are not downloaded yet. Open the Settings tab and click “Download models”."
            )
        code = self.group_box.code
        if not code:
            return error(self, "Add a group and its people first (Groups tab).")
        path = self.ctx.org.model_dir(code) / groupmodel.FILE_NAME
        if not path.exists():
            return error(self, f"Group {code} is not trained yet. Capture its people, then train it in the Train tab.")
        try:
            model = groupmodel.read(path)
        except ValueError as e:
            return error(self, str(e))
        number = self.camera_box.currentData() or 0
        self.ctx.qsettings.setValue("camera_index", number)
        shots = list(self.ctx.org.settings.shot_schedule_s) if self.real_timing.isChecked() else list(DEMO_SHOTS_S)
        self._stop_reason = ""
        self.worker = DemoWorker(self.ctx, number, code, model, shots)
        self.worker.frame.connect(self.on_frame)
        self.worker.progress.connect(self.on_progress)
        self.worker.attendance.connect(self.on_attendance)
        self.worker.stopped.connect(self._on_stopped)
        self.worker.finished.connect(self._on_worker_finished)  # the thread has really ended
        self.worker.start()
        self.start_btn.setText("Stop camera")
        self.take_btn.setEnabled(True)
        self._set_controls_enabled(False)
        self.table.setRowCount(0)
        self.summary.setText("")
        self.payload.clear()

    def stop_camera(self) -> None:
        if self.worker:
            self.worker.stop()

    def take_attendance(self) -> None:
        if self.worker:
            self.take_btn.setEnabled(False)
            self.summary.setText("Taking attendance… stay in front of the camera.")
            self.worker.take_attendance()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (self.group_box, self.camera_box, self.refresh_cams, self.real_timing):
            widget.setEnabled(enabled)

    # ----- worker signals (always on the GUI thread) -----
    def on_frame(self, picture: QImage, faces: list) -> None:
        self.view.show_frame(picture, faces)

    def on_progress(self, done: int, total: int) -> None:
        self.bar.setRange(0, total)
        self.bar.setValue(done)

    def on_attendance(self, payload: dict) -> None:
        self.take_btn.setEnabled(self.worker is not None)
        people = payload["people"]
        self.table.setRowCount(0)
        for person in people:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(person["name"]))
            item = QTableWidgetItem(STATUS_TEXT.get(person["status"], person["status"]))
            item.setForeground(QColor(STATUS_COLOUR.get(person["status"], theme.BAD)))
            self.table.setItem(row, 1, item)
        count = {s: sum(1 for p in people if p["status"] == s) for s in STATUS_TEXT}
        self.summary.setText(
            f"<b>{payload['group_code']}</b>: {count['present']} present · {count['absent']} absent · "
            f"{count['needs_review']} to review — from {payload['valid_frames']} good pictures."
        )
        self.payload.setPlainText(payload_text(payload))

    def _on_stopped(self, reason: str) -> None:
        self._stop_reason = reason

    def _on_worker_finished(self) -> None:
        """Only now is it safe to let go of the worker thread."""
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.wait()
        self.start_btn.setText("Start camera")
        self.take_btn.setEnabled(False)
        self._set_controls_enabled(True)
        self.bar.setValue(0)
        self.view.clear()
        if self._stop_reason and self._stop_reason != "Camera stopped":
            error(self, self._stop_reason)

    def shutdown(self) -> None:
        """Called when the window closes."""
        if self.worker:
            self.worker.stop()
            if not self.worker.wait(5000):
                log.warning("The demo camera thread did not stop within 5 s")
        if self.probe:
            self.probe.wait(5000)

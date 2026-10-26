"""Capture student photos with a Face-ID-like ring."""

from __future__ import annotations

import math
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout, QWidget,
)

from ..core.capture_logic import RING_SEGMENTS, CaptureSession
from ..core.landmarks import eye_openness, head_pose
from ..core.quality import check_face, crop_for_storage
from . import theme
from .common import confirm, danger, error, muted, primary, title
from .context import AppContext

SAVE_INTERVAL_S = 0.18


class CameraWorker(QThread):
    frame = Signal(QImage, dict)
    stopped = Signal(str)

    def __init__(self, ctx: AppContext, camera_index: int, target_dir: Path, photos_per_student: int):
        super().__init__()
        self.ctx = ctx
        self.camera_index = camera_index
        self.target_dir = target_dir
        segs = max(1, (photos_per_student - 8) // RING_SEGMENTS)
        self.session = CaptureSession(photos_per_segment=segs, front_photos=max(4, photos_per_student - segs * RING_SEGMENTS))
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            engine = self.ctx.engine()
        except Exception as e:
            self.stopped.emit(f"Could not load the face models: {e}")
            return
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.camera_index, backend)
        if not cap.isOpened():
            self.stopped.emit(f"Camera {self.camera_index} could not be opened. Try another camera number.")
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.target_dir.mkdir(parents=True, exist_ok=True)
        last_save = 0.0
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        counter = 0
        message = "Camera stopped"
        try:
            while self._running:
                ok, img = cap.read()
                if not ok or img is None:
                    message = "The camera stopped sending pictures."
                    break
                faces = engine.detect(img)
                widths = [f.width for f in faces]
                yaw = pitch = openness = None
                problem = None
                main = faces[0] if faces else None
                if main is not None:
                    yaw, pitch = head_pose(main.kps)
                    if engine.landmarks is not None:
                        openness = eye_openness(engine.landmarks.predict(img, main.box))
                    problem = check_face(img, main.box)
                    fh, fw = img.shape[:2]
                    cx = (main.box[0] + main.box[2]) / 2 / fw
                    cy = (main.box[1] + main.box[3]) / 2 / fh
                    if problem is None and (abs(cx - 0.5) > 0.22 or abs(cy - 0.5) > 0.25):
                        problem = "Move your face into the circle"
                self.session.require_blink = engine.landmarks is not None
                fb = self.session.update(widths, yaw, pitch, openness, problem)
                if fb.save and main is not None and time.time() - last_save >= SAVE_INTERVAL_S:
                    crop = crop_for_storage(img, main.box)
                    tag = "front" if fb.target is None else f"seg{fb.target:02d}"
                    counter += 1
                    path = self.target_dir / f"{stamp}-{counter:03d}-{tag}.jpg"
                    ok_enc, enc = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
                    if ok_enc:
                        enc.tofile(str(path))  # works with Arabic folder names on Windows
                    last_save = time.time()
                elif fb.save:
                    # Too soon after the last photo: undo the count so the session stays in sync.
                    if fb.target is None:
                        self.session.front_saved -= 1
                    else:
                        self.session.filled[fb.target] -= 1

                mirrored = cv2.flip(img, 1)
                h, w = mirrored.shape[:2]
                rgb = cv2.cvtColor(mirrored, cv2.COLOR_BGR2RGB)
                qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
                boxes = [[w - f.box[2], f.box[1], w - f.box[0], f.box[3]] for f in faces]
                self.frame.emit(qimg, {
                    "message": fb.message,
                    "target": fb.target if fb.target is not None else (-1 if self.session.current_target is None else self.session.current_target),
                    "looking_straight": self.session.current_target is None and not self.session.finished,
                    "blocked": fb.blocked,
                    "filled": [min(1.0, n / self.session.photos_per_segment) for n in self.session.filled],
                    "front": self.session.front_saved / self.session.front_photos,
                    "saved": self.session.saved_photos,
                    "total": self.session.total_photos,
                    "blink": self.session.blink_done or not self.session.require_blink,
                    "finished": self.session.finished,
                    "boxes": boxes,
                })
                if self.session.finished:
                    message = "Done"
                    break
        finally:
            cap.release()
        self.stopped.emit(message)


class RingView(QWidget):
    """Shows the mirrored camera picture with the capture ring on top."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(560, 420)
        self.image: QImage | None = None
        self.state: dict = {}

    def show_frame(self, image: QImage, state: dict):
        self.image = image
        self.state = state
        self.update()

    def clear(self):
        self.image = None
        self.state = {}
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#0b1220"))
        if self.image is None:
            p.setPen(QColor("#94a3b8"))
            p.setFont(QFont(self.font().family(), 13))
            p.drawText(self.rect(), Qt.AlignCenter, "Choose a student and press “Start camera”")
            return
        img = self.image
        scale = min(self.width() / img.width(), self.height() / img.height())
        w, h = img.width() * scale, img.height() * scale
        ox, oy = (self.width() - w) / 2, (self.height() - h) / 2
        p.drawImage(QRectF(ox, oy, w, h), img)

        for b in self.state.get("boxes", []):
            p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
            p.drawRect(QRectF(ox + b[0] * scale, oy + b[1] * scale, (b[2] - b[0]) * scale, (b[3] - b[1]) * scale))

        # Ring in the middle of the picture.
        r = min(w, h) * 0.36
        cx, cy = ox + w / 2, oy + h / 2
        p.setPen(QPen(QColor(255, 255, 255, 60), 2))
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        filled = self.state.get("filled", [0] * RING_SEGMENTS)
        target = self.state.get("target", -1)
        span = 360 / RING_SEGMENTS
        for seg in range(RING_SEGMENTS):
            start = seg * span - span / 2 + 3
            done = filled[seg] >= 1.0
            if seg == target and not done:
                color, width = QColor("#22c55e"), 16
            elif done:
                color, width = QColor(theme.PRIMARY), 12
            else:
                color, width = QColor(255, 255, 255, 70), 10
            p.setPen(QPen(color, width, Qt.SolidLine, Qt.FlatCap))
            rr = r + 18
            p.drawArc(QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr), int(start * 16), int((span - 6) * 16))
            if 0 < filled[seg] < 1.0:
                p.setPen(QPen(QColor(theme.PRIMARY), 12, Qt.SolidLine, Qt.FlatCap))
                p.drawArc(QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr), int(start * 16), int((span - 6) * filled[seg] * 16))
        if self.state.get("looking_straight"):
            p.setPen(QPen(QColor("#22c55e"), 4))
            p.drawEllipse(QRectF(cx - 10, cy - 10, 20, 20))

        msg = self.state.get("message", "")
        if msg:
            p.setFont(QFont(self.font().family(), 14, QFont.Bold))
            box = QRectF(ox, oy + h - 56, w, 56)
            p.fillRect(box, QColor(0, 0, 0, 150) if not self.state.get("blocked") else QColor(185, 28, 28, 190))
            p.setPen(QColor("white"))
            p.drawText(box, Qt.AlignCenter, msg)


class CaptureTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.worker: CameraWorker | None = None
        root = QHBoxLayout(self)

        self.view = RingView()
        root.addWidget(self.view, 3)

        side = QVBoxLayout()
        side.addWidget(title("Capture photos"))
        side.addWidget(muted(
            "One student at a time, alone in front of the camera, good light on the face. "
            "The student looks straight first, then follows the green part of the circle, and blinks once."
        ))
        form = QGroupBox("Who")
        g = QGridLayout(form)
        self.class_box = QComboBox()
        self.class_box.currentIndexChanged.connect(self.refresh_students)
        self.student_box = QComboBox()
        self.camera_box = QSpinBox()
        self.camera_box.setRange(0, 9)
        self.camera_box.setValue(int(self.ctx.qsettings.value("camera_index", 0)))
        g.addWidget(QLabel("Class"), 0, 0)
        g.addWidget(self.class_box, 0, 1)
        g.addWidget(QLabel("Student"), 1, 0)
        g.addWidget(self.student_box, 1, 1)
        g.addWidget(QLabel("Camera number"), 2, 0)
        g.addWidget(self.camera_box, 2, 1)
        side.addWidget(form)

        self.start_btn = primary("Start camera")
        self.start_btn.clicked.connect(self.toggle)
        side.addWidget(self.start_btn)
        self.retake_btn = danger("Delete this student's photos (retake)")
        self.retake_btn.clicked.connect(self.retake)
        side.addWidget(self.retake_btn)

        status = QGroupBox("Progress")
        sl = QVBoxLayout(status)
        self.count_label = QLabel("Photos: —")
        self.ring_label = QLabel("Circle: —")
        self.blink_label = QLabel("Blink: —")
        for l in (self.count_label, self.ring_label, self.blink_label):
            sl.addWidget(l)
        side.addWidget(status)
        side.addStretch(1)
        self.next_btn = primary("Next student →")
        self.next_btn.clicked.connect(self.next_student)
        side.addWidget(self.next_btn)
        root.addLayout(side, 1)

        ctx.classes_changed.connect(self.refresh_classes)
        self.refresh_classes()

    # ----- lists -----
    def refresh_classes(self):
        current = self.class_box.currentText()
        self.class_box.blockSignals(True)
        self.class_box.clear()
        self.class_box.addItems(self.ctx.school.class_codes())
        if current:
            self.class_box.setCurrentText(current)
        self.class_box.blockSignals(False)
        self.refresh_students()

    def refresh_students(self):
        code = self.class_box.currentText()
        current = self.student_box.currentData()
        self.student_box.clear()
        if not code:
            return
        school = self.ctx.school
        for s in school.load_class(code).students:
            n = len(school.photos(code, s))
            self.student_box.addItem(f"{s.name}  ({n} photos)", s.id)
        if current:
            i = self.student_box.findData(current)
            if i >= 0:
                self.student_box.setCurrentIndex(i)

    def _student(self):
        code = self.class_box.currentText()
        sid = self.student_box.currentData()
        if not (code and sid):
            return code, None
        return code, next((s for s in self.ctx.school.load_class(code).students if s.id == sid), None)

    # ----- camera -----
    def toggle(self):
        if self.worker:
            self.worker.stop()
            return
        if not self.ctx.models_ready:
            return error(self, "The face models are not downloaded yet. Open the Settings tab and click “Download models”.")
        code, student = self._student()
        if not student:
            return error(self, "Choose a class and a student first (add them in the Classes tab).")
        self.ctx.qsettings.setValue("camera_index", self.camera_box.value())
        self.worker = CameraWorker(self.ctx, self.camera_box.value(), self.ctx.school.student_dir(code, student),
                                   self.ctx.school.settings.photos_per_student)
        self.worker.frame.connect(self.on_frame)
        self.worker.stopped.connect(self.on_stopped)
        self.worker.start()
        self.start_btn.setText("Stop camera")
        for w in (self.class_box, self.student_box, self.camera_box, self.retake_btn, self.next_btn):
            w.setEnabled(False)

    def on_frame(self, img: QImage, state: dict):
        self.view.show_frame(img, state)
        self.count_label.setText(f"Photos: {state['saved']} / {state['total']}")
        self.ring_label.setText(f"Circle: {sum(1 for f in state['filled'] if f >= 1)} / {RING_SEGMENTS} parts")
        self.blink_label.setText("Blink: done ✓" if state["blink"] else "Blink: not yet")

    def on_stopped(self, message: str):
        self.worker = None
        self.start_btn.setText("Start camera")
        for w in (self.class_box, self.student_box, self.camera_box, self.retake_btn, self.next_btn):
            w.setEnabled(True)
        code = self.class_box.currentText()
        self.refresh_students()
        if code:
            self.ctx.photos_changed.emit(code)
        if message not in ("Done", "Camera stopped"):
            error(self, message)
        elif message == "Done":
            self.view.state["message"] = "Done — all photos saved. Press “Next student”."
            self.view.update()

    def retake(self):
        code, student = self._student()
        if student and confirm(self, f"Delete all photos of {student.name}?"):
            self.ctx.school.clear_photos(code, student)
            self.refresh_students()
            self.ctx.photos_changed.emit(code)

    def next_student(self):
        if self.student_box.currentIndex() + 1 < self.student_box.count():
            self.student_box.setCurrentIndex(self.student_box.currentIndex() + 1)
        self.view.clear()

    def shutdown(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait(3000)

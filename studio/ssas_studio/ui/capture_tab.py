"""Capture student photos: the camera stays on for the whole class, one student after another."""

from __future__ import annotations

import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
from PySide6.QtCore import QRectF, Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QGroupBox, QHBoxLayout, QListWidget, QListWidgetItem, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from ..core.capture_logic import RING_SEGMENTS, AutoStart, CaptureSession
from ..core.landmarks import eye_openness, head_pose
from ..core.quality import check_face, crop_for_storage
from . import theme
from .common import confirm, danger, error, info, muted, primary, title
from .context import AppContext

SAVE_INTERVAL_S = 0.18
DONE_SHOWN_S = 2.0  # how long "Done ✓" stays on the picture
GIVE_UP_S = 12.0  # nobody in front of the camera for this long: start the student again
PROBE_CAMERAS = 4


def _backend() -> int:
    return cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


class CameraProbe(QThread):
    """Finds the cameras that open (done in the background, it can take a second or two)."""

    found = Signal(list)

    def run(self):
        out = []
        for i in range(PROBE_CAMERAS):
            cap = cv2.VideoCapture(i, _backend())
            if cap.isOpened():
                out.append((i, f"Camera {i}  ({int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}×{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))})"))
            cap.release()
        self.found.emit(out)


def new_session(settings) -> CaptureSession:
    n = settings.photos_per_student
    per_part = max(1, (n - 8) // RING_SEGMENTS)
    return CaptureSession(photos_per_segment=per_part, front_photos=max(4, n - per_part * RING_SEGMENTS),
                          strict_order=settings.strict_order)


class CameraWorker(QThread):
    """Runs the camera and the capture steps. The tab tells it which student is next."""

    frame = Signal(QImage, dict)
    student_done = Signal(str)  # student id
    stopped = Signal(str)

    def __init__(self, ctx: AppContext, camera_index: int):
        super().__init__()
        self.ctx = ctx
        self.camera_index = camera_index
        self.settings = ctx.school.settings
        self._running = True
        self._lock = threading.Lock()
        self._student: tuple[str, str, Path, int] | None = None  # id, name, folder, photos already there
        self._skip = False
        self.capturing = False

    # ----- called from the window -----
    def stop(self):
        self._running = False

    def set_student(self, sid: str | None, name: str = "", folder: Path | None = None, existing: int = 0):
        with self._lock:
            self._student = (sid, name, folder, existing) if sid else None

    def skip(self):
        self._skip = True

    # ----- the camera loop -----
    def run(self):
        try:
            engine = self.ctx.engine()
        except Exception as e:
            self.stopped.emit(f"Could not load the face models: {e}")
            return
        cap = cv2.VideoCapture(self.camera_index, _backend())
        if not cap.isOpened():
            self.stopped.emit(f"Camera {self.camera_index} could not be opened. Choose another camera.")
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        gate = AutoStart()
        session: CaptureSession | None = None
        counter = 0
        stamp = ""
        last_save = 0.0
        last_face = time.monotonic()
        done_until = 0.0
        done_name = ""
        message = "Camera stopped"
        try:
            while self._running:
                ok, img = cap.read()
                if not ok or img is None:
                    message = "The camera stopped sending pictures."
                    break
                now = time.monotonic()
                faces = engine.detect(img)
                widths = [f.width for f in faces]
                if faces:
                    last_face = now
                with self._lock:
                    student = self._student
                skip, self._skip = self._skip, False

                state, text, blocked, hold, target = "idle", "Choose a student in the list", False, 0.0, -1
                if now < done_until:
                    state, text = "done", f"Done ✓   {done_name}"
                    gate.update(widths, now)  # keeps counting how long the last face has been gone
                elif student is not None:
                    sid, name, folder, existing = student
                    if skip and session is not None:
                        session = None
                        gate.rearm()
                    if session is None:
                        hold, ready = gate.update(widths, now)
                        state = "waiting"
                        text = (f"Next: {name} — step in front of the camera" if not widths or gate.need_absence
                                else f"Ready: {name} — hold still" if hold > 0 else "One person at a time, a bit closer")
                        if ready:
                            session = new_session(self.settings)
                            folder.mkdir(parents=True, exist_ok=True)
                            stamp, counter, last_save = datetime.now().strftime("%Y%m%d-%H%M%S"), 0, 0.0
                    if session is not None:
                        if now - last_face > GIVE_UP_S:
                            session = None  # the student walked away
                            gate.rearm()
                            state, text = "waiting", f"Next: {name} — step in front of the camera"
                        else:
                            state = "capturing"
                            main = faces[0] if faces else None
                            yaw = pitch = openness = None
                            problem = None
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
                            session.require_blink = engine.landmarks is not None
                            fb = session.update(widths, yaw, pitch, openness, problem)
                            text, blocked = fb.message, fb.blocked
                            target = fb.target if fb.target is not None else -1
                            if fb.save and main is not None and now - last_save >= SAVE_INTERVAL_S:
                                crop = crop_for_storage(img, main.box)
                                tag = "front" if fb.target is None else f"seg{fb.target:02d}"
                                counter += 1
                                ok_enc, enc = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
                                if ok_enc:
                                    enc.tofile(str(folder / f"{stamp}-{counter:03d}-{tag}.jpg"))  # Arabic folder names work
                                last_save = now
                            elif fb.save:
                                # Too soon after the last photo: undo the count so the session stays in sync.
                                if fb.target is None:
                                    session.front_saved -= 1
                                else:
                                    session.filled[fb.target] -= 1
                            if session.finished:
                                done_name, done_until = name, now + DONE_SHOWN_S
                                self.set_student(None)
                                gate.rearm()
                                finished_id, session = sid, None
                                self.capturing = False
                                self.student_done.emit(finished_id)
                                state, text = "done", f"Done ✓   {name}"
                self.capturing = session is not None

                mirrored = cv2.flip(img, 1)
                h, w = mirrored.shape[:2]
                rgb = cv2.cvtColor(mirrored, cv2.COLOR_BGR2RGB)
                qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
                boxes = [[w - f.box[2], f.box[1], w - f.box[0], f.box[3]] for f in faces]
                info = {"state": state, "message": text, "blocked": blocked, "hold": hold, "target": target,
                        "boxes": boxes, "name": student[1] if student else ""}
                if session is not None:
                    info.update({
                        "phase": session.phase,
                        "filled": [min(1.0, n / session.photos_per_segment) for n in session.filled],
                        "saved": session.saved_photos, "total": session.total_photos,
                        "blink": session.blink_done or not session.require_blink,
                    })
                self.frame.emit(qimg, info)
        finally:
            cap.release()
            self.capturing = False
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
            p.drawText(self.rect(), Qt.AlignCenter, "Press “Start camera”.\nThe camera stays on for the whole class.")
            return
        img = self.image
        scale = min(self.width() / img.width(), self.height() / img.height())
        w, h = img.width() * scale, img.height() * scale
        ox, oy = (self.width() - w) / 2, (self.height() - h) / 2
        p.drawImage(QRectF(ox, oy, w, h), img)
        st = self.state
        capturing = st.get("state") == "capturing"

        for b in st.get("boxes", []):
            p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
            p.drawRect(QRectF(ox + b[0] * scale, oy + b[1] * scale, (b[2] - b[0]) * scale, (b[3] - b[1]) * scale))

        # Ring in the middle of the picture.
        r = min(w, h) * 0.36
        cx, cy = ox + w / 2, oy + h / 2
        p.setPen(QPen(QColor(255, 255, 255, 60), 2))
        p.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
        rr = r + 18
        arc = QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr)
        filled = st.get("filled", [0] * RING_SEGMENTS) if capturing else [0] * RING_SEGMENTS
        target = st.get("target", -1)
        span = 360 / RING_SEGMENTS
        for seg in range(RING_SEGMENTS):
            start = seg * span - span / 2 + 3
            done = filled[seg] >= 1.0
            if seg == target and not done:
                color, width = QColor(theme.OK), 16
            elif done:
                color, width = QColor(theme.PRIMARY), 12
            else:
                color, width = QColor(255, 255, 255, 70), 10
            p.setPen(QPen(color, width, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(arc, int(start * 16), int((span - 6) * 16))
            if 0 < filled[seg] < 1.0:
                p.setPen(QPen(QColor(theme.PRIMARY), 12, Qt.SolidLine, Qt.FlatCap))
                p.drawArc(arc, int(start * 16), int((span - 6) * filled[seg] * 16))
        if capturing and st.get("phase") == "front":
            p.setPen(QPen(QColor(theme.OK), 4))
            p.drawEllipse(QRectF(cx - 10, cy - 10, 20, 20))
        if st.get("state") == "waiting" and st.get("hold", 0) > 0:  # auto-start filling up
            p.setPen(QPen(QColor(theme.OK), 8, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(QRectF(cx - r + 10, cy - r + 10, 2 * r - 20, 2 * r - 20), 90 * 16, int(-360 * st["hold"] * 16))

        if st.get("state") == "done":
            p.fillRect(QRectF(ox, oy, w, h), QColor(22, 163, 74, 90))

        # Student name and counter, top left.
        if st.get("name"):
            label = st["name"] + (f"   {st['saved']} / {st['total']}" if capturing and "saved" in st else "")
            p.setFont(QFont(self.font().family(), 13, QFont.Bold))
            fm = p.fontMetrics()
            box = QRectF(ox + 12, oy + 12, fm.horizontalAdvance(label) + 28, 36)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(box, 8, 8)
            p.setPen(QColor("white"))
            p.drawText(box, Qt.AlignCenter, label)

        msg = st.get("message", "")
        if msg:
            p.setFont(QFont(self.font().family(), 15, QFont.Bold))
            box = QRectF(ox, oy + h - 60, w, 60)
            bad = st.get("blocked")
            p.fillRect(box, QColor(185, 28, 28, 200) if bad else QColor(22, 163, 74, 210) if st.get("state") == "done"
                       else QColor(0, 0, 0, 150))
            p.setPen(QColor("white"))
            p.drawText(box, Qt.AlignCenter, msg)


class CaptureTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.worker: CameraWorker | None = None
        self.probe: CameraProbe | None = None
        self._probed = False
        self._sid: str | None = None  # the student whose turn it is
        root = QHBoxLayout(self)

        self.view = RingView()
        root.addWidget(self.view, 1)

        side_w = QWidget()
        side_w.setFixedWidth(350)
        side = QVBoxLayout(side_w)
        side.setContentsMargins(0, 0, 0, 0)
        side.addWidget(title("Capture photos"))
        side.addWidget(muted(
            "The camera stays on for the whole class. Each student steps in alone, looks at the camera, "
            "then slowly turns their head in a circle and blinks once. It takes about 20 seconds."
        ))

        cam = QHBoxLayout()
        self.camera_box = QComboBox()
        self.camera_box.addItem("Camera 0", 0)
        saved = int(self.ctx.qsettings.value("camera_index", 0))
        i = self.camera_box.findData(saved)
        if i < 0:
            self.camera_box.addItem(f"Camera {saved}", saved)
            i = self.camera_box.count() - 1
        self.camera_box.setCurrentIndex(i)
        self.refresh_cams = QPushButton("Refresh")
        self.refresh_cams.setMinimumWidth(84)
        self.refresh_cams.clicked.connect(self.find_cameras)
        cam.addWidget(self.camera_box, 1)
        cam.addWidget(self.refresh_cams)
        side.addLayout(cam)

        self.class_box = QComboBox()
        self.class_box.currentIndexChanged.connect(self.refresh_students)
        side.addWidget(self.class_box)

        students = QGroupBox("Students")
        sl = QVBoxLayout(students)
        sl.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self.on_pick)
        sl.addWidget(self.list)
        self.class_label = muted("")
        sl.addWidget(self.class_label)
        side.addWidget(students, 1)

        self.start_btn = primary("Start camera   (Space)")
        self.start_btn.setFocusPolicy(Qt.NoFocus)
        self.start_btn.clicked.connect(self.toggle)
        side.addWidget(self.start_btn)

        self.bar = QProgressBar()
        self.bar.setFormat("%v / %m photos")
        self.bar.setRange(0, 1)
        side.addWidget(self.bar)

        row = QHBoxLayout()
        self.skip_btn = QPushButton("Skip student   (Enter)")
        self.skip_btn.setFocusPolicy(Qt.NoFocus)
        self.skip_btn.clicked.connect(self.skip)
        self.retake_btn = danger("Retake…")
        self.retake_btn.setToolTip("Delete the photos of the selected student")
        self.retake_btn.clicked.connect(self.retake)
        row.addWidget(self.skip_btn, 1)
        row.addWidget(self.retake_btn)
        side.addLayout(row)
        root.addWidget(side_w)

        for key, fn in ((Qt.Key_Space, self.toggle), (Qt.Key_Return, self.skip), (Qt.Key_Enter, self.skip)):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(fn)

        ctx.classes_changed.connect(self.refresh_classes)
        ctx.photos_changed.connect(lambda _c: self.refresh_students())
        self.refresh_classes()

    def showEvent(self, e):
        super().showEvent(e)
        if not self._probed:
            self._probed = True
            self.find_cameras()

    # ----- cameras -----
    def find_cameras(self):
        if self.worker or (self.probe and self.probe.isRunning()):
            return
        self.refresh_cams.setEnabled(False)
        self.probe = CameraProbe()
        self.probe.found.connect(self._cameras_found)
        self.probe.start()

    def _cameras_found(self, cams: list):
        self.refresh_cams.setEnabled(True)
        if not cams:
            return
        want = self.camera_box.currentData()
        self.camera_box.clear()
        for idx, label in cams:
            self.camera_box.addItem(label, idx)
        i = self.camera_box.findData(want)
        self.camera_box.setCurrentIndex(max(0, i))

    # ----- lists -----
    def _target(self) -> int:
        return self.ctx.school.settings.photos_per_student

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
        keep = self._sid or (self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None)
        self.list.blockSignals(True)
        self.list.clear()
        done = 0
        if code:
            school, target = self.ctx.school, self._target()
            for s in school.load_class(code).students:
                n = len(school.photos(code, s))
                if n >= target:
                    done += 1
                    it = QListWidgetItem(f"✓  {s.name}")
                    it.setForeground(QColor(theme.OK))
                elif n:
                    it = QListWidgetItem(f"•  {s.name}   ({n}/{target})")
                    it.setForeground(QColor(theme.WARN))
                else:
                    it = QListWidgetItem(f"○  {s.name}")
                    it.setForeground(QColor(theme.MUTED))
                it.setData(Qt.UserRole, s.id)
                self.list.addItem(it)
            self.class_label.setText(f"{done} of {self.list.count()} students done")
        self.list.blockSignals(False)
        if keep:
            self._select(keep, notify=False)
        elif self.list.count():
            self._select_next(None, notify=False)

    def _row_of(self, sid: str) -> int:
        return next((r for r in range(self.list.count()) if self.list.item(r).data(Qt.UserRole) == sid), -1)

    def _complete(self, r: int) -> bool:
        return self.list.item(r).text().startswith("✓")

    def _select(self, sid: str | None, notify: bool = True):
        r = self._row_of(sid) if sid else -1
        self.list.blockSignals(True)
        self.list.setCurrentRow(r)
        self.list.blockSignals(False)
        self._sid = sid if r >= 0 else None
        if notify:
            self._tell_worker()

    def _select_next(self, after: str | None, notify: bool = True) -> bool:
        """Select the next student who still needs photos (after ``after``, wrapping around)."""
        n = self.list.count()
        start = self._row_of(after) + 1 if after else 0
        for k in range(n):
            r = (start + k) % n
            if not self._complete(r):
                self._select(self.list.item(r).data(Qt.UserRole), notify)
                return True
        return False

    def _student(self):
        code = self.class_box.currentText()
        if not (code and self._sid):
            return code, None
        return code, next((s for s in self.ctx.school.load_class(code).students if s.id == self._sid), None)

    def _tell_worker(self):
        if not self.worker:
            return
        code, student = self._student()
        if student is None:
            self.worker.set_student(None)
            return
        self.worker.set_student(student.id, student.name, self.ctx.school.student_dir(code, student),
                                len(self.ctx.school.photos(code, student)))

    def on_pick(self, row: int):
        if row < 0:
            return
        if self.worker and self.worker.capturing:  # not in the middle of a student
            self._select(self._sid, notify=False)
            return
        self._sid = self.list.item(row).data(Qt.UserRole)
        self._tell_worker()

    # ----- camera -----
    def toggle(self):
        if self.worker:
            self.worker.stop()
            return
        if not self.ctx.models_ready:
            return error(self, "The face models are not downloaded yet. Open the Settings tab and click “Download models”.")
        code, student = self._student()
        if not student or (self.list.count() and self._complete(self._row_of(student.id))):
            if not self._select_next(self._sid, notify=False):
                return error(self, "Every student in this class already has all the photos. "
                                   "Pick a student in the list and press Retake to take them again.")
            code, student = self._student()
        if not student:
            return error(self, "Add a class and its students first (Classes tab).")
        idx = self.camera_box.currentData()
        self.ctx.qsettings.setValue("camera_index", idx)
        self.worker = CameraWorker(self.ctx, idx if idx is not None else 0)
        self.worker.frame.connect(self.on_frame)
        self.worker.student_done.connect(self.on_student_done)
        self.worker.stopped.connect(self.on_stopped)
        self._tell_worker()
        self.worker.start()
        self.start_btn.setText("Stop camera   (Space)")
        for w in (self.class_box, self.camera_box, self.refresh_cams, self.retake_btn):
            w.setEnabled(False)

    def on_frame(self, img: QImage, state: dict):
        self.view.show_frame(img, state)
        if state.get("state") == "capturing" and "total" in state:
            self.bar.setRange(0, state["total"])
            self.bar.setValue(state["saved"])
        elif state.get("state") != "done":
            self.bar.setValue(0)

    def on_student_done(self, sid: str):
        code = self.class_box.currentText()
        QApplication.beep()
        self.ctx.photos_changed.emit(code)  # refreshes this list and the Classes tab
        if not self._select_next(sid):
            if self.worker:
                self.worker.stop()
            info(self, f"All students of {code} are done ✓")

    def skip(self):
        if not self.worker or not self._sid:
            return
        current = self._sid
        self.worker.skip()
        self._select_next(current)

    def on_stopped(self, message: str):
        self.worker = None
        self.start_btn.setText("Start camera   (Space)")
        for w in (self.class_box, self.camera_box, self.refresh_cams, self.retake_btn):
            w.setEnabled(True)
        self.bar.setValue(0)
        code = self.class_box.currentText()
        self.refresh_students()
        if code:
            self.ctx.photos_changed.emit(code)
        self.view.clear()
        if message not in ("Camera stopped",):
            error(self, message)

    def retake(self):
        code, student = self._student()
        if student and confirm(self, f"Delete all photos of {student.name} and take them again?"):
            self.ctx.school.clear_photos(code, student)
            self.refresh_students()
            self.ctx.photos_changed.emit(code)

    def shutdown(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait(3000)
        if self.probe:
            self.probe.wait(3000)

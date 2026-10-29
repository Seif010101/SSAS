"""Camera I/O for the Capture tab. The decisions are made by ``core.student_capture.StudentCapture``."""

from __future__ import annotations

import sys
import threading
import time
from functools import partial
from pathlib import Path

import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from ...core.capture_logic import RING_SEGMENTS, CaptureSession
from ...core.landmarks import eye_openness, head_pose
from ...core.quality import check_face, crop_for_storage
from ...core.student_capture import AutoStart, FrameResult, Measurement, StudentCapture
from ...logs import get_logger
from ..context import AppContext

log = get_logger("capture")

PROBE_CAMERAS = 4  # camera numbers 0..3 are tried
FACE_CENTRE_TOLERANCE = (0.22, 0.25)  # how far from the middle of the picture the face may be (x, y)


def camera_backend() -> int:
    return cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


class CameraProbe(QThread):
    """Finds the cameras that open. Runs in the background because it can take a second or two."""

    found = Signal(list)  # [(camera number, label)]

    def run(self) -> None:
        cameras = []
        for i in range(PROBE_CAMERAS):
            cap = cv2.VideoCapture(i, camera_backend())
            if cap.isOpened():
                size = f"{int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))}×{int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))}"
                cameras.append((i, f"Camera {i}  ({size})"))
            cap.release()
        self.found.emit(cameras)


def new_session(settings) -> CaptureSession:
    """A fresh capture session for one student, sized from the "photos per student" setting."""
    n = settings.photos_per_student
    per_part = max(1, (n - 8) // RING_SEGMENTS)
    return CaptureSession(
        photos_per_segment=per_part,
        front_photos=max(4, n - per_part * RING_SEGMENTS),
        strict_order=settings.strict_order,
    )


class CameraWorker(QThread):
    """Reads the camera, asks ``StudentCapture`` what to do with every frame, saves the photos it asks for.

    The tab tells it whose turn it is with ``set_student``. Nothing here touches widgets: results go out as signals.
    """

    frame = Signal(QImage, object, list)  # mirrored picture, FrameResult, face boxes in picture coordinates
    student_done = Signal(str)  # student id
    stopped = Signal(str)  # why the camera stopped (emitted last)

    def __init__(self, ctx: AppContext, camera_index: int):
        super().__init__()
        self.ctx = ctx
        self.camera_index = camera_index
        self._running = True
        self._lock = threading.Lock()
        self._student: tuple[str, str, Path] | None = None  # id, name, photo folder
        self._skip = False

    # ----- called from the window -----
    def stop(self) -> None:
        self._running = False

    def set_student(self, student_id: str | None, name: str = "", folder: Path | None = None) -> None:
        with self._lock:
            self._student = (student_id, name, folder) if student_id else None

    def skip(self) -> None:
        self._skip = True

    # ----- the camera loop -----
    def run(self) -> None:
        reason = "Camera stopped"
        try:
            reason = self._loop() or reason
        except Exception as e:
            log.exception("The capture loop failed")
            reason = f"The camera stopped because of an error: {e}"
        finally:
            self.stopped.emit(reason)

    def _loop(self) -> str | None:
        try:
            engine = self.ctx.engine()
        except Exception as e:
            log.exception("Could not load the face models")
            return f"Could not load the face models: {e}"
        cap = cv2.VideoCapture(self.camera_index, camera_backend())
        if not cap.isOpened():
            return f"Camera {self.camera_index} could not be opened. Choose another camera."
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        settings = self.ctx.school.settings
        capture = StudentCapture(lambda: new_session(settings), auto_start=AutoStart())
        current_id = None
        try:
            while self._running:
                ok, img = cap.read()
                if not ok or img is None:
                    return "The camera stopped sending pictures."
                with self._lock:
                    student = self._student
                if student is None or student[0] != current_id:
                    current_id = student[0] if student else None
                    capture.set_student(student[1] if student else None)
                if self._skip:
                    self._skip = False
                    capture.skip()

                faces = engine.detect(img)
                main = faces[0] if faces else None
                result = capture.step(
                    [f.width for f in faces], time.monotonic(), partial(self._measure, engine, img, main)
                )
                if result.save_as and main is not None:
                    self._save_photo(student[2] / result.save_as, img, main)
                self._emit_frame(img, result, faces)
                if result.student_done:
                    done_id, current_id = current_id, None
                    self.set_student(None)  # the tab picks the next student
                    self.student_done.emit(done_id)
        finally:
            cap.release()
        return None

    @staticmethod
    def _measure(engine, img, face) -> Measurement:
        if face is None:
            return Measurement(None, None, None, None)
        yaw, pitch = head_pose(face.kps)
        openness = eye_openness(engine.landmarks.predict(img, face.box)) if engine.landmarks is not None else None
        problem = check_face(img, face.box)
        if problem is None:
            h, w = img.shape[:2]
            cx, cy = (face.box[0] + face.box[2]) / 2 / w, (face.box[1] + face.box[3]) / 2 / h
            if abs(cx - 0.5) > FACE_CENTRE_TOLERANCE[0] or abs(cy - 0.5) > FACE_CENTRE_TOLERANCE[1]:
                problem = "Move your face into the circle"
        return Measurement(yaw, pitch, openness, problem)

    @staticmethod
    def _save_photo(path: Path, img, face) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        ok, encoded = cv2.imencode(".jpg", crop_for_storage(img, face.box), [cv2.IMWRITE_JPEG_QUALITY, 92])
        if ok:
            encoded.tofile(str(path))  # works with Arabic folder names on Windows

    def _emit_frame(self, img, result: FrameResult, faces) -> None:
        mirrored = cv2.flip(img, 1)  # like a mirror, so students can steer by what they see
        h, w = mirrored.shape[:2]
        rgb = cv2.cvtColor(mirrored, cv2.COLOR_BGR2RGB)
        picture = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        boxes = [[w - f.box[2], f.box[1], w - f.box[0], f.box[3]] for f in faces]
        self.frame.emit(picture, result, boxes)

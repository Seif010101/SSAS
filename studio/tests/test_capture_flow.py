"""Runs the real capture tab with a fake camera: auto-start, saving, auto-advance, finishing the class."""

import os
import time

import cv2
import numpy as np
import pytest

from conftest import needs_face_models

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PERSON_FRAMES = 85  # frames with a person in front of the camera, then a gap while the next one steps in
GAP_FRAMES = 8


class FakeCamera:
    """Serves a face picture, with the head pose and blink scripted by the frame number."""

    pose = (0.0, 0.0)
    openness = 0.3

    def __init__(self, frame):
        self.person = frame
        self.empty = np.zeros_like(frame)
        self.n = 0

    def isOpened(self):
        return True

    def set(self, *_):
        return True

    def get(self, *_):
        return 0

    def release(self):
        pass

    def read(self):
        from ssas_studio.core.capture_logic import CaptureSession

        f = self.n % (PERSON_FRAMES + GAP_FRAMES)
        self.n += 1
        time.sleep(0.005)
        if f >= PERSON_FRAMES:
            FakeCamera.pose, FakeCamera.openness = (0.0, 0.0), 0.3
            return True, self.empty.copy()
        if f < 20:
            FakeCamera.pose = (0.0, 0.0)  # looking straight
        elif f < 20 + 8 * 5:
            seg = (f - 20) // 5  # turning round the circle, 5 frames per part
            dy, dp = CaptureSession.segment_vector(seg)
            FakeCamera.pose = (-dy, dp)
        else:
            FakeCamera.pose = (0.0, 0.0)
        FakeCamera.openness = 0.05 if 70 <= f < 73 else 0.3  # one blink at the end
        return True, self.person.copy()


@needs_face_models
@pytest.mark.parametrize("strict", [False])
def test_capture_a_class_hands_free(tmp_path, models_dir, astronaut_bgr, monkeypatch, strict):
    from PySide6.QtWidgets import QApplication

    from ssas_studio.core.capture_logic import AutoStart
    from ssas_studio.ui import capture_tab as ct
    from ssas_studio.ui.context import AppContext

    app = QApplication.instance() or QApplication([])
    from ssas_studio.core.pipeline import FaceEngine

    # A 960x540 picture with the astronaut's face in the middle (the capture asks for a centred face).
    box = FaceEngine(models_dir, prefer_gpu=False).detect(astronaut_bgr)[0].box
    k = 190.0 / (box[2] - box[0])
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    m = np.float32([[k, 0, 480 - k * cx], [0, k, 270 - k * cy]])
    canvas = cv2.warpAffine(astronaut_bgr, m, (960, 540), borderMode=cv2.BORDER_REPLICATE)

    monkeypatch.setattr(ct.cv2, "VideoCapture", lambda *a, **k: FakeCamera(canvas))
    monkeypatch.setattr(ct, "head_pose", lambda kps: FakeCamera.pose)
    monkeypatch.setattr(ct, "eye_openness", lambda pts: FakeCamera.openness)
    monkeypatch.setattr(ct, "check_face", lambda img, box: None)
    monkeypatch.setattr(ct, "SAVE_INTERVAL_S", 0.0)
    monkeypatch.setattr(ct, "DONE_SHOWN_S", 0.2)
    monkeypatch.setattr(ct, "AutoStart", lambda: AutoStart(hold_s=0.15, absent_s=0.1))
    monkeypatch.setattr(ct.QApplication, "beep", staticmethod(lambda: None))
    messages = []
    monkeypatch.setattr(ct, "info", lambda parent, m: messages.append(m))
    monkeypatch.setattr(ct, "error", lambda parent, m: messages.append("ERROR " + m))

    ctx = AppContext(data_dir=tmp_path / "data", models_dir=models_dir)
    st = ctx.school.settings
    st.strict_order = strict
    ctx.school.settings = st
    ctx.school.add_class("9A1", 9, "Advanced", 1)
    names = ["Ahmed Ali", "أحمد محمد"]
    for n in names:
        ctx.school.add_student("9A1", n)

    tab = ct.CaptureTab(ctx)
    tab._probed = True  # do not probe real cameras
    tab.camera_box.clear()
    tab.camera_box.addItem("fake", 0)
    tab.show()
    assert tab.list.count() == 2 and tab._sid is not None

    tab.toggle()
    deadline = time.time() + 240
    while tab.worker is not None and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert tab.worker is None, f"the capture did not finish: {messages}"
    app.processEvents()

    assert not [m for m in messages if m.startswith("ERROR")], messages
    assert any("done" in m for m in messages), messages
    school = ctx.school
    for s in school.load_class("9A1").students:
        photos = school.photos("9A1", s)
        assert len(photos) == 40, (s.name, len(photos))
        assert all(p.parent == school.student_dir("9A1", s) for p in photos)
    assert tab.class_label.text().startswith("2 of 2")
    tab.shutdown()

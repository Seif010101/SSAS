"""The Live demo: the screen's decision rules in Python, recognition with the real models, and the tab itself."""

import json
import time

import numpy as np
import pytest
from conftest import needs_face_models

from ssas_studio.core import groupmodel
from ssas_studio.core.attendance import AttendanceAggregator, FrameObservation, frame_health
from ssas_studio.core.live import GroupMatcher, analyse


def frame(*ids, strong=False, unknown=0, bodies=-1, faces=None):
    return FrameObservation(
        True, dict.fromkeys(ids, strong), unknown, bodies, len(ids) + unknown if faces is None else faces
    )


# ----- the same cases as board-app/core/src/test/.../AttendanceTest.kt -----
def test_present_needs_two_frames_or_one_strong():
    a = AttendanceAggregator(3)
    for f in (frame(0), frame(0, 1), frame(2, strong=True), frame()):
        a.add(f)
    assert a.result().statuses == ["present", "absent", "present"]


def test_absent_only_when_nobody_is_unexplained():
    a = AttendanceAggregator(3)
    for _ in range(4):
        a.add(frame(0, 1, unknown=1))
    assert a.result().statuses == ["present", "present", "needs_review"]


def test_a_sleeping_recognised_person_explains_a_faceless_body():
    a = AttendanceAggregator(3)
    a.add(frame(0, 1, bodies=2, faces=2))
    a.add(frame(0, 1, bodies=2, faces=2))
    for _ in range(3):
        a.add(frame(0, bodies=2, faces=1))
    assert a.result().statuses == ["present", "present", "absent"]


def test_too_few_good_frames_or_none_at_all():
    a = AttendanceAggregator(2, min_valid_frames=3)
    a.add(frame(0, strong=True))
    a.add(FrameObservation(valid=False))
    assert a.result().statuses == ["present", "needs_review"]
    b = AttendanceAggregator(2)
    b.add(FrameObservation(valid=False))
    assert b.result().statuses == ["no_data", "no_data"]


def test_early_stop_when_everyone_is_present():
    a = AttendanceAggregator(2)
    a.add(frame(0, 1, strong=True))
    assert a.all_present()


def test_frame_health():
    rng = np.random.default_rng(0)
    room = rng.integers(0, 255, (480, 640, 3), dtype=np.uint8)
    ok, reason, sig = frame_health(room)
    assert ok and reason is None
    assert frame_health(room, sig)[1] == "frozen picture"
    assert not frame_health(np.zeros((480, 640, 3), np.uint8))[0]
    assert frame_health(np.full((480, 640, 3), 200, np.uint8))[1].startswith("uniform")


def _model(embeddings, names, thresholds=None):
    people = [{"id": f"G-00{i + 1}", "name": n} for i, n in enumerate(names)]
    return groupmodel.build(
        "G",
        people,
        np.asarray(embeddings, np.float32),
        thresholds or {"accept": 0.3, "strong": 0.6, "margin": 0.05},
        {},
        "prototype",
        {},
        "now",
        "test",
    )


def test_matcher_follows_the_screen_rule():
    m = GroupMatcher(_model(np.eye(2, 512), ["A", "B"]))
    e = np.zeros((3, 512), np.float32)
    e[0, 0] = 1.0  # exactly A, strong
    e[1, 0], e[1, 1] = 0.4, 0.38  # A wins but by less than the margin: unknown
    e[2, 1] = 0.45  # B, accepted but not strong
    assert m.match(e) == [(0, 1.0, True), (None, pytest.approx(0.4), False), (1, pytest.approx(0.45), False)]


@needs_face_models
def test_analyse_recognises_faces_with_the_real_models(models_dir, astronaut_bgr, cameraman_bgr):
    from ssas_studio.core.align import norm_crop
    from ssas_studio.core.pipeline import FaceEngine

    engine = FaceEngine(models_dir, prefer_gpu=False, with_landmarks=False)
    embs = [
        engine.embedder.embed([norm_crop(img, engine.detect(img)[0].kps)])[0] for img in (astronaut_bgr, cameraman_bgr)
    ]
    matcher = GroupMatcher(_model(embs, ["seif", "eyad"]))
    obs, scores, seen = analyse(engine, matcher, astronaut_bgr)
    assert obs.valid and set(obs.recognised) == {0} and obs.unknown_faces == 0
    assert [s.name for s in seen] == ["seif"] and scores[0] > 0.9


@needs_face_models
def test_the_live_demo_tab_takes_attendance_like_a_screen(
    tmp_path, models_dir, astronaut_bgr, cameraman_bgr, monkeypatch
):
    from PySide6.QtWidgets import QApplication

    from ssas_studio.core.align import norm_crop
    from ssas_studio.core.pipeline import FaceEngine
    from ssas_studio.ui import demo_tab
    from ssas_studio.ui.context import AppContext

    app = QApplication.instance() or QApplication([])

    class FakeCamera:
        """The astronaut in front of the camera, with a little sensor noise like a real webcam."""

        def __init__(self, *args, **kwargs):
            self.rng = np.random.default_rng(1)

        def isOpened(self):
            return True

        def set(self, *args):
            return True

        def read(self):
            time.sleep(0.01)
            noise = self.rng.integers(-3, 4, astronaut_bgr.shape)
            return True, np.clip(astronaut_bgr.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        def release(self):
            pass

    monkeypatch.setattr(demo_tab.cv2, "VideoCapture", FakeCamera)
    monkeypatch.setattr(demo_tab, "DEMO_SHOTS_S", [0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35])
    errors = []
    monkeypatch.setattr(demo_tab, "error", lambda parent, m: errors.append(m))

    ctx = AppContext(data_dir=tmp_path / "data", models_dir=models_dir)
    ctx.org.add_group("9A3")
    engine = FaceEngine(models_dir, prefer_gpu=False, with_landmarks=False)
    embs = [
        engine.embedder.embed([norm_crop(img, engine.detect(img)[0].kps)])[0] for img in (astronaut_bgr, cameraman_bgr)
    ]
    model = _model(embs, ["seif", "eyad"])
    model["group_code"] = "9A3"
    groupmodel.write(ctx.org.model_dir("9A3") / groupmodel.FILE_NAME, model)

    tab = demo_tab.DemoTab(ctx)
    tab.group_box.setCurrentText("9A3")
    tab.toggle()
    assert tab.worker is not None, errors

    def wait(cond, seconds=60):
        end = time.time() + seconds
        while time.time() < end and not cond():
            app.processEvents()
            time.sleep(0.01)
        return cond()

    assert wait(lambda: tab.view.image is not None and tab.view.faces), errors
    assert tab.view.faces[0][1] == "seif" and tab.view.faces[0][2]  # the name is drawn on the face
    tab.take_attendance()
    assert wait(lambda: tab.table.rowCount() == 2), errors
    statuses = {tab.table.item(r, 0).text(): tab.table.item(r, 1).text() for r in range(2)}
    assert statuses == {"seif": "Present ✓", "eyad": "Absent"}
    payload = json.loads(tab.payload.toPlainText())
    assert payload["format"] == "ssas.result" and payload["group_code"] == "9A3"
    assert [p["status"] for p in payload["people"]] == ["present", "absent"]
    assert len(tab.payload.toPlainText()) < 5000  # text only: no picture in it
    tab.toggle()  # stop
    assert wait(lambda: tab.worker is None), errors
    assert not errors

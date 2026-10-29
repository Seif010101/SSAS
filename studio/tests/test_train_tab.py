"""The Train and Export tabs, driven like a user would (one class, two students)."""

import os
import threading
import time

import cv2
import numpy as np
import pytest
from conftest import needs_face_models

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _variants(img, n, rng):
    """Different 'photos' of one person: shifted, scaled, re-lit."""
    h, w = img.shape[:2]
    out = []
    for _ in range(n):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), rng.uniform(-6, 6), rng.uniform(0.9, 1.1))
        m[:, 2] += rng.uniform(-15, 15, 2)
        v = cv2.warpAffine(img, m, (w, h), borderMode=cv2.BORDER_REPLICATE)
        out.append(np.clip(v.astype(np.float32) * rng.uniform(0.8, 1.2), 0, 255).astype(np.uint8))
    return out


def _wait(app, cond, seconds=120):
    end = time.time() + seconds
    while not cond() and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    return cond()


@pytest.fixture
def app():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def ctx(tmp_path, models_dir):
    from ssas_studio.ui.context import AppContext

    c = AppContext(data_dir=tmp_path / "data", models_dir=models_dir)
    st = c.school.settings
    st.epochs, st.folds, st.seeds, st.augment_per_photo = 5, 3, 1, 2
    c.school.settings = st
    return c


def _add_class(ctx, code, people):
    """people: {name: image}. Writes 8 photos per student into the class folder."""
    rng = np.random.default_rng(0)
    ctx.school.add_class(code, 9, "Advanced", 3)
    for name, img in people.items():
        student = ctx.school.add_student(code, name)
        for i, v in enumerate(_variants(img, 8, rng)):
            cv2.imencode(".jpg", v)[1].tofile(str(ctx.school.student_dir(code, student) / f"p{i}.jpg"))


@needs_face_models
def test_train_tab_lists_students_trains_and_unblocks_export(app, ctx, astronaut_bgr, cameraman_bgr, monkeypatch):
    from PySide6.QtCore import Qt

    from ssas_studio.ui import train_tab
    from ssas_studio.ui.export_tab import ExportTab
    from ssas_studio.ui.train_tab import TrainTab

    messages = []
    monkeypatch.setattr(train_tab, "error", lambda parent, m: messages.append(m))
    _add_class(ctx, "9A3", {"seif": astronaut_bgr, "eyad": cameraman_bgr})

    tab = TrainTab(ctx)
    export = ExportTab(ctx)
    # The names are visible before any training.
    assert [tab.table.item(r, 0).text() for r in range(tab.table.rowCount())] == ["seif", "eyad"]
    assert "not trained" in tab.summary.text().lower()
    assert "9A3" in export.board_list.item(0).text() and "not trained" in export.board_list.item(0).text()

    # Every screen update happens on the GUI thread, whatever thread the job runs on.
    seen = []
    original = tab.show_report
    monkeypatch.setattr(tab, "show_report", lambda code: (seen.append(threading.current_thread()), original(code))[1])

    tab.start(["9A3"])
    assert _wait(app, lambda: tab.job is None and ctx.school.report("9A3") is not None), messages
    assert not messages
    assert seen and all(t is threading.main_thread() for t in seen)
    assert (ctx.school.model_dir("9A3") / "class-model.json").exists()
    assert [tab.table.item(r, 0).text() for r in range(tab.table.rowCount())] == ["seif", "eyad"]
    assert tab.table.item(0, 2).text().endswith("%")
    assert tab.train_btn.isEnabled() and not tab.stop_btn.isEnabled()
    assert "not trained" not in export.board_list.item(0).text()

    # Export the trained board to a "USB stick" through the Export tab.
    from ssas_studio.ui import export_tab

    notes = []
    monkeypatch.setattr(export_tab, "info", lambda parent, m: notes.append(m))
    monkeypatch.setattr(export_tab, "error", lambda parent, m: notes.append("ERROR " + m))
    monkeypatch.setattr(export_tab, "open_folder", lambda path: None)
    usb = ctx.data_dir.parent / "usb"
    usb.mkdir()
    export.drive_box.insertItem(0, str(usb), str(usb))
    export.drive_box.setCurrentIndex(0)
    assert export.board_list.item(0).checkState() == Qt.Checked  # ticked now that it is trained
    export.export()
    assert _wait(app, lambda: export.job is None), notes
    assert notes and not notes[0].startswith("ERROR"), notes
    board = usb / "SSAS-USB" / "screens" / "9A3"
    assert (board / "board.json").exists() and (board / "class-9A3.json").exists()


@needs_face_models
def test_train_tab_explains_when_a_class_cannot_be_trained(app, ctx, astronaut_bgr, monkeypatch):
    from ssas_studio.ui import train_tab
    from ssas_studio.ui.train_tab import TrainTab

    messages = []
    monkeypatch.setattr(train_tab, "error", lambda parent, m: messages.append(m))
    _add_class(ctx, "9A3", {"seif": astronaut_bgr})
    ctx.school.add_student("9A3", "eyad")  # no photos

    tab = TrainTab(ctx)
    assert [tab.table.item(r, 0).text() for r in range(tab.table.rowCount())] == ["seif", "eyad"]
    tab.start(["9A3"])
    assert messages and "two students" in messages[0].lower()
    assert tab.job is None and tab.train_btn.isEnabled()

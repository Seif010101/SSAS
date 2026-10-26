import json

import numpy as np
import pytest

from ssas_studio.core import classmodel
from ssas_studio.core.export import board_plans, export_usb
from ssas_studio.core.storage import School, import_students, safe_folder_name


def test_school_classes_students(tmp_path):
    s = School(tmp_path)
    s.add_class("9A1", 9, "Advanced", 1, "Room 12")
    with pytest.raises(ValueError):
        s.add_class("9A1", 9, "Advanced", 1)
    a = s.add_student("9A1", "أحمد  محمد")
    b = s.add_student("9A1", "Omar Ali")
    assert a.id == "9A1-001" and b.id == "9A1-002"
    assert a.name == "أحمد محمد"
    assert (tmp_path / "screens" / "9A1" / "أحمد محمد").is_dir()
    s.remove_student("9A1", a.id)
    assert [x.name for x in s.load_class("9A1").students] == ["Omar Ali"]
    assert s.add_student("9A1", "Zed").id == "9A1-003"  # ids are never reused


def test_board_tokens_are_kept_until_replaced(tmp_path):
    s = School(tmp_path)
    t = s.board_token("9A1")
    assert School(tmp_path).board_token("9A1") == t
    s.new_board_token("9A1")
    assert School(tmp_path).board_token("9A1") != t


def test_safe_folder_names():
    assert safe_folder_name('a/b:c*?"') == "a_b_c___"
    assert safe_folder_name("model") == "_model"
    assert safe_folder_name("  محمد   علي ") == "محمد علي"


def test_import_students_csv_and_xlsx(tmp_path):
    csv = tmp_path / "s.csv"
    csv.write_text("Name\nAhmed Ali\n\nمحمد سامي\nAhmed Ali\n", encoding="utf-8")
    assert import_students(csv) == ["Ahmed Ali", "محمد سامي"]
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in (["اسم الطالب"], ["Sara"], ["Omar"]):
        ws.append(row)
    x = tmp_path / "s.xlsx"
    wb.save(x)
    assert import_students(x) == ["Sara", "Omar"]


def _fake_model(school, code):
    c = school.load_class(code)
    students = [{"id": s.id, "name": s.name} for s in c.students]
    w = np.eye(len(students), 512, dtype=np.float32)
    m = classmodel.build(code, students, w, {"accept": 0.3, "strong": 0.5, "margin": 0.05}, {}, "head",
                         {"detector": {"file": "det_10g.onnx", "sha256": "x"}}, "now", "test")
    classmodel.write(school.model_dir(code) / "class-model.json", m)


def test_board_plans_with_labs_and_pe(tmp_path):
    s = School(tmp_path)
    s.add_class("9A1", 9, "Advanced", 1)
    s.add_class("9A2", 9, "Advanced", 2)
    s.add_lab("LAB1", "Science lab")
    c = s.load_class("9A1")
    c.timetable = {"1": {"1": "skip", "2": "LAB1"}}
    s.save_class(c)
    plans, problems = board_plans(s)
    assert not problems
    days = len(s.school_days)
    n_periods = len(s.class_periods())
    assert len(plans["9A1"].slots) == days * n_periods - 2
    assert plans["LAB1"].slots == [{"day": 1, "period": 2, "class_code": "9A1"}]
    assert plans["LAB1"].classes == {"9A1"}
    # Two classes in the same lab at the same time is reported.
    c2 = s.load_class("9A2")
    c2.timetable = {"1": {"2": "LAB1"}}
    s.save_class(c2)
    _, problems = board_plans(s)
    assert any("LAB1" in p for p in problems)


def test_export_usb_layout(tmp_path):
    s = School(tmp_path / "data")
    s.add_class("9A1", 9, "Advanced", 1)
    s.add_student("9A1", "Ahmed")
    s.add_student("9A1", "Omar")
    _fake_model(s, "9A1")
    models = tmp_path / "models"
    models.mkdir()
    (models / "det_10g.onnx").write_bytes(b"det")
    (models / "w600k_r50.onnx").write_bytes(b"emb")
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"apk")

    with pytest.raises(ValueError):
        export_usb(s, tmp_path / "usb", ["9A2"], models, apk)

    out = export_usb(s, tmp_path / "usb", ["9A1"], models, apk)
    root = tmp_path / "usb" / "SSAS-USB"
    assert out["folder"] == str(root)
    assert (root / "ssas-board.apk").read_bytes() == b"apk"
    assert (root / "models" / "det_10g.onnx").exists()
    board = json.loads((root / "screens" / "9A1" / "board.json").read_text(encoding="utf-8"))
    assert board["board_code"] == "9A1" and board["kind"] == "class"
    assert board["classes"][0]["file"] == "class-9A1.json"
    assert board["server"]["token"]
    assert board["capture"]["offset_min"] == 3.0
    m = classmodel.read(root / "screens" / "9A1" / "class-9A1.json")
    assert [x["name"] for x in m["students"]] == ["Ahmed", "Omar"]
    srv = json.loads((root / "server" / "boards.json").read_text(encoding="utf-8"))
    assert srv["boards"][0]["board_code"] == "9A1"
    assert board["server"]["token"] not in json.dumps(srv)  # only the hash goes to the server file
    # No photos are ever copied to the USB.
    assert not list(root.rglob("*.jpg"))

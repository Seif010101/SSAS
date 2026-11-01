import json

import numpy as np
import pytest

from ssas_studio.core import groupmodel
from ssas_studio.core.export import board_plans, check_ready, export_usb
from ssas_studio.core.storage import Organisation, import_people, safe_folder_name, valid_pin


def test_groups_and_people(tmp_path):
    org = Organisation(tmp_path)
    org.add_group("9A1", "Grade 9 Advanced 1", "Room 12")
    with pytest.raises(ValueError):
        org.add_group("9A1")
    with pytest.raises(ValueError):
        org.add_group("../x")
    a = org.add_person("9A1", "أحمد  محمد")
    b = org.add_person("9A1", "Omar Ali")
    assert a.id == "9A1-001" and b.id == "9A1-002"
    assert a.name == "أحمد محمد"
    assert (tmp_path / "groups" / "9A1" / "أحمد محمد").is_dir()
    org.remove_person("9A1", a.id)
    assert [x.name for x in org.load_group("9A1").people] == ["Omar Ali"]
    assert org.add_person("9A1", "Zed").id == "9A1-003"  # ids are never reused
    g = org.load_group("9A1")
    assert (g.name, g.room, g.label) == ("Grade 9 Advanced 1", "Room 12", "9A1 · Grade 9 Advanced 1")
    assert org.add_group("TEAM-A").label == "TEAM-A"


def test_board_tokens_are_kept_until_replaced(tmp_path):
    org = Organisation(tmp_path)
    t = org.board_token("9A1")
    assert Organisation(tmp_path).board_token("9A1") == t
    org.new_board_token("9A1")
    assert Organisation(tmp_path).board_token("9A1") != t


def test_safe_folder_names_and_pins():
    assert safe_folder_name('a/b:c*?"') == "a_b_c___"
    assert safe_folder_name("model") == "_model"
    assert safe_folder_name("  محمد   علي ") == "محمد علي"
    assert valid_pin("493817") and not valid_pin("2468") and not valid_pin("12345a") and not valid_pin("")


def test_import_people_csv_and_xlsx(tmp_path):
    csv = tmp_path / "s.csv"
    csv.write_text("Name\nAhmed Ali\n\nمحمد سامي\nAhmed Ali\n", encoding="utf-8")
    assert import_people(csv) == ["Ahmed Ali", "محمد سامي"]
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in (["الاسم"], ["Sara"], ["Omar"]):
        ws.append(row)
    x = tmp_path / "s.xlsx"
    wb.save(x)
    assert import_people(x) == ["Sara", "Omar"]


def _fake_model(org, code):
    g = org.load_group(code)
    people = [{"id": p.id, "name": p.name} for p in g.people]
    w = np.eye(len(people), 512, dtype=np.float32)
    m = groupmodel.build(
        code,
        people,
        w,
        {"accept": 0.3, "strong": 0.5, "margin": 0.05},
        {},
        "head",
        {"detector": {"file": "det_10g.onnx", "sha256": "x"}},
        "now",
        "test",
    )
    groupmodel.write(org.model_dir(code) / groupmodel.FILE_NAME, m)


def test_board_plans_with_shared_rooms_and_skipped_sessions(tmp_path):
    org = Organisation(tmp_path)
    org.add_group("9A1")
    org.add_group("9A2")
    org.add_shared_room("LAB1", "Science lab")
    g = org.load_group("9A1")
    g.timetable = {"1": {"1": "skip", "2": "LAB1"}}
    org.save_group(g)
    plans, problems = board_plans(org)
    assert not problems
    days = len(org.days)
    n_sessions = len(org.attendance_sessions())
    assert len(plans["9A1"].slots) == days * n_sessions - 2
    assert plans["LAB1"].slots == [{"day": 1, "session": 2, "group_code": "9A1"}]
    assert plans["LAB1"].groups == {"9A1"} and plans["LAB1"].kind == "shared"
    # Two groups in the same shared room at the same time is reported.
    g2 = org.load_group("9A2")
    g2.timetable = {"1": {"2": "LAB1"}}
    org.save_group(g2)
    _, problems = board_plans(org)
    assert any("LAB1" in p for p in problems)


def test_export_needs_a_pin_and_an_https_server(tmp_path):
    org = Organisation(tmp_path)
    org.add_group("9A1")
    assert any("PIN" in r for r in check_ready(org, ["9A1"]))
    st = org.settings
    st.board_admin_pin, st.server_url = "493817", "http://192.168.1.10"
    org.settings = st
    reasons = check_ready(org, ["9A1"])
    assert any("https://" in r for r in reasons) and any("no trained model" in r for r in reasons)


def test_export_usb_layout(tmp_path):
    org = Organisation(tmp_path / "data")
    org.add_group("9A1")
    org.add_person("9A1", "Ahmed")
    org.add_person("9A1", "Omar")
    _fake_model(org, "9A1")
    st = org.settings
    st.board_admin_pin = "493817"
    org.settings = st
    models = tmp_path / "models"
    models.mkdir()
    (models / "det_10g.onnx").write_bytes(b"det")
    (models / "w600k_r50.onnx").write_bytes(b"emb")
    apk = tmp_path / "app.apk"
    apk.write_bytes(b"apk")

    with pytest.raises(ValueError):
        export_usb(org, tmp_path / "usb", ["9A2"], models, apk)

    out = export_usb(org, tmp_path / "usb", ["9A1"], models, apk)
    root = tmp_path / "usb" / "SSAS-USB"
    assert out["folder"] == str(root)
    assert (root / "ssas-board.apk").read_bytes() == b"apk"
    assert (root / "models" / "det_10g.onnx").exists()
    board = json.loads((root / "screens" / "9A1" / "board.json").read_text(encoding="utf-8"))
    assert (board["format"], board["version"], board["board_code"], board["kind"]) == ("ssas.board", 2, "9A1", "group")
    assert board["groups"][0]["file"] == "group-9A1.json" and board["groups"][0]["people"] == 2
    assert board["slots"][0] == {"day": 1, "session": 1, "group_code": "9A1"}
    assert all(s["kind"] in ("session", "break", "other") for s in board["sessions"])
    assert board["server"]["token"]
    assert board["capture"]["offset_min"] == 3.0
    m = groupmodel.read(root / "screens" / "9A1" / "group-9A1.json")
    assert [x["name"] for x in m["people"]] == ["Ahmed", "Omar"]
    srv = json.loads((root / "server" / "boards.json").read_text(encoding="utf-8"))
    assert srv["version"] == 2 and srv["boards"][0]["board_code"] == "9A1"
    assert srv["boards"][0]["people"]["9A1"] == [{"id": "9A1-001", "name": "Ahmed"}, {"id": "9A1-002", "name": "Omar"}]
    assert board["server"]["token"] not in json.dumps(srv)  # only the hash goes to the server file
    # No photos and no face data are ever in the server file, and no photos on the USB.
    assert "weights" not in json.dumps(srv)
    assert not list(root.rglob("*.jpg"))


def _make_v1_folder(root):
    """A data folder like Studio 0.1 left it: school words, one class (9A3) with seif and eyad and a trained model."""
    (root / "screens" / "9A3" / "seif").mkdir(parents=True)
    (root / "screens" / "9A3" / "eyad").mkdir(parents=True)
    (root / "screens" / "9A3" / "seif" / "p1.jpg").write_bytes(b"photo of seif")
    (root / "screens" / "9A3" / "eyad" / "p1.jpg").write_bytes(b"photo of eyad")
    school = {
        "format": "ssas.school",
        "version": 1,
        "school_name": "My School",
        "school_days": [1, 2, 3, 4, 5],
        "bell": [
            {"number": 1, "start": "07:30", "end": "08:15", "kind": "class"},
            {"number": 0, "start": "08:15", "end": "08:30", "kind": "break"},
            {"number": 0, "start": "08:30", "end": "09:00", "kind": "assembly"},
        ],
        "labs": [{"code": "LAB1", "name": "Lab"}],
        "settings": {"photos_per_student": 40, "board_admin_pin": "2468", "server_url": "", "settings_version": 2},
        "board_tokens": {"9A3": "secret-token"},
    }
    (root / "school.json").write_text(json.dumps(school), encoding="utf-8")
    cls = {
        "format": "ssas.class",
        "version": 1,
        "code": "9A3",
        "grade": 9,
        "track": "Advanced",
        "section": 3,
        "room": "",
        "students": [
            {"id": "9A3-001", "name": "seif", "folder": "seif"},
            {"id": "9A3-002", "name": "eyad", "folder": "eyad"},
        ],
        "timetable": {"1": {"1": "LAB1"}},
    }
    (root / "screens" / "9A3" / "class.json").write_text(json.dumps(cls), encoding="utf-8")
    model = {
        "format": "ssas.class-model",
        "version": 1,
        "class_code": "9A3",
        "created_at": "x",
        "studio_version": "0.1.3",
        "method": "head",
        "models": {},
        "students": [{"id": "9A3-001", "name": "seif"}, {"id": "9A3-002", "name": "eyad"}],
        "weights": groupmodel.encode_matrix(np.eye(2, 512, dtype=np.float32)),
        "thresholds": {"accept": 0.3, "strong": 0.5, "margin": 0.05},
        "metrics": {},
    }
    (root / "screens" / "9A3" / "model").mkdir()
    (root / "screens" / "9A3" / "model" / "class-model.json").write_text(json.dumps(model), encoding="utf-8")
    report = {
        "class_code": "9A3",
        "students": [{"id": "9A3-001", "name": "seif", "photos": 1, "recall": 1.0}],
        "weak_students": ["eyad"],
        "metrics": {"accuracy": 1.0, "wrong_student_rate": 0.0},
        "photo_problems": [{"student": "eyad", "photo": "p2.jpg", "problem": "no face found"}],
    }
    (root / "screens" / "9A3" / "model" / "report.json").write_text(json.dumps(report), encoding="utf-8")


def test_a_studio_0_1_data_folder_is_converted_once(tmp_path):
    _make_v1_folder(tmp_path)
    org = Organisation(tmp_path)
    assert org.name == "My School" and org.group_codes() == ["9A3"]
    assert [s["kind"] for s in org.sessions] == ["session", "break", "other"]
    assert org.shared_rooms == [{"code": "LAB1", "name": "Lab"}]
    g = org.load_group("9A3")
    assert [p.name for p in g.people] == ["seif", "eyad"] and g.timetable == {"1": {"1": "LAB1"}}
    # The photos are where the people are, untouched.
    assert [p.read_bytes() for p in org.photos("9A3", g.people[0])] == [b"photo of seif"]
    assert [p.read_bytes() for p in org.photos("9A3", g.people[1])] == [b"photo of eyad"]
    # The trained model keeps working, in the new format.
    m = groupmodel.read(org.model_dir("9A3") / groupmodel.FILE_NAME)
    assert m["group_code"] == "9A3" and [p["name"] for p in m["people"]] == ["seif", "eyad"]
    report = org.report("9A3")
    assert report["people"][0]["name"] == "seif" and report["weak_people"] == ["eyad"]
    assert report["metrics"]["wrong_person_rate"] == 0.0 and report["photo_problems"][0]["person"] == "eyad"
    # The old default PIN is not kept; the screen key is.
    assert org.settings.board_admin_pin == "" and org.settings.photos_per_person == 40
    assert org.board_token("9A3") == "secret-token"
    # Old files: removed, with a copy in backup-0.1.
    assert not (tmp_path / "school.json").exists() and not (tmp_path / "screens").exists()
    assert (tmp_path / "backup-0.1" / "school.json").exists() and (
        tmp_path / "backup-0.1" / "9A3" / "class.json"
    ).exists()
    # Opening again changes nothing.
    assert Organisation(tmp_path).load_group("9A3").people == g.people

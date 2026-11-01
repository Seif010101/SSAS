import hashlib
import json
import re
import sqlite3
import time

import pyotp
import pytest
from fastapi.testclient import TestClient

from ssas_server import auth
from ssas_server.config import Config, parse_networks
from ssas_server.db import Database
from ssas_server.main import create_app
from ssas_server.security import csv_cell

TOKEN = "board-token-9A1"
PEOPLE = {
    "9A1": [{"id": "9A1-001", "name": "Ahmed"}, {"id": "9A1-002", "name": "محمد"}, {"id": "9A1-003", "name": "Sara"}]
}


def result(session, statuses, group="9A1", board="9A1", day="2026-10-26"):
    return {
        "format": "ssas.result",
        "version": 2,
        "board_code": board,
        "group_code": group,
        "date": day,
        "session": session,
        "session_start": f"{day}T08:00",
        "captured_at": f"{day}T08:04",
        "frames": 3,
        "valid_frames": 3,
        "unknown_max": 0,
        "suspicious_max": 0,
        "model_created_at": "x",
        "app_version": "0.2.0",
        "people": [{"id": f"{group}-00{i + 1}", "name": n, "status": s} for i, (n, s) in enumerate(statuses)],
    }


def make(tmp_path, **cfg):
    app = create_app(Config(data_dir=tmp_path, org_name="Test Org", cookie_secure=False, **cfg))
    db = app.state.db
    secret = auth.create_admin(db, "dev@org.test", "Dev", "developer", "correct horse battery")
    sup_secret = auth.create_admin(db, "sup@org.test", "Sup", "supervisor", "supervisor password")
    db.add_board("9A1", "group", "9A1", ["9A1"], PEOPLE, hashlib.sha256(TOKEN.encode()).hexdigest())
    return TestClient(app), db, secret, sup_secret


@pytest.fixture
def ctx(tmp_path):
    return make(tmp_path)


def login(client, email, password, secret, at=None):
    code = pyotp.TOTP(secret).at(at or time.time())
    return client.post("/login", data={"email": email, "password": password, "code": code}, follow_redirects=False)


H = {"Authorization": f"Bearer {TOKEN}"}


def test_board_api_accepts_only_its_own_group_and_ignores_duplicates(ctx):
    client, db, *_ = ctx
    assert client.post("/api/v1/results", json=result(1, [("Ahmed", "present")])).status_code == 401
    assert (
        client.post(
            "/api/v1/results", json=result(1, [("Ahmed", "present")]), headers={"Authorization": "Bearer nope"}
        ).status_code
        == 401
    )
    assert client.post("/api/v1/results", json=result(1, [("Ahmed", "present")]), headers=H).status_code == 200
    assert client.post("/api/v1/results", json=result(1, [("Ahmed", "present")]), headers=H).status_code == 409
    assert client.post("/api/v1/results", json=result(2, [("X", "present")], group="9A2"), headers=H).status_code == 403
    assert client.post("/api/v1/results", json=result(3, [("Ahmed", "sleeping")]), headers=H).status_code == 400
    assert client.post("/api/v1/heartbeat", json={"armed": True, "app_version": "0.2.0"}, headers=H).status_code == 200
    assert db.one("SELECT last_seen FROM boards")["last_seen"]


def test_results_are_checked_and_names_come_from_the_registered_list(ctx):
    client, db, *_ = ctx
    old = result(1, [("Ahmed", "present")])
    old["version"] = 1
    assert client.post("/api/v1/results", json=old, headers=H).status_code == 400
    unknown = result(1, [("Ahmed", "present")])
    unknown["people"][0]["id"] = "9A1-999"
    assert client.post("/api/v1/results", json=unknown, headers=H).status_code == 403
    twice = result(1, [("Ahmed", "present")])
    twice["people"].append(dict(twice["people"][0]))
    assert client.post("/api/v1/results", json=twice, headers=H).status_code == 400
    for key, bad in (("session", "1"), ("frames", -1), ("date", "yesterday"), ("app_version", "x" * 500)):
        r = result(1, [("Ahmed", "present")])
        r[key] = bad
        assert client.post("/api/v1/results", json=r, headers=H).status_code == 400, key
    future = result(5, [("Ahmed", "present")], day="2099-01-01")
    assert client.post("/api/v1/results", json=future, headers=H).status_code == 400
    basic = result(6, [("Ahmed", "present")], day="20261026")  # another spelling of the same date
    assert client.post("/api/v1/results", json=basic, headers=H).status_code == 200
    assert client.post("/api/v1/results", json=result(6, [("Ahmed", "present")]), headers=H).status_code == 409
    db.exec("DELETE FROM results")
    renamed = result(1, [("<script>alert(1)</script>", "present"), ("=cmd|' /C calc'!A0", "absent")])
    assert client.post("/api/v1/results", json=renamed, headers=H).status_code == 200
    stored = json.loads(db.one("SELECT payload FROM results")["payload"])
    assert [p["name"] for p in stored["people"]] == ["Ahmed", "محمد"]


def test_heartbeat_keeps_only_known_fields(ctx):
    client, db, *_ = ctx
    client.post(
        "/api/v1/heartbeat", json={"armed": True, "pending": 2, "last_error": "e" * 1000, "evil": "x"}, headers=H
    )
    hb = json.loads(db.one("SELECT heartbeat FROM boards")["heartbeat"])
    assert hb == {"armed": True, "pending": 2, "last_error": "e" * 300}


def test_login_requires_password_and_fresh_totp(ctx):
    client, db, secret, _ = ctx
    assert client.get("/", follow_redirects=False).status_code == 303
    assert "Wrong" in login(client, "dev@org.test", "wrong password", secret).text
    r = client.post("/login", data={"email": "dev@org.test", "password": "correct horse battery", "code": "000000"})
    assert "Wrong" in r.text
    t = time.time()
    r = login(client, "dev@org.test", "correct horse battery", secret, at=t)
    assert r.status_code == 303 and "ssas_session" in r.cookies
    # The same code cannot be used twice.
    client2 = TestClient(client.app)
    assert "Wrong" in login(client2, "dev@org.test", "correct horse battery", secret, at=t).text


def test_lockout_after_five_failures(ctx):
    client, db, secret, _ = ctx
    for _ in range(5):
        login(client, "dev@org.test", "nope nope nope", secret)
    r = login(client, "dev@org.test", "correct horse battery", secret)
    assert "Too many attempts" in r.text


def test_too_many_sign_ins_from_one_address(ctx):
    client, *_ = ctx
    codes = [
        client.post("/login", data={"email": f"x{i}@org.test", "password": "x", "code": "1"}).status_code
        for i in range(12)
    ]
    assert codes[:10] == [200] * 10 and codes[10:] == [429, 429]


def test_pages_show_results_and_left_after_present(ctx):
    client, db, secret, sup_secret = ctx
    client.post("/api/v1/results", json=result(1, [("Ahmed", "present"), ("محمد", "present")]), headers=H)
    client.post("/api/v1/results", json=result(2, [("Ahmed", "absent"), ("محمد", "present")]), headers=H)
    login(client, "dev@org.test", "correct horse battery", secret)
    page = client.get("/?day=2026-10-26").text
    assert "Session 1" in page and "Session 2" in page
    assert 'class="badge warn">1<' in page  # Ahmed left after session 1
    detail = client.get("/group/9A1/2026-10-26/2").text
    assert "was present in session 1" in detail and "محمد" in detail
    csv_text = client.get("/export.csv?start=2026-10-26&end=2026-10-26").content.decode("utf-8-sig")
    assert csv_text.splitlines()[0] == "date,session,group,person_id,person_name,status,board,captured_at"
    assert "9A1-001,Ahmed,absent" in csv_text


def test_supervisor_is_view_only_and_csrf_is_checked(ctx):
    client, db, secret, sup_secret = ctx
    login(client, "sup@org.test", "supervisor password", sup_secret)
    assert "Upload" not in client.get("/boards").text
    files = {"file": ("boards.json", b"{}", "application/json")}
    assert client.post("/boards/import", files=files, data={"csrf": "x"}).status_code == 403

    dev = TestClient(client.app)
    login(dev, "dev@org.test", "correct horse battery", secret)
    csrf = re.search(r'name="csrf" value="([^"]+)"', dev.get("/boards").text).group(1)
    data = {
        "format": "ssas.server-boards",
        "version": 2,
        "boards": [
            {
                "board_code": "LAB1",
                "kind": "shared",
                "name": "Lab",
                "groups": ["9A1", "9A2"],
                "token_sha256": "ab" * 32,
                "people": {"9A1": PEOPLE["9A1"], "9A2": [{"id": "9A2-001", "name": "Omar"}]},
            }
        ],
    }
    files = {"file": ("boards.json", json.dumps(data).encode(), "application/json")}
    assert dev.post("/boards/import", files=files, data={"csrf": "wrong"}).status_code == 400
    r = dev.post("/boards/import", files=files, data={"csrf": csrf})
    assert r.status_code == 200 and "Imported 1 boards" in r.text
    assert db.one("SELECT kind FROM boards WHERE board_code = 'LAB1'")["kind"] == "shared"

    bad = json.loads(json.dumps(data))
    bad["boards"][0]["board_code"] = "../x"
    files = {"file": ("boards.json", json.dumps(bad).encode(), "application/json")}
    r = dev.post("/boards/import", files=files, data={"csrf": csrf})
    assert r.status_code == 400 and "Not imported" in r.text
    old = dict(data, version=1)
    files = {"file": ("boards.json", json.dumps(old).encode(), "application/json")}
    assert "older SSAS Studio" in dev.post("/boards/import", files=files, data={"csrf": csrf}).text


def test_security_headers_and_size_limits(ctx):
    client, *_ = ctx
    h = client.get("/login").headers
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"
    assert h["referrer-policy"] == "no-referrer" and h["cache-control"] == "no-store"
    assert client.post("/api/v1/heartbeat", content=b"x" * 300_000, headers=H).status_code == 413

    def chunks():
        for _ in range(40):
            yield b"x" * 10_000

    assert client.post("/api/v1/heartbeat", content=chunks(), headers=H).status_code == 413


def test_admin_pages_can_be_limited_to_some_addresses(tmp_path):
    client, *_ = make(tmp_path, admin_allow=parse_networks("10.0.0.0/8"))
    assert client.get("/login").status_code == 403  # the test client's address is not in 10.0.0.0/8
    assert client.get("/api/v1/health").status_code == 200  # the screens are not affected
    with pytest.raises(ValueError):
        parse_networks("10.0.0.0/8, not-an-address")


def test_csv_cells_cannot_be_formulas():
    assert csv_cell("=1+1") == "'=1+1" and csv_cell("@SUM(A1)") == "'@SUM(A1)" and csv_cell("-2") == "'-2"
    assert csv_cell("Ahmed") == "Ahmed" and csv_cell(3) == "3" and csv_cell(None) == ""
    assert csv_cell("＝1+1") == "'＝1+1"  # full-width equals sign


def test_database_from_0_1_is_upgraded(tmp_path):
    path = tmp_path / "ssas.sqlite3"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE boards (board_code TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, classes TEXT NOT NULL,
            students TEXT NOT NULL, token_sha256 TEXT NOT NULL, updated_at TEXT NOT NULL, last_seen TEXT, heartbeat TEXT);
        CREATE TABLE results (id INTEGER PRIMARY KEY, board_code TEXT NOT NULL, class_code TEXT NOT NULL, date TEXT NOT NULL,
            period INTEGER NOT NULL, lesson_start TEXT NOT NULL, received_at TEXT NOT NULL, payload TEXT NOT NULL,
            UNIQUE (class_code, date, period));
        CREATE INDEX results_by_date ON results (date, class_code);
    """)
    old = {
        "format": "ssas.result",
        "version": 1,
        "board_code": "LAB",
        "class_code": "9A1",
        "date": "2026-10-26",
        "period": 2,
        "lesson_start": "2026-10-26T08:00",
        "students": [{"id": "9A1-001", "name": "Ahmed", "status": "present"}],
    }
    c.execute("INSERT INTO boards VALUES ('LAB', 'lab', 'Lab', '[\"9A1\"]', '{}', 'ab', 'now', NULL, NULL)")
    c.execute("INSERT INTO results VALUES (1, 'LAB', '9A1', '2026-10-26', 2, '08:00', 'now', ?)", (json.dumps(old),))
    c.commit()
    c.close()

    db = Database(path)
    row = db.one("SELECT group_code, session, payload FROM results")
    assert (row["group_code"], row["session"]) == ("9A1", 2)
    p = json.loads(row["payload"])
    assert p["version"] == 2 and p["people"][0]["name"] == "Ahmed" and p["session"] == 2 and "students" not in p
    assert db.one("SELECT kind, groups FROM boards")["kind"] == "shared"
    Database(path)  # opening again changes nothing


def test_self_signed_certificate_and_fingerprint(tmp_path, monkeypatch):
    from ssas_server import cli
    from ssas_server.config import load

    monkeypatch.setenv("SSAS_DATA_DIR", str(tmp_path))
    cfg = load()
    cli.ensure_cert(cfg)
    fp = cli.fingerprint(cfg)
    assert len(fp) == 64
    cli.ensure_cert(cfg)  # second call keeps the same certificate
    assert cli.fingerprint(cfg) == fp


def test_settings_from_the_environment(tmp_path, monkeypatch):
    from ssas_server.config import load

    monkeypatch.setenv("SSAS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SSAS_SCHOOL_NAME", "Old name")  # 0.1 .env files keep working
    monkeypatch.setenv("SSAS_TLS", "off")
    monkeypatch.setenv("SSAS_ADMIN_ALLOW", "192.168.1.0/24")
    cfg = load()
    assert cfg.org_name == "Old name" and cfg.tls is False and cfg.behind_proxy is False
    assert [str(n) for n in cfg.admin_allow] == ["192.168.1.0/24"]
    monkeypatch.setenv("SSAS_ORG_NAME", "New name")
    assert load().org_name == "New name"

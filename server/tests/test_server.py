import hashlib
import json
import re
import time

import pyotp
import pytest
from fastapi.testclient import TestClient

from ssas_server import auth
from ssas_server.config import Config
from ssas_server.main import create_app

TOKEN = "board-token-9A1"


def result(period, statuses, cls="9A1", board="9A1", day="2026-10-26"):
    return {
        "format": "ssas.result", "version": 1, "board_code": board, "class_code": cls, "date": day, "period": period,
        "lesson_start": f"{day}T08:00", "captured_at": f"{day}T08:04", "frames": 3, "valid_frames": 3,
        "unknown_max": 0, "suspicious_max": 0, "model_created_at": "x", "app_version": "0.1.0",
        "students": [{"id": f"{cls}-00{i + 1}", "name": n, "status": s} for i, (n, s) in enumerate(statuses)],
    }


@pytest.fixture
def ctx(tmp_path):
    cfg = Config(data_dir=tmp_path, school_name="Test School", cookie_secure=False)
    app = create_app(cfg)
    db = app.state.db
    secret = auth.create_admin(db, "dev@school.test", "Dev", "developer", "correct horse battery")
    sup_secret = auth.create_admin(db, "sup@school.test", "Sup", "supervisor", "supervisor password")
    db.exec("INSERT INTO boards (board_code, kind, name, classes, students, token_sha256, updated_at) VALUES (?,?,?,?,?,?,?)",
            ("9A1", "class", "9A1", json.dumps(["9A1"]), "{}", hashlib.sha256(TOKEN.encode()).hexdigest(), "now"))
    return TestClient(app), db, secret, sup_secret


def login(client, email, password, secret, at=None):
    code = pyotp.TOTP(secret).at(at or time.time())
    return client.post("/login", data={"email": email, "password": password, "code": code}, follow_redirects=False)


def test_board_api_accepts_only_its_own_class_and_ignores_duplicates(ctx):
    client, db, *_ = ctx
    h = {"Authorization": f"Bearer {TOKEN}"}
    assert client.post("/api/v1/results", json=result(1, [("Ahmed", "present")])).status_code == 401
    assert client.post("/api/v1/results", json=result(1, [("Ahmed", "present")]), headers={"Authorization": "Bearer nope"}).status_code == 401
    r = client.post("/api/v1/results", json=result(1, [("Ahmed", "present")]), headers=h)
    assert r.status_code == 200
    assert client.post("/api/v1/results", json=result(1, [("Ahmed", "present")]), headers=h).status_code == 409
    other = result(2, [("X", "present")], cls="9A2")
    assert client.post("/api/v1/results", json=other, headers=h).status_code == 403
    bad = result(3, [("Ahmed", "sleeping")])
    assert client.post("/api/v1/results", json=bad, headers=h).status_code == 400
    assert client.post("/api/v1/heartbeat", json={"armed": True, "app_version": "0.1.0"}, headers=h).status_code == 200
    assert db.one("SELECT last_seen FROM boards")["last_seen"]


def test_login_requires_password_and_fresh_totp(ctx):
    client, db, secret, _ = ctx
    assert client.get("/", follow_redirects=False).status_code == 303
    assert "Wrong" in login(client, "dev@school.test", "wrong password", secret).text
    r = client.post("/login", data={"email": "dev@school.test", "password": "correct horse battery", "code": "000000"})
    assert "Wrong" in r.text
    t = time.time()
    r = login(client, "dev@school.test", "correct horse battery", secret, at=t)
    assert r.status_code == 303 and "ssas_session" in r.cookies
    # The same code cannot be used twice.
    client2 = TestClient(client.app)
    assert "Wrong" in login(client2, "dev@school.test", "correct horse battery", secret, at=t).text


def test_lockout_after_five_failures(ctx):
    client, db, secret, _ = ctx
    for _ in range(5):
        login(client, "dev@school.test", "nope nope nope", secret)
    r = login(client, "dev@school.test", "correct horse battery", secret)
    assert "Too many attempts" in r.text


def test_pages_show_results_and_missing_after_present(ctx):
    client, db, secret, sup_secret = ctx
    h = {"Authorization": f"Bearer {TOKEN}"}
    client.post("/api/v1/results", json=result(1, [("Ahmed", "present"), ("محمد", "present")]), headers=h)
    client.post("/api/v1/results", json=result(2, [("Ahmed", "absent"), ("محمد", "present")]), headers=h)
    login(client, "dev@school.test", "correct horse battery", secret)
    page = client.get("/?day=2026-10-26").text
    assert "Period 1" in page and "Period 2" in page
    assert 'class="badge warn">1<' in page  # Ahmed left after period 1
    detail = client.get("/class/9A1/2026-10-26/2").text
    assert "was present in period 1" in detail and "محمد" in detail
    csv_text = client.get("/export.csv?start=2026-10-26&end=2026-10-26").content.decode("utf-8-sig")
    assert "9A1-001,Ahmed,absent" in csv_text


def test_supervisor_is_view_only_and_csrf_is_checked(ctx):
    client, db, secret, sup_secret = ctx
    login(client, "sup@school.test", "supervisor password", sup_secret)
    page = client.get("/boards").text
    assert "Upload" not in page
    files = {"file": ("boards.json", b"{}", "application/json")}
    assert client.post("/boards/import", files=files, data={"csrf": "x"}).status_code == 403

    dev = TestClient(client.app)
    login(dev, "dev@school.test", "correct horse battery", secret)
    page = dev.get("/boards").text
    csrf = re.search(r'name="csrf" value="([^"]+)"', page).group(1)
    data = {"format": "ssas.server-boards", "version": 1, "boards": [
        {"board_code": "LAB1", "kind": "lab", "name": "Lab", "classes": ["9A1", "9A2"], "token_sha256": "ab", "students": {}}]}
    files = {"file": ("boards.json", json.dumps(data).encode(), "application/json")}
    assert dev.post("/boards/import", files=files, data={"csrf": "wrong"}).status_code == 400
    r = dev.post("/boards/import", files=files, data={"csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303 and "Imported+1" in r.headers["location"]
    assert db.one("SELECT kind FROM boards WHERE board_code = 'LAB1'")["kind"] == "lab"


def test_self_signed_certificate_and_fingerprint(tmp_path, monkeypatch):
    from ssas_server import cli

    monkeypatch.setenv("SSAS_DATA_DIR", str(tmp_path))
    cfg = __import__("ssas_server.config", fromlist=["load"]).load()
    cli.ensure_cert(cfg)
    fp = cli.fingerprint(cfg)
    assert len(fp) == 64
    cli.ensure_cert(cfg)  # second call keeps the same certificate
    assert cli.fingerprint(cfg) == fp

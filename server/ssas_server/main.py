"""FastAPI app: board API (token auth) and admin pages (password + TOTP)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date as Date
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import __version__, auth
from .attendance import COUNTED, counts, day_results, missing_after_present
from .config import Config, load
from .db import Database, now

HERE = Path(__file__).parent
COOKIE = "ssas_session"
STATUS_LABELS = {"present": "Present", "absent": "Absent", "needs_review": "Needs review", "no_data": "No data", "late": "Late"}


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or load()
    db = Database(cfg.db_path)
    app = FastAPI(title="SSAS server", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.db = db
    app.state.cfg = cfg
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    templates.env.globals.update(school=cfg.school_name, version=__version__, labels=STATUS_LABELS)
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    # ---------------- board API ----------------
    def board_from(request: Request):
        h = request.headers.get("authorization", "")
        if not h.lower().startswith("bearer "):
            raise HTTPException(401, "missing token")
        token_sha = hashlib.sha256(h[7:].strip().encode()).hexdigest()
        row = db.one("SELECT * FROM boards WHERE token_sha256 = ?", (token_sha,))
        if row is None:
            raise HTTPException(401, "unknown board")
        db.exec("UPDATE boards SET last_seen = ? WHERE board_code = ?", (now(), row["board_code"]))
        return row

    @app.post("/api/v1/results")
    async def post_result(request: Request):
        board = board_from(request)
        try:
            p = await request.json()
        except ValueError:
            raise HTTPException(400, "invalid JSON")
        if p.get("format") != "ssas.result" or int(p.get("version", 0)) > 1:
            raise HTTPException(400, "unsupported result format")
        for key in ("board_code", "class_code", "date", "period", "students"):
            if key not in p:
                raise HTTPException(400, f"missing {key}")
        if p["board_code"] != board["board_code"]:
            raise HTTPException(403, "result is for another board")
        if p["class_code"] not in json.loads(board["classes"]):
            raise HTTPException(403, "this board does not take attendance for that class")
        try:
            Date.fromisoformat(p["date"])
        except ValueError:
            raise HTTPException(400, "bad date")
        for s in p["students"]:
            if s.get("status") not in COUNTED:
                raise HTTPException(400, "bad status")
        exists = db.one("SELECT id FROM results WHERE class_code = ? AND date = ? AND period = ?",
                        (p["class_code"], p["date"], int(p["period"])))
        if exists:
            return JSONResponse({"ok": True, "duplicate": True}, status_code=409)
        db.exec(
            "INSERT INTO results (board_code, class_code, date, period, lesson_start, received_at, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (board["board_code"], p["class_code"], p["date"], int(p["period"]), str(p.get("lesson_start", "")),
             now(), json.dumps(p, ensure_ascii=False)),
        )
        return {"ok": True}

    @app.post("/api/v1/heartbeat")
    async def heartbeat(request: Request):
        board = board_from(request)
        try:
            body = await request.json()
        except ValueError:
            body = {}
        db.exec("UPDATE boards SET heartbeat = ? WHERE board_code = ?", (json.dumps(body)[:4000], board["board_code"]))
        return {"ok": True, "server_time": datetime.now().isoformat(timespec="seconds")}

    @app.get("/api/v1/health")
    def health():
        return {"ok": True, "version": __version__}

    # ---------------- admin pages ----------------
    def current(request: Request) -> auth.Admin | None:
        return auth.session_admin(db, request.cookies.get(COOKIE), cfg.session_idle_min, cfg.session_max_hours)

    def page(request: Request, name: str, admin: auth.Admin | None, **ctx):
        token = request.cookies.get(COOKIE)
        return templates.TemplateResponse(request, name, {"admin": admin, "csrf": auth.csrf_token(token) if token else "", **ctx})

    def need_login(request: Request) -> auth.Admin:
        admin = current(request)
        if admin is None:
            raise HTTPException(303, headers={"Location": "/login"})
        return admin

    @app.exception_handler(HTTPException)
    async def redirect_handler(request: Request, exc: HTTPException):
        if exc.status_code == 303:
            return RedirectResponse(exc.headers["Location"], status_code=303)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return page(request, "login.html", None, error=None)

    @app.post("/login")
    def login_post(request: Request, email: str = Form(...), password: str = Form(...), code: str = Form(...)):
        try:
            admin = auth.login(db, email, password, code)
        except auth.LoginError as e:
            return page(request, "login.html", None, error=str(e), email=email)
        token = auth.new_session(db, admin)
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(COOKIE, token, httponly=True, samesite="strict", secure=cfg.cookie_secure,
                        max_age=cfg.session_max_hours * 3600)
        return resp

    @app.post("/logout")
    def logout(request: Request):
        auth.end_session(db, request.cookies.get(COOKIE))
        resp = RedirectResponse("/login", status_code=303)
        resp.delete_cookie(COOKIE)
        return resp

    @app.get("/", response_class=HTMLResponse)
    def today(request: Request, day: str | None = None):
        admin = need_login(request)
        d = day or Date.today().isoformat()
        results = day_results(db, d)
        classes = sorted(set(results) | {c for b in db.q("SELECT classes FROM boards") for c in json.loads(b["classes"])})
        periods = sorted({p for r in results.values() for p in r})
        grid = {c: {p: counts(results[c][p]) for p in results.get(c, {})} for c in classes}
        flags = {c: missing_after_present(results.get(c, {})) for c in classes}
        return page(request, "today.html", admin, day=d, classes=classes, periods=periods, grid=grid, flags=flags)

    @app.get("/class/{code}/{day}/{period}", response_class=HTMLResponse)
    def period_detail(request: Request, code: str, day: str, period: int):
        admin = need_login(request)
        row = db.one("SELECT * FROM results WHERE class_code = ? AND date = ? AND period = ?", (code, day, period))
        if row is None:
            raise HTTPException(404, "no result")
        p = json.loads(row["payload"])
        flags = missing_after_present(day_results(db, day).get(code, {}))
        return page(request, "period.html", admin, p=p, code=code, day=day, period=period, flags=flags,
                    received=row["received_at"], c=counts(p))

    @app.get("/boards", response_class=HTMLResponse)
    def boards(request: Request):
        admin = need_login(request)
        rows = []
        for b in db.q("SELECT * FROM boards ORDER BY board_code"):
            hb = json.loads(b["heartbeat"]) if b["heartbeat"] else {}
            rows.append({"code": b["board_code"], "kind": b["kind"], "name": b["name"],
                         "classes": ", ".join(json.loads(b["classes"])), "last_seen": b["last_seen"], "hb": hb})
        return page(request, "boards.html", admin, rows=rows, message=request.query_params.get("msg"))

    @app.post("/boards/import")
    async def import_boards(request: Request, file: UploadFile, csrf: str = Form(...)):
        admin = need_login(request)
        if not admin.can_edit:
            raise HTTPException(403, "view-only account")
        if not auth.check_csrf(request.cookies.get(COOKIE), csrf):
            raise HTTPException(400, "form expired, reload the page")
        try:
            data = json.loads((await file.read()).decode("utf-8"))
            assert data.get("format") == "ssas.server-boards"
            n = 0
            for b in data["boards"]:
                db.exec(
                    "INSERT INTO boards (board_code, kind, name, classes, students, token_sha256, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(board_code) DO UPDATE SET kind=excluded.kind, name=excluded.name, classes=excluded.classes, "
                    "students=excluded.students, token_sha256=excluded.token_sha256, updated_at=excluded.updated_at",
                    (b["board_code"], b["kind"], b["name"], json.dumps(b["classes"]), json.dumps(b.get("students", {}), ensure_ascii=False),
                     b["token_sha256"], now()),
                )
                n += 1
        except (ValueError, KeyError, AssertionError):
            return RedirectResponse("/boards?msg=That+is+not+a+boards.json+file+from+SSAS+Studio", status_code=303)
        db.audit(admin.email, "boards.import", {"count": n})
        return RedirectResponse(f"/boards?msg=Imported+{n}+boards", status_code=303)

    @app.get("/export.csv")
    def export_csv(request: Request, start: str | None = None, end: str | None = None):
        admin = need_login(request)
        start = start or "0000-01-01"
        end = end or "9999-12-31"
        buf = io.StringIO()
        buf.write("﻿")  # so Excel opens Arabic names correctly
        w = csv.writer(buf)
        w.writerow(["date", "period", "class", "student_id", "student_name", "status", "board", "captured_at"])
        for r in db.q("SELECT payload FROM results WHERE date BETWEEN ? AND ? ORDER BY date, class_code, period", (start, end)):
            p = json.loads(r["payload"])
            for s in p["students"]:
                w.writerow([p["date"], p["period"], p["class_code"], s["id"], s["name"], s["status"], p["board_code"], p.get("captured_at", "")])
        db.audit(admin.email, "export.csv", {"start": start, "end": end})
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="ssas-attendance-{start}-{end}.csv"'})

    return app



"""The admin web pages (sign-in with password + 6-digit code).

/                                  Today: every group x session, with counts
/group/{code}/{day}/{session}      one session: everyone's status
/boards                            the screens, their last contact, and the boards.json upload
/export.csv                        all results between two dates, for Excel
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import date as Date

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from . import auth
from .attendance import counts, day_results, left_after_present
from .security import csv_cell

router = APIRouter()
COOKIE = "ssas_session"
CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,15}$")  # board and group codes, as Studio makes them
PERSON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
BOARD_KINDS = ("group", "shared")


# ---------------- helpers ----------------
def current(request: Request) -> auth.Admin | None:
    cfg = request.app.state.cfg
    return auth.session_admin(
        request.app.state.db, request.cookies.get(COOKIE), cfg.session_idle_min, cfg.session_max_hours
    )


def need_login(request: Request) -> auth.Admin:
    admin = current(request)
    if admin is None:
        raise HTTPException(303, headers={"Location": "/login"})
    return admin


def page(request: Request, name: str, admin: auth.Admin | None, status_code: int = 200, **ctx):
    token = request.cookies.get(COOKIE)
    return request.app.state.templates.TemplateResponse(
        request, name, {"admin": admin, "csrf": auth.csrf_token(token) if token else "", **ctx}, status_code=status_code
    )


def parse_boards_file(raw: bytes) -> list[dict]:
    """The screens in a boards.json from Studio (format ssas.server-boards, version 2). Raises ValueError."""
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or data.get("format") != "ssas.server-boards":
        raise ValueError("not a boards.json file from SSAS Studio")
    if data.get("version") != 2:
        raise ValueError("this boards.json is from an older SSAS Studio: install Studio 0.2 and export again")
    boards = []
    for b in data.get("boards", []):
        groups = b.get("groups")
        people = b.get("people")
        ok = (
            CODE.match(str(b.get("board_code", "")))
            and b.get("kind") in BOARD_KINDS
            and isinstance(b.get("name"), str)
            and len(b["name"]) <= 80
            and SHA256.match(str(b.get("token_sha256", "")))
            and isinstance(groups, list)
            and all(isinstance(g, str) and CODE.match(g) for g in groups)
            and isinstance(people, dict)
            and set(people) <= set(groups)
        )
        if not ok:
            raise ValueError(f"screen {str(b.get('board_code'))[:20]!r} is not valid")
        for g, members in people.items():
            if not (
                isinstance(members, list)
                and all(
                    isinstance(m, dict)
                    and PERSON_ID.match(str(m.get("id", "")))
                    and isinstance(m.get("name"), str)
                    and 0 < len(m["name"]) <= 120
                    for m in members
                )
            ):
                raise ValueError(f"the people list of group {g} is not valid")
        boards.append(
            {
                "code": b["board_code"],
                "kind": b["kind"],
                "name": b["name"],
                "groups": groups,
                "people": {g: [{"id": m["id"], "name": m["name"]} for m in people[g]] for g in people},
                "token_sha256": b["token_sha256"],
            }
        )
    return boards


# ---------------- sign in / out ----------------
@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return page(request, "login.html", None, error=None)


@router.post("/login")
def login_post(
    request: Request,
    email: str = Form(..., max_length=200),
    password: str = Form(..., max_length=200),
    code: str = Form(..., max_length=20),
):
    wait = request.app.state.login_limit.hit(request.client.host if request.client else "?")
    if wait:
        return page(
            request,
            "login.html",
            None,
            429,
            email=email,
            error=f"Too many sign-in attempts from this address. Try again in {int(wait // 60) + 1} minutes.",
        )
    try:
        admin = auth.login(request.app.state.db, email, password, code)
    except auth.LoginError as e:
        return page(request, "login.html", None, error=str(e), email=email)
    cfg = request.app.state.cfg
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        COOKIE,
        auth.new_session(request.app.state.db, admin),
        httponly=True,
        samesite="strict",
        secure=cfg.cookie_secure,
        max_age=cfg.session_max_hours * 3600,
    )
    return resp


@router.post("/logout")
def logout(request: Request):
    auth.end_session(request.app.state.db, request.cookies.get(COOKIE))
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


# ---------------- attendance ----------------
@router.get("/", response_class=HTMLResponse)
def today(request: Request, day: str | None = None):
    admin = need_login(request)
    db = request.app.state.db
    try:
        d = Date.fromisoformat(day).isoformat() if day else Date.today().isoformat()
    except ValueError:
        d = Date.today().isoformat()
    results = day_results(db, d)
    groups = sorted(set(results) | {g for b in db.q("SELECT groups FROM boards") for g in json.loads(b["groups"])})
    sessions = sorted({s for r in results.values() for s in r})
    grid = {g: {s: counts(results[g][s]) for s in results.get(g, {})} for g in groups}
    flags = {g: left_after_present(results.get(g, {})) for g in groups}
    return page(request, "today.html", admin, day=d, groups=groups, sessions=sessions, grid=grid, flags=flags)


@router.get("/group/{code}/{day}/{session}", response_class=HTMLResponse)
def session_detail(request: Request, code: str, day: str, session: int):
    admin = need_login(request)
    db = request.app.state.db
    row = db.one("SELECT * FROM results WHERE group_code = ? AND date = ? AND session = ?", (code, day, session))
    if row is None:
        raise HTTPException(404, "no result for this group and session")
    p = json.loads(row["payload"])
    flags = left_after_present(day_results(db, day).get(code, {}))
    return page(
        request,
        "session.html",
        admin,
        p=p,
        code=code,
        day=day,
        session=session,
        flags=flags,
        received=row["received_at"],
        c=counts(p),
    )


@router.get("/export.csv")
def export_csv(request: Request, start: str | None = None, end: str | None = None):
    admin = need_login(request)
    db = request.app.state.db
    start = start or "0000-01-01"
    end = end or "9999-12-31"
    buf = io.StringIO()
    buf.write("﻿")  # so Excel shows Arabic names correctly
    w = csv.writer(buf)
    w.writerow(["date", "session", "group", "person_id", "person_name", "status", "board", "captured_at"])
    for r in db.q(
        "SELECT payload FROM results WHERE date BETWEEN ? AND ? ORDER BY date, group_code, session", (start, end)
    ):
        p = json.loads(r["payload"])
        for person in p["people"]:
            w.writerow(
                [
                    csv_cell(v)
                    for v in (
                        p["date"],
                        p["session"],
                        p["group_code"],
                        person["id"],
                        person["name"],
                        person["status"],
                        p["board_code"],
                        p.get("captured_at", ""),
                    )
                ]
            )
    db.audit(admin.email, "export.csv", {"start": start, "end": end})
    safe = re.sub(r"[^0-9-]", "", f"{start}_{end}".replace("_", "-to-"))
    return Response(
        buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="ssas-attendance-{safe}.csv"'},
    )


# ---------------- screens ----------------
def boards_page(request: Request, admin: auth.Admin, message: str | None = None, status_code: int = 200):
    rows = []
    for b in request.app.state.db.q("SELECT * FROM boards ORDER BY board_code"):
        hb = json.loads(b["heartbeat"]) if b["heartbeat"] else {}
        rows.append(
            {
                "code": b["board_code"],
                "kind": b["kind"],
                "name": b["name"],
                "groups": ", ".join(json.loads(b["groups"])),
                "last_seen": b["last_seen"],
                "hb": hb,
            }
        )
    return page(request, "boards.html", admin, status_code, rows=rows, message=message)


@router.get("/boards", response_class=HTMLResponse)
def boards(request: Request):
    return boards_page(request, need_login(request))


@router.post("/boards/import", response_class=HTMLResponse)
async def import_boards(request: Request, file: UploadFile, csrf: str = Form(...)):
    admin = need_login(request)
    if not admin.can_edit:
        raise HTTPException(403, "view-only account")
    if not auth.check_csrf(request.cookies.get(COOKIE), csrf):
        raise HTTPException(400, "form expired, reload the page")
    try:
        screens = parse_boards_file(await file.read())
    except (ValueError, RecursionError) as e:
        broken = isinstance(e, (json.JSONDecodeError, UnicodeDecodeError, RecursionError))
        return boards_page(request, admin, f"Not imported: {'not a JSON file' if broken else e}.", 400)
    db = request.app.state.db
    for s in screens:
        db.add_board(s["code"], s["kind"], s["name"], s["groups"], s["people"], s["token_sha256"])
    db.audit(admin.email, "boards.import", {"count": len(screens)})
    return boards_page(request, admin, f"Imported {len(screens)} boards.")

"""The API the screens call (each screen signs its requests with its own token).

POST /api/v1/results    one attendance result (format ssas.result, version 2)
POST /api/v1/heartbeat  "I am alive" every 5 minutes, with the screen's status
GET  /api/v1/health     for monitoring; no token needed

Answers a screen acts on (board app, Uploader.kt):
    200 stored · 409 already stored        -> the screen deletes its copy
    400 broken result                      -> the screen sets it aside and never resends it
    401 unknown token · 403 not registered -> the screen keeps it and tries again later
                                              (fixed by uploading the new boards.json here)
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date as Date
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from . import __version__
from .attendance import STATUSES
from .db import now

router = APIRouter(prefix="/api/v1")

RESULT_FORMAT = "ssas.result"
RESULT_VERSION = 2
TEXT_FIELDS = {"session_start": 32, "captured_at": 40, "camera_problem": 300, "model_created_at": 40, "app_version": 40}
COUNT_FIELDS = ("frames", "valid_frames", "unknown_max", "suspicious_max")
HEARTBEAT_FIELDS = {
    "board_code": str,
    "app_version": str,
    "armed": bool,
    "last_capture": str,
    "last_error": str,
    "next_capture": str,
    "pending": int,
    "time": str,
}


def _int_between(v, low: int, high: int) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and low <= v <= high


def screen_from(request: Request) -> sqlite3.Row:
    """The screen that sent this request, from its token; 401 when unknown."""
    db = request.app.state.db
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(401, "missing screen token")
    row = db.one(
        "SELECT * FROM boards WHERE token_sha256 = ?", (hashlib.sha256(header[7:].strip().encode()).hexdigest(),)
    )
    if row is None:
        raise HTTPException(401, "unknown screen: upload the latest boards.json on the server's Boards page")
    db.exec("UPDATE boards SET last_seen = ? WHERE board_code = ?", (now(), row["board_code"]))
    return row


async def _json_body(request: Request):
    try:
        return await request.json()
    except (ValueError, RecursionError):
        raise HTTPException(400, "invalid JSON") from None


def check_result(board: sqlite3.Row, p) -> dict:
    """Check a result from `board` and return what to store. The names always come from the
    registered list, never from the screen, so a stolen token cannot add or rename people."""
    if not isinstance(p, dict) or p.get("format") != RESULT_FORMAT:
        raise HTTPException(400, "not an SSAS result")
    if p.get("version") != RESULT_VERSION:
        raise HTTPException(
            400, f"result version {p.get('version')!r} is not supported: install SSAS Board 0.2 or newer"
        )
    group, day, session, people = p.get("group_code"), p.get("date"), p.get("session"), p.get("people")
    if not (
        isinstance(group, str) and isinstance(day, str) and _int_between(session, 0, 999) and isinstance(people, list)
    ):
        raise HTTPException(400, "missing or wrong group_code, date, session or people")
    try:
        Date.fromisoformat(day)
    except ValueError:
        raise HTTPException(400, "bad date") from None
    if p.get("board_code") != board["board_code"]:
        raise HTTPException(403, "this result is for another screen")
    if group not in json.loads(board["groups"]):
        raise HTTPException(403, f"this screen does not take attendance for group {group[:40]}")
    names = {x["id"]: x["name"] for x in json.loads(board["people"]).get(group, [])}

    clean_people, seen = [], set()
    for x in people:
        if not (isinstance(x, dict) and isinstance(x.get("id"), str) and x.get("status") in STATUSES):
            raise HTTPException(400, "bad entry in people")
        if x["id"] in seen:
            raise HTTPException(400, "the same person is listed twice")
        if x["id"] not in names:
            raise HTTPException(
                403, f"{x['id'][:40]} is not registered in group {group} on this server: upload the latest boards.json"
            )
        seen.add(x["id"])
        entry = {"id": x["id"], "name": names[x["id"]], "status": x["status"]}
        score = x.get("score")
        if score is not None:
            if not (isinstance(score, (int, float)) and not isinstance(score, bool) and -1.0 <= score <= 1.0):
                raise HTTPException(400, "bad score")
            entry["score"] = round(float(score), 4)
        clean_people.append(entry)

    out = {
        "format": RESULT_FORMAT,
        "version": RESULT_VERSION,
        "board_code": board["board_code"],
        "group_code": group,
        "date": day,
        "session": session,
        "people": clean_people,
    }
    for key, longest in TEXT_FIELDS.items():
        v = p.get(key)
        if v is not None:
            if not (isinstance(v, str) and len(v) <= longest):
                raise HTTPException(400, f"bad {key}")
            out[key] = v
    for key in COUNT_FIELDS:
        v = p.get(key, 0)
        if not _int_between(v, 0, 1_000_000):
            raise HTTPException(400, f"bad {key}")
        out[key] = v
    return out


@router.post("/results")
async def post_result(request: Request):
    board = screen_from(request)
    r = check_result(board, await _json_body(request))
    try:
        request.app.state.db.exec(
            "INSERT INTO results (board_code, group_code, date, session, session_start, received_at, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                r["board_code"],
                r["group_code"],
                r["date"],
                r["session"],
                r.get("session_start", ""),
                now(),
                json.dumps(r, ensure_ascii=False),
            ),
        )
    except sqlite3.IntegrityError:  # this group, date and session is already stored
        return JSONResponse({"ok": True, "duplicate": True}, status_code=409)
    return {"ok": True}


@router.post("/heartbeat")
async def heartbeat(request: Request):
    board = screen_from(request)
    body = await _json_body(request)
    keep = {}
    if isinstance(body, dict):
        for key, kind in HEARTBEAT_FIELDS.items():
            v = body.get(key)
            if isinstance(v, kind) and (kind is not int or not isinstance(v, bool)):
                keep[key] = v[:300] if isinstance(v, str) else v
    request.app.state.db.exec(
        "UPDATE boards SET heartbeat = ? WHERE board_code = ?",
        (json.dumps(keep, ensure_ascii=False), board["board_code"]),
    )
    return {"ok": True, "server_time": datetime.now().isoformat(timespec="seconds")}


@router.get("/health")
def health():
    return {"ok": True, "version": __version__}

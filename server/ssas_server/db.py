"""SQLite storage: one file (ssas.sqlite3) in the data folder.

Tables:
    admins    people who sign in to the web pages (password + 6-digit code)
    sessions  signed-in browsers (only a hash of the cookie is stored)
    boards    the screens, their groups and the people registered for each group (from boards.json)
    results   one row per group, date and session: the result a screen sent, as JSON
    audit     who did what (sign-ins, uploads, exports)
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('developer', 'supervisor')),
    pw_hash TEXT NOT NULL,
    totp_secret TEXT NOT NULL,
    last_totp_step INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    admin_id INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS boards (
    board_code TEXT PRIMARY KEY,
    kind TEXT NOT NULL,              -- 'group' (the room of one group) or 'shared' (a room several groups use)
    name TEXT NOT NULL,
    groups TEXT NOT NULL,            -- JSON list of group codes
    people TEXT NOT NULL,            -- JSON {group_code: [{"id", "name"}]}
    token_sha256 TEXT NOT NULL,      -- SHA-256 of the screen's token (the token itself is never stored)
    updated_at TEXT NOT NULL,
    last_seen TEXT,
    heartbeat TEXT                   -- JSON of the screen's last heartbeat
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY,
    board_code TEXT NOT NULL,
    group_code TEXT NOT NULL,
    date TEXT NOT NULL,
    session INTEGER NOT NULL,
    session_start TEXT NOT NULL,
    received_at TEXT NOT NULL,
    payload TEXT NOT NULL,           -- the ssas.result JSON (version 2), names from the registered list
    UNIQUE (group_code, date, session)
);
CREATE INDEX IF NOT EXISTS results_by_date ON results (date, group_code);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def result_v1_to_v2(p: dict) -> dict:
    """A stored 0.1 result (school words) in the 0.2 shape."""
    old = ("class_code", "period", "lesson_start", "students")
    out = {k: v for k, v in p.items() if k not in old}
    out.update(
        version=2,
        group_code=p.get("class_code", ""),
        session=p.get("period", 0),
        session_start=p.get("lesson_start", ""),
        people=p.get("students", []),
    )
    return out


def _columns(c: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in c.execute(f"PRAGMA table_info({table})")}


def _upgrade_from_v1(c: sqlite3.Connection) -> None:
    """Rename the columns of a 0.1 database (class, period, student) to the 0.2 words, once."""
    if "class_code" in _columns(c, "results"):
        c.execute("ALTER TABLE results RENAME COLUMN class_code TO group_code")
        c.execute("ALTER TABLE results RENAME COLUMN period TO session")
        c.execute("ALTER TABLE results RENAME COLUMN lesson_start TO session_start")
        for rid, payload in c.execute("SELECT id, payload FROM results").fetchall():
            c.execute(
                "UPDATE results SET payload = ? WHERE id = ?",
                (json.dumps(result_v1_to_v2(json.loads(payload)), ensure_ascii=False), rid),
            )
    if "classes" in _columns(c, "boards"):
        c.execute("ALTER TABLE boards RENAME COLUMN classes TO groups")
        c.execute("ALTER TABLE boards RENAME COLUMN students TO people")
        c.execute("UPDATE boards SET kind = CASE kind WHEN 'class' THEN 'group' WHEN 'lab' THEN 'shared' ELSE kind END")


class Database:
    """One connection per thread (FastAPI runs page handlers in a thread pool)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        c = self.conn()
        c.execute("BEGIN IMMEDIATE")
        try:
            _upgrade_from_v1(c)
            c.execute("COMMIT")
        except Exception:
            c.execute("ROLLBACK")
            raise
        c.executescript(SCHEMA)

    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=15, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
        return c

    def q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return self.conn().execute(sql, args).fetchall()

    def one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        return self.conn().execute(sql, args).fetchone()

    def exec(self, sql: str, args: tuple = ()) -> int:
        cur = self.conn().execute(sql, args)
        return cur.lastrowid or cur.rowcount

    def audit(self, actor: str, action: str, detail: dict | str) -> None:
        self.exec(
            "INSERT INTO audit (at, actor, action, detail) VALUES (?, ?, ?, ?)",
            (now(), actor, action, detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)),
        )

    def add_board(
        self, code: str, kind: str, name: str, groups: list[str], people: dict[str, list[dict]], token_sha256: str
    ) -> None:
        """Add a screen, or replace its details (from boards.json)."""
        self.exec(
            "INSERT INTO boards (board_code, kind, name, groups, people, token_sha256, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(board_code) DO UPDATE SET kind=excluded.kind, name=excluded.name, groups=excluded.groups, "
            "people=excluded.people, token_sha256=excluded.token_sha256, updated_at=excluded.updated_at",
            (code, kind, name, json.dumps(list(groups)), json.dumps(people, ensure_ascii=False), token_sha256, now()),
        )

"""SQLite storage (one file in the data folder)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
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
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    classes TEXT NOT NULL,
    students TEXT NOT NULL,
    token_sha256 TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_seen TEXT,
    heartbeat TEXT
);
CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY,
    board_code TEXT NOT NULL,
    class_code TEXT NOT NULL,
    date TEXT NOT NULL,
    period INTEGER NOT NULL,
    lesson_start TEXT NOT NULL,
    received_at TEXT NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE (class_code, date, period)
);
CREATE INDEX IF NOT EXISTS results_by_date ON results (date, class_code);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self.conn() as c:
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
        self.exec("INSERT INTO audit (at, actor, action, detail) VALUES (?, ?, ?, ?)",
                  (now(), actor, action, detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)))

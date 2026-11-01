"""Reading stored results: one session, one day, and the 'left after being present' check."""

from __future__ import annotations

import json
from collections import defaultdict

from .db import Database

STATUSES = ("present", "absent", "needs_review", "no_data")
PRESENT_LIKE = {"present", "late"}


def day_results(db: Database, date: str) -> dict[str, dict[int, dict]]:
    """{group_code: {session: payload}} for one date."""
    out: dict[str, dict[int, dict]] = defaultdict(dict)
    for r in db.q(
        "SELECT group_code, session, payload FROM results WHERE date = ? ORDER BY group_code, session", (date,)
    ):
        out[r["group_code"]][r["session"]] = json.loads(r["payload"])
    return out


def counts(payload: dict) -> dict[str, int]:
    """How many people have each status in one result."""
    c = dict.fromkeys(STATUSES, 0)
    for person in payload.get("people", []):
        c[person["status"]] = c.get(person["status"], 0) + 1
    return c


def left_after_present(sessions: dict[int, dict]) -> dict[str, dict]:
    """People seen in an earlier session of the day and absent from a later one."""
    seen: dict[str, int] = {}
    flags: dict[str, dict] = {}
    for session in sorted(sessions):
        for person in sessions[session].get("people", []):
            if person["status"] in PRESENT_LIKE:
                seen.setdefault(person["id"], session)
            elif person["status"] == "absent" and person["id"] in seen and person["id"] not in flags:
                flags[person["id"]] = {"name": person["name"], "present_in": seen[person["id"]], "absent_from": session}
    return flags

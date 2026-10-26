"""Reading the stored results: per period, per day, and the 'missing after present' check."""

from __future__ import annotations

import json
from collections import defaultdict

from .db import Database

PRESENT_LIKE = {"present", "late"}
COUNTED = ("present", "absent", "needs_review", "no_data")


def day_results(db: Database, date: str) -> dict[str, dict[int, dict]]:
    """{class_code: {period: payload}} for one date."""
    out: dict[str, dict[int, dict]] = defaultdict(dict)
    for r in db.q("SELECT class_code, period, payload FROM results WHERE date = ? ORDER BY class_code, period", (date,)):
        out[r["class_code"]][r["period"]] = json.loads(r["payload"])
    return out


def counts(payload: dict) -> dict[str, int]:
    c = {k: 0 for k in COUNTED}
    for s in payload.get("students", []):
        c[s["status"]] = c.get(s["status"], 0) + 1
    return c


def missing_after_present(periods: dict[int, dict]) -> dict[str, dict]:
    """Students seen in an earlier lesson of the day and absent in a later one ("left after being present")."""
    seen: dict[str, int] = {}
    flags: dict[str, dict] = {}
    for period in sorted(periods):
        for s in periods[period].get("students", []):
            if s["status"] in PRESENT_LIKE:
                seen.setdefault(s["id"], period)
            elif s["status"] == "absent" and s["id"] in seen and s["id"] not in flags:
                flags[s["id"]] = {"name": s["name"], "present_in": seen[s["id"]], "absent_from": period}
    return flags

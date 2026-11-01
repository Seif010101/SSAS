"""Write the USB folder that the screens import (formats in docs/data-format.md, all version 2).

SSAS-USB/
    ssas-usb.json                       which screens are on this stick
    ssas-board.apk                      the screen app
    models/  det_10g.onnx  w600k_r50.onnx  [rtmo-s.onnx]  models.json
    screens/<screen>/board.json  group-<code>.json ...
    server/boards.json                  for the server's Boards page (no photos, no face data)
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import __version__
from . import groupmodel
from .models import MODELS, sha256_file
from .storage import Organisation, now_iso, valid_pin

BOARD_FORMAT = "ssas.board"
FORMAT_VERSION = 2
USB_FOLDER = "SSAS-USB"

ProgressFn = Callable[[str, float], None]


@dataclass
class BoardPlan:
    """What one screen does: its own group's sessions, or the sessions of the groups that visit a shared room."""

    code: str
    kind: str  # "group" (the room of one group) or "shared" (a room several groups use)
    name: str
    groups: set[str] = field(default_factory=set)
    slots: list[dict] = field(default_factory=list)  # {"day", "session", "group_code"}


def board_plans(org: Organisation) -> tuple[dict[str, BoardPlan], list[str]]:
    """Which group each screen takes attendance for, in which sessions. Returns (plans, problems)."""
    problems: list[str] = []
    plans: dict[str, BoardPlan] = {}
    rooms = {r["code"]: r for r in org.shared_rooms}
    for code in org.group_codes():
        plans[code] = BoardPlan(code, "group", code, {code})
    for code, room in rooms.items():
        plans[code] = BoardPlan(code, "shared", room.get("name") or code)
    taken: dict[tuple[str, int, int], str] = {}
    for code in org.group_codes():
        g = org.load_group(code)
        for day in org.days:
            for s in org.attendance_sessions():
                cell = g.timetable.get(str(day), {}).get(str(s["number"]), "here")
                if cell == "skip":
                    continue
                board = code if cell == "here" else cell
                if board not in plans:
                    problems.append(f"{code}: unknown shared room '{cell}' on day {day}, session {s['number']}")
                    continue
                key = (board, day, s["number"])
                if key in taken:
                    problems.append(
                        f"{board}: both {taken[key]} and {code} are scheduled on day {day}, session {s['number']}"
                    )
                    continue
                taken[key] = code
                plans[board].groups.add(code)
                plans[board].slots.append({"day": day, "session": s["number"], "group_code": code})
    return plans, problems


def check_ready(org: Organisation, boards: list[str]) -> list[str]:
    """Reasons the export cannot start yet (empty when it can)."""
    st = org.settings
    reasons = []
    if not valid_pin(st.board_admin_pin):
        reasons.append("Set the screens' admin PIN (6 or more digits) in Settings first.")
    if st.server_url and not st.server_url.lower().startswith("https://"):
        reasons.append("The server address in Settings must start with https://")
    plans, _ = board_plans(org)
    for b in boards:
        if b not in plans:
            reasons.append(f"Unknown screen: {b}")
            continue
        for code in sorted(plans[b].groups):
            if not (org.model_dir(code) / groupmodel.FILE_NAME).exists():
                reasons.append(f"Group {code} has no trained model yet (needed by screen {b}). Train it first.")
    return reasons


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _copy_if_changed(src: Path, dst: Path, sha: str) -> None:
    if dst.exists() and sha256_file(dst) == sha:
        return
    tmp = dst.with_suffix(dst.suffix + ".part")
    shutil.copyfile(src, tmp)
    tmp.replace(dst)


def export_usb(
    org: Organisation,
    target: Path,
    boards: list[str],
    models_dir: Path,
    apk: Path | None,
    progress: ProgressFn | None = None,
) -> dict:
    """Export the chosen screens to ``target``/SSAS-USB. Returns a summary dict."""
    reasons = check_ready(org, boards)
    if reasons:
        raise ValueError("\n".join(reasons))
    plans, problems = board_plans(org)

    root = Path(target) / USB_FOLDER
    for sub in ("models", "screens", "server"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    st = org.settings

    def step(msg, f):
        if progress:
            progress(msg, f)

    # Models (copied once; skipped when the same file is already on the USB).
    model_entries = {}
    keys = [k for k, m in MODELS.items() if m.for_board and (models_dir / m.filename).exists()]
    for i, key in enumerate(keys):
        m = MODELS[key]
        src = models_dir / m.filename
        step(f"Copying model {m.filename}", 0.05 + 0.5 * i / max(1, len(keys)))
        sha = sha256_file(src)
        _copy_if_changed(src, root / "models" / m.filename, sha)
        model_entries[key] = {"file": m.filename, "sha256": sha}
    (root / "models" / "models.json").write_text(json.dumps(model_entries, indent=2), encoding="utf-8")

    if apk and Path(apk).exists():
        step("Copying the screen app", 0.6)
        shutil.copyfile(apk, root / "ssas-board.apk")

    server_boards = []
    for i, b in enumerate(boards):
        plan = plans[b]
        step(f"Writing screen {b}", 0.65 + 0.3 * i / max(1, len(boards)))
        folder = root / "screens" / b
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        group_files, people = [], {}
        for code in sorted(plan.groups):
            model = groupmodel.read(org.model_dir(code) / groupmodel.FILE_NAME)
            name = f"group-{code}.json"
            groupmodel.write(folder / name, model)
            group_files.append(
                {"group_code": code, "file": name, "sha256": sha256_file(folder / name), "people": len(model["people"])}
            )
            people[code] = [{"id": p["id"], "name": p["name"]} for p in model["people"]]
        token = org.board_token(b)
        board = {
            "format": BOARD_FORMAT,
            "version": FORMAT_VERSION,
            "board_code": b,
            "kind": plan.kind,
            "name": plan.name,
            "org_name": org.name,
            "exported_at": now_iso(),
            "studio_version": __version__,
            "days": org.days,
            "sessions": org.sessions,
            "slots": sorted(plan.slots, key=lambda s: (s["day"], s["session"])),
            "groups": group_files,
            "capture": {
                "offset_min": st.capture_offset_min,
                "window_min": st.capture_window_min,
                "shots_s": st.shot_schedule_s,
                "min_valid_frames": st.min_valid_frames,
            },
            "models": model_entries,
            "server": {"url": st.server_url.strip(), "cert_sha256": st.server_cert_sha256.strip(), "token": token},
            "admin_pin_sha256": _sha256_text(f"{b}:{st.board_admin_pin}"),
            "sound": st.sound,
        }
        (folder / "board.json").write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
        server_boards.append(
            {
                "board_code": b,
                "kind": plan.kind,
                "name": plan.name,
                "groups": sorted(plan.groups),
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                "people": people,
            }
        )

    # boards.json keeps the screens exported earlier to this stick, unless they are from an older Studio.
    existing = []
    sb_path = root / "server" / "boards.json"
    if sb_path.exists():
        try:
            old = json.loads(sb_path.read_text(encoding="utf-8"))
            existing = old.get("boards", []) if old.get("version") == FORMAT_VERSION else []
        except (ValueError, OSError):
            existing = []
    merged = {e["board_code"]: e for e in existing}
    merged.update({e["board_code"]: e for e in server_boards})
    sb_path.write_text(
        json.dumps(
            {
                "format": "ssas.server-boards",
                "version": FORMAT_VERSION,
                "org_name": org.name,
                "boards": sorted(merged.values(), key=lambda e: e["board_code"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    index = {
        "format": "ssas.usb",
        "version": FORMAT_VERSION,
        "org_name": org.name,
        "exported_at": now_iso(),
        "studio_version": __version__,
        "boards": sorted({p.name for p in (root / "screens").iterdir() if (p / "board.json").exists()}),
        "app": "ssas-board.apk" if (root / "ssas-board.apk").exists() else None,
    }
    (root / "ssas-usb.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    step("Done", 1.0)
    return {"folder": str(root), "boards": boards, "problems": problems, "models": list(model_entries)}

"""Write the USB folder that the boards import (see docs/data-format.md).

SSAS-USB/
    ssas-usb.json
    ssas-board.apk
    models/  det_10g.onnx  w600k_r50.onnx  [rtmo-s.onnx]  models.json
    screens/<board>/board.json  class-<code>.json ...
    server/boards.json
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import __version__
from . import classmodel
from .models import MODELS, sha256_file
from .storage import School, now_iso

BOARD_FORMAT = "ssas.board"
BOARD_VERSION = 1
USB_FOLDER = "SSAS-USB"

ProgressFn = Callable[[str, float], None]


@dataclass
class BoardPlan:
    code: str
    kind: str  # "class" or "lab"
    name: str
    classes: set[str] = field(default_factory=set)
    slots: list[dict] = field(default_factory=list)  # {"day", "period", "class_code"}


def board_plans(school: School) -> tuple[dict[str, BoardPlan], list[str]]:
    """Which class each board takes attendance for, in which periods. Returns (plans, problems)."""
    problems: list[str] = []
    plans: dict[str, BoardPlan] = {}
    labs = {lab["code"]: lab for lab in school.labs}
    for code in school.class_codes():
        plans[code] = BoardPlan(code, "class", code, {code})
    for code, lab in labs.items():
        plans[code] = BoardPlan(code, "lab", lab.get("name") or code)
    taken: dict[tuple[str, int, int], str] = {}
    for code in school.class_codes():
        c = school.load_class(code)
        for day in school.school_days:
            for p in school.class_periods():
                cell = c.timetable.get(str(day), {}).get(str(p["number"]), "here")
                if cell == "skip":
                    continue
                board = code if cell == "here" else cell
                if board not in plans:
                    problems.append(f"{code}: unknown lab '{cell}' on day {day}, period {p['number']}")
                    continue
                key = (board, day, p["number"])
                if key in taken:
                    problems.append(
                        f"{board}: both {taken[key]} and {code} are scheduled on day {day}, period {p['number']}"
                    )
                    continue
                taken[key] = code
                plans[board].classes.add(code)
                plans[board].slots.append({"day": day, "period": p["number"], "class_code": code})
    return plans, problems


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _copy_if_changed(src: Path, dst: Path, sha: str) -> None:
    if dst.exists() and sha256_file(dst) == sha:
        return
    tmp = dst.with_suffix(dst.suffix + ".part")
    shutil.copyfile(src, tmp)
    tmp.replace(dst)


def export_usb(
    school: School,
    target: Path,
    boards: list[str],
    models_dir: Path,
    apk: Path | None,
    progress: ProgressFn | None = None,
) -> dict:
    """Export the chosen boards to ``target``/SSAS-USB. Returns a summary dict."""
    plans, problems = board_plans(school)
    missing = [b for b in boards if b not in plans]
    if missing:
        raise ValueError(f"Unknown boards: {', '.join(missing)}")
    for b in boards:
        for code in plans[b].classes:
            if not (school.model_dir(code) / "class-model.json").exists():
                raise ValueError(f"Class {code} has no trained model yet (needed by board {b}). Train it first.")

    root = Path(target) / USB_FOLDER
    (root / "models").mkdir(parents=True, exist_ok=True)
    (root / "screens").mkdir(parents=True, exist_ok=True)
    (root / "server").mkdir(parents=True, exist_ok=True)
    st = school.settings

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
        step("Copying the board app", 0.6)
        shutil.copyfile(apk, root / "ssas-board.apk")

    server_boards = []
    for i, b in enumerate(boards):
        plan = plans[b]
        step(f"Writing board {b}", 0.65 + 0.3 * i / max(1, len(boards)))
        folder = root / "screens" / b
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        class_files = []
        for code in sorted(plan.classes):
            model = classmodel.read(school.model_dir(code) / "class-model.json")
            name = f"class-{code}.json"
            classmodel.write(folder / name, model)
            class_files.append(
                {
                    "class_code": code,
                    "file": name,
                    "sha256": sha256_file(folder / name),
                    "students": len(model["students"]),
                }
            )
        token = school.board_token(b)
        board = {
            "format": BOARD_FORMAT,
            "version": BOARD_VERSION,
            "board_code": b,
            "kind": plan.kind,
            "name": plan.name,
            "school_name": school.name,
            "exported_at": now_iso(),
            "studio_version": __version__,
            "school_days": school.school_days,
            "bell": school.bell,
            "slots": sorted(plan.slots, key=lambda s: (s["day"], s["period"])),
            "classes": class_files,
            "capture": {
                "offset_min": st.capture_offset_min,
                "window_min": st.capture_window_min,
                "shots_s": st.shot_schedule_s,
                "min_valid_frames": st.min_valid_frames,
            },
            "models": model_entries,
            "server": {"url": st.server_url, "cert_sha256": st.server_cert_sha256, "token": token},
            "admin_pin_sha256": _sha256_text(f"{b}:{st.board_admin_pin}"),
            "sound": st.sound,
        }
        (folder / "board.json").write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding="utf-8")
        server_boards.append(
            {
                "board_code": b,
                "kind": plan.kind,
                "name": plan.name,
                "classes": sorted(plan.classes),
                "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
                "students": {
                    code: list(classmodel.read(school.model_dir(code) / "class-model.json")["students"])
                    for code in sorted(plan.classes)
                },
            }
        )

    existing = []
    sb_path = root / "server" / "boards.json"
    if sb_path.exists():
        try:
            existing = json.loads(sb_path.read_text(encoding="utf-8")).get("boards", [])
        except (ValueError, OSError):
            existing = []
    merged = {e["board_code"]: e for e in existing}
    merged.update({e["board_code"]: e for e in server_boards})
    sb_path.write_text(
        json.dumps(
            {
                "format": "ssas.server-boards",
                "version": 1,
                "school_name": school.name,
                "boards": sorted(merged.values(), key=lambda e: e["board_code"]),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    index = {
        "format": "ssas.usb",
        "version": 1,
        "school_name": school.name,
        "exported_at": now_iso(),
        "studio_version": __version__,
        "boards": sorted({p.name for p in (root / "screens").iterdir() if (p / "board.json").exists()}),
        "app": "ssas-board.apk" if (root / "ssas-board.apk").exists() else None,
    }
    (root / "ssas-usb.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    step("Done", 1.0)
    return {"folder": str(root), "boards": boards, "problems": problems, "models": list(model_entries)}

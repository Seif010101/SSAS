"""The organisation's data on the laptop: plain folders and JSON files.

<data folder>/
    org.json                        name, working days, session times, settings, shared rooms, screen keys
    groups/
        9A1/
            group.json              the group's name, room, people and timetable
            Ahmed Ali/              one folder per person with their photos
                20261026-101500-03-left.jpg
            model/
                group-model.json    the trained model of this group only
                report.json         training report
                embeddings.npz      cached embeddings (also used as "strangers" for the other groups)

A data folder made by Studio 0.1 (school.json, screens/<class>/class.json) is converted once, the first time
Studio 0.2 opens it (migrate_v1). The photos stay where they are, trained models keep working, and a copy of
the old files is kept in backup-0.1/.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from ..logs import get_logger

log = get_logger("storage")

FORMAT_VERSION = 2
PHOTO_EXT = ".jpg"

SESSION_KINDS = ("session", "break", "other")  # attendance is taken in "session" rows only
DEFAULT_SESSIONS = [
    {"number": 1, "start": "07:30", "end": "08:15", "kind": "session"},
    {"number": 2, "start": "08:20", "end": "09:05", "kind": "session"},
    {"number": 3, "start": "09:10", "end": "09:55", "kind": "session"},
    {"number": 0, "start": "09:55", "end": "10:15", "kind": "break"},
    {"number": 4, "start": "10:15", "end": "11:00", "kind": "session"},
    {"number": 5, "start": "11:05", "end": "11:50", "kind": "session"},
    {"number": 6, "start": "11:55", "end": "12:40", "kind": "session"},
]
DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,15}$")
_PIN_RE = re.compile(r"^\d{6,12}$")
_BAD_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_FOLDERS = {"model"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_folder_name(name: str) -> str:
    """A Windows-safe folder name that keeps Arabic and other letters."""
    clean = _BAD_NAME_CHARS.sub("_", name).strip().rstrip(".")
    clean = re.sub(r"\s+", " ", clean)
    if not clean or clean.lower() in RESERVED_FOLDERS:
        clean = f"_{clean or 'person'}"
    return clean[:80]


def valid_code(code: str) -> bool:
    """Group, shared-room and screen codes: letters, digits, - and _ (max 16). They become folder names."""
    return bool(_CODE_RE.match(code))


def valid_pin(pin: str) -> bool:
    """The screens' admin PIN: 6 to 12 digits (there is no default PIN)."""
    return bool(_PIN_RE.match(pin))


def suggest_pin() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def _read_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


@dataclass
class Settings:
    capture_offset_min: float = 3.0  # the camera opens this many minutes after a session starts
    capture_window_min: float = 5.0  # ... and stays open at most this long
    shot_schedule_s: list[int] = field(default_factory=lambda: [0, 10, 25, 45, 75, 120, 180, 240])
    min_valid_frames: int = 3
    epochs: int = 200
    augment_per_photo: int = 10
    folds: int = 5
    seeds: int = 3
    min_accuracy: float = 0.98
    photos_per_person: int = 40
    strict_order: bool = False  # capture: ring parts must be followed in a random order (anti-cheat)
    settings_version: int = 3
    server_url: str = ""  # https://... or empty (no server: results go out by USB)
    server_cert_sha256: str = ""  # empty = the server has a normal public certificate (e.g. a VPS)
    board_admin_pin: str = ""  # 6+ digits; must be set before the first export
    sound: bool = True


@dataclass
class Person:
    id: str
    name: str
    folder: str


@dataclass
class Group:
    code: str
    name: str = ""
    room: str = ""
    people: list[Person] = field(default_factory=list)
    # timetable[day][session] = "here" | "skip" | <shared room code>; missing = "here" for attendance sessions
    timetable: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return f"{self.code} · {self.name}" if self.name and self.name != self.code else self.code

    def to_json(self) -> dict:
        d = asdict(self)
        d["format"] = "ssas.group"
        d["version"] = FORMAT_VERSION
        return d

    @staticmethod
    def from_json(d: dict) -> Group:
        return Group(
            code=d["code"],
            name=d.get("name", ""),
            room=d.get("room", ""),
            people=[Person(**p) for p in d.get("people", [])],
            timetable=d.get("timetable", {}),
        )


class Organisation:
    """Everything stored under one data folder."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        migrate_v1(self.root)
        self.groups_dir = self.root / "groups"
        self.groups_dir.mkdir(parents=True, exist_ok=True)
        self._org = _read_json(self.root / "org.json", None)
        if self._org is None:
            self._org = {
                "format": "ssas.org",
                "version": FORMAT_VERSION,
                "name": "My organisation",
                "days": [1, 2, 3, 4, 5],
                "sessions": DEFAULT_SESSIONS,
                "shared_rooms": [],
                "settings": asdict(Settings()),
                "board_tokens": {},
            }
            self.save()

    # ----- organisation -----
    def save(self) -> None:
        _write_json(self.root / "org.json", self._org)

    @property
    def name(self) -> str:
        return self._org.get("name", "")

    @name.setter
    def name(self, value: str) -> None:
        self._org["name"] = value.strip()
        self.save()

    @property
    def days(self) -> list[int]:
        """Working days, 1 = Monday ... 7 = Sunday."""
        return list(self._org.get("days", [1, 2, 3, 4, 5]))

    @days.setter
    def days(self, days: list[int]) -> None:
        self._org["days"] = sorted({int(d) for d in days if 1 <= int(d) <= 7})
        self.save()

    @property
    def sessions(self) -> list[dict]:
        """The daily times: [{"number", "start", "end", "kind"}], kind in SESSION_KINDS."""
        return list(self._org.get("sessions", []))

    @sessions.setter
    def sessions(self, rows: list[dict]) -> None:
        clean = []
        for r in rows:
            kind = r.get("kind", "session")
            if kind not in SESSION_KINDS:
                raise ValueError(f"Unknown session type: {kind}")
            if _parse_hhmm(r["end"]) <= _parse_hhmm(r["start"]):
                raise ValueError(f"Session {r.get('number')}: end must be after start")
            clean.append({"number": int(r.get("number", 0)), "start": r["start"], "end": r["end"], "kind": kind})
        clean.sort(key=lambda r: _parse_hhmm(r["start"]))
        self._org["sessions"] = clean
        self.save()

    def attendance_sessions(self) -> list[dict]:
        """The sessions in which attendance is taken."""
        return [s for s in self.sessions if s["kind"] == "session"]

    @property
    def shared_rooms(self) -> list[dict]:
        """Rooms that several groups use at different times (a lab, a hall): [{"code", "name"}]."""
        return list(self._org.get("shared_rooms", []))

    def add_shared_room(self, code: str, name: str) -> None:
        if not valid_code(code):
            raise ValueError("A room code may contain letters, digits, - and _ only (max 16).")
        if code in self.group_codes() or any(r["code"] == code for r in self.shared_rooms):
            raise ValueError(f"The code {code} is already used.")
        self._org.setdefault("shared_rooms", []).append({"code": code, "name": name})
        self.save()

    def remove_shared_room(self, code: str) -> None:
        self._org["shared_rooms"] = [r for r in self.shared_rooms if r["code"] != code]
        self.save()

    @property
    def settings(self) -> Settings:
        base = asdict(Settings())
        base.update({k: v for k, v in self._org.get("settings", {}).items() if k in base})
        return Settings(**base)

    @settings.setter
    def settings(self, s: Settings) -> None:
        self._org["settings"] = asdict(s)
        self.save()

    def board_token(self, board_code: str) -> str:
        """The secret a screen uses to send results to the server (made once per screen)."""
        tokens = self._org.setdefault("board_tokens", {})
        if board_code not in tokens:
            tokens[board_code] = secrets.token_urlsafe(32)
            self.save()
        return tokens[board_code]

    def new_board_token(self, board_code: str) -> None:
        """Replace a screen's server key, e.g. after a USB stick was lost."""
        self._org.setdefault("board_tokens", {})[board_code] = secrets.token_urlsafe(32)
        self.save()

    # ----- groups -----
    def group_codes(self) -> list[str]:
        return sorted(p.name for p in self.groups_dir.iterdir() if (p / "group.json").exists())

    def group_dir(self, code: str) -> Path:
        return self.groups_dir / code

    def load_group(self, code: str) -> Group:
        return Group.from_json(_read_json(self.group_dir(code) / "group.json", None))

    def save_group(self, g: Group) -> None:
        _write_json(self.group_dir(g.code) / "group.json", g.to_json())

    def add_group(self, code: str, name: str = "", room: str = "") -> Group:
        if not valid_code(code):
            raise ValueError("A group code may contain letters, digits, - and _ only (max 16), e.g. 9A1 or TEAM-A.")
        if (self.group_dir(code) / "group.json").exists() or any(r["code"] == code for r in self.shared_rooms):
            raise ValueError(f"The code {code} is already used.")
        g = Group(code=code, name=name.strip() or code, room=room.strip())
        self.save_group(g)
        return g

    def delete_group(self, code: str) -> None:
        shutil.rmtree(self.group_dir(code), ignore_errors=True)

    # ----- people -----
    def add_person(self, code: str, name: str) -> Person:
        name = " ".join(name.split())
        if not name:
            raise ValueError("The name is empty.")
        g = self.load_group(code)
        if any(p.name == name for p in g.people):
            raise ValueError(f"{name} is already in {code}.")
        folder = safe_folder_name(name)
        existing = {p.folder for p in g.people}
        base, n = folder, 2
        while folder in existing:
            folder = f"{base} ({n})"
            n += 1
        num = 1 + max([int(p.id.rsplit("-", 1)[-1]) for p in g.people if p.id.rsplit("-", 1)[-1].isdigit()] or [0])
        person = Person(id=f"{code}-{num:03d}", name=name, folder=folder)
        g.people.append(person)
        (self.group_dir(code) / folder).mkdir(parents=True, exist_ok=True)
        self.save_group(g)
        return person

    def rename_person(self, code: str, person_id: str, new_name: str) -> None:
        g = self.load_group(code)
        for p in g.people:
            if p.id == person_id:
                p.name = " ".join(new_name.split())
        self.save_group(g)

    def remove_person(self, code: str, person_id: str) -> None:
        g = self.load_group(code)
        keep = []
        for p in g.people:
            if p.id == person_id:
                shutil.rmtree(self.group_dir(code) / p.folder, ignore_errors=True)
            else:
                keep.append(p)
        g.people = keep
        self.save_group(g)

    def person_dir(self, code: str, person: Person) -> Path:
        return self.group_dir(code) / person.folder

    def photos(self, code: str, person: Person) -> list[Path]:
        d = self.person_dir(code, person)
        return sorted(d.glob(f"*{PHOTO_EXT}")) if d.exists() else []

    def clear_photos(self, code: str, person: Person) -> None:
        for p in self.photos(code, person):
            p.unlink(missing_ok=True)

    # ----- model -----
    def model_dir(self, code: str) -> Path:
        return self.group_dir(code) / "model"

    def report(self, code: str) -> dict | None:
        return _read_json(self.model_dir(code) / "report.json", None)


def import_people(path: Path) -> list[str]:
    """Read names from .xlsx / .csv / .txt (first column, header row optional)."""
    path = Path(path)
    names: list[str] = []
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        for row in ws.iter_rows(values_only=True):
            if row and row[0] is not None:
                names.append(str(row[0]))
    else:
        import csv

        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if row and row[0].strip():
                    names.append(row[0])
    names = [" ".join(n.split()) for n in names if n and n.strip()]
    headers = {"name", "names", "person", "people", "student", "student name", "employee", "الاسم", "اسم الطالب", "اسم"}
    if names and names[0].lower() in headers:
        names = names[1:]
    seen, out = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _parse_hhmm(s: str) -> int:
    m = re.match(r"^(\d{1,2}):(\d{2})$", s.strip())
    if not m:
        raise ValueError(f"Time must look like 07:30, got {s!r}")
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h < 24 and 0 <= mi < 60):
        raise ValueError(f"Invalid time {s!r}")
    return h * 60 + mi


# ----- one-time upgrade of a Studio 0.1 data folder -----
_OLD_KINDS = {"class": "session", "break": "break"}  # assembly, pe and other become "other"


def _report_v1_to_v2(r: dict) -> dict:
    out = {k: v for k, v in r.items() if k not in ("class_code", "students", "weak_students")}
    out["group_code"] = r.get("class_code", "")
    out["people"] = r.get("students", [])
    out["weak_people"] = r.get("weak_students", [])
    metrics = dict(out.get("metrics", {}))
    if "wrong_student_rate" in metrics:
        metrics["wrong_person_rate"] = metrics.pop("wrong_student_rate")
    out["metrics"] = metrics
    out["photo_problems"] = [
        {"person": p.get("student", p.get("person", "")), "photo": p.get("photo", ""), "problem": p.get("problem", "")}
        for p in r.get("photo_problems", [])
    ]
    return out


def migrate_v1(root: Path) -> bool:
    """Convert a Studio 0.1 data folder (school, classes, students, periods) to the 0.2 layout, once.

    Safe to run again after an interruption: org.json is written last, and the old school.json is removed only
    after it. Returns True when something was converted."""
    old = root / "school.json"
    if not old.exists() or (root / "org.json").exists():
        return False
    from . import groupmodel  # here, so that storage does not need numpy for normal use

    school = _read_json(old, {})
    backup = root / "backup-0.1"
    backup.mkdir(exist_ok=True)
    shutil.copy2(old, backup / "school.json")
    src = root / "screens" if (root / "screens").exists() else root / "groups"
    converted = 0
    for d in sorted(src.iterdir()) if src.exists() else []:
        class_json = d / "class.json"
        if not class_json.exists():
            continue
        c = _read_json(class_json, {})
        (backup / d.name).mkdir(exist_ok=True)
        shutil.copy2(class_json, backup / d.name / "class.json")
        group = Group(
            code=c["code"],
            name=c["code"],
            room=c.get("room", ""),
            people=[Person(**s) for s in c.get("students", [])],
            timetable=c.get("timetable", {}),
        )
        _write_json(d / "group.json", group.to_json())
        old_model = d / "model" / "class-model.json"
        if old_model.exists():
            groupmodel.write(
                d / "model" / groupmodel.FILE_NAME, groupmodel.from_v1(json.loads(old_model.read_text("utf-8")))
            )
            old_model.unlink()
        report = d / "model" / "report.json"
        if report.exists():
            _write_json(report, _report_v1_to_v2(_read_json(report, {})))
        class_json.unlink()
        converted += 1
    if src.name == "screens":
        src.rename(root / "groups")

    settings = dict(school.get("settings", {}))
    if "photos_per_student" in settings:
        settings["photos_per_person"] = settings.pop("photos_per_student")
    if settings.get("board_admin_pin") == "2468":  # the old default PIN: a new one must be chosen
        settings["board_admin_pin"] = ""
    settings["settings_version"] = 3
    _write_json(
        root / "org.json",
        {
            "format": "ssas.org",
            "version": FORMAT_VERSION,
            "name": school.get("school_name", ""),
            "days": school.get("school_days", [1, 2, 3, 4, 5]),
            "sessions": [{**p, "kind": _OLD_KINDS.get(p.get("kind"), "other")} for p in school.get("bell", [])],
            "shared_rooms": school.get("labs", []),
            "settings": settings,
            "board_tokens": school.get("board_tokens", {}),
        },
    )
    old.unlink()
    log.info("Converted the Studio 0.1 data folder %s (%d groups); old files kept in %s", root, converted, backup)
    return True

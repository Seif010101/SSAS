"""School data on the laptop: plain folders and JSON files.

    <data root>/
        school.json                     school name, days, bell times, settings, labs
        screens/
            9A1/
                class.json              class info, students, timetable
                Ahmed Ali/              one folder per student with their photos
                    20261026-101500-03-left.jpg
                model/
                    class-model.json    the trained model for this class only
                    report.json         training report
                    embeddings.npz      cached embeddings (used as "strangers" for other classes)
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

FORMAT_VERSION = 1
PHOTO_EXT = ".jpg"

PERIOD_KINDS = ("class", "break", "assembly", "pe", "other")
DEFAULT_BELL = [
    {"number": 1, "start": "07:30", "end": "08:15", "kind": "class"},
    {"number": 2, "start": "08:20", "end": "09:05", "kind": "class"},
    {"number": 3, "start": "09:10", "end": "09:55", "kind": "class"},
    {"number": 0, "start": "09:55", "end": "10:15", "kind": "break"},
    {"number": 4, "start": "10:15", "end": "11:00", "kind": "class"},
    {"number": 5, "start": "11:05", "end": "11:50", "kind": "class"},
    {"number": 6, "start": "11:55", "end": "12:40", "kind": "class"},
]
DAY_NAMES = {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat", 7: "Sun"}

_CODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,15}$")
_BAD_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_FOLDERS = {"model"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_folder_name(name: str) -> str:
    """A Windows-safe folder name that keeps Arabic and other letters."""
    clean = _BAD_NAME_CHARS.sub("_", name).strip().rstrip(".")
    clean = re.sub(r"\s+", " ", clean)
    if not clean or clean.lower() in RESERVED_FOLDERS:
        clean = f"_{clean or 'student'}"
    return clean[:80]


def valid_code(code: str) -> bool:
    return bool(_CODE_RE.match(code))


def _read_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


@dataclass
class Settings:
    capture_offset_min: float = 3.0
    capture_window_min: float = 5.0
    shot_schedule_s: list[int] = field(default_factory=lambda: [0, 10, 25, 45, 75, 120, 180, 240])
    min_valid_frames: int = 3
    epochs: int = 200
    augment_per_photo: int = 10
    folds: int = 5
    seeds: int = 3
    min_accuracy: float = 0.98
    photos_per_student: int = 40
    strict_order: bool = False  # capture: ring parts must be followed in a random order (anti-cheat)
    settings_version: int = 2
    server_url: str = ""
    server_cert_sha256: str = ""
    board_admin_pin: str = "2468"
    sound: bool = True


@dataclass
class Student:
    id: str
    name: str
    folder: str


@dataclass
class SchoolClass:
    code: str
    grade: int
    track: str
    section: int
    room: str = ""
    students: list[Student] = field(default_factory=list)
    # timetable[day][period] = "here" | "skip" | <lab code>; missing = "here" for class periods
    timetable: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_json(self) -> dict:
        d = asdict(self)
        d["format"] = "ssas.class"
        d["version"] = FORMAT_VERSION
        return d

    @staticmethod
    def from_json(d: dict) -> "SchoolClass":
        return SchoolClass(
            code=d["code"],
            grade=int(d.get("grade", 0)),
            track=d.get("track", ""),
            section=int(d.get("section", 0)),
            room=d.get("room", ""),
            students=[Student(**s) for s in d.get("students", [])],
            timetable=d.get("timetable", {}),
        )


class School:
    """Everything stored under one data folder."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.screens = self.root / "screens"
        self.screens.mkdir(parents=True, exist_ok=True)
        self._school = _read_json(self.root / "school.json", None)
        if self._school is None:
            self._school = {
                "format": "ssas.school",
                "version": FORMAT_VERSION,
                "school_name": "My School",
                "school_days": [1, 2, 3, 4, 5],
                "bell": DEFAULT_BELL,
                "labs": [],
                "settings": asdict(Settings()),
                "board_tokens": {},
            }
            self.save_school()

    # ----- school-level -----
    def save_school(self) -> None:
        _write_json(self.root / "school.json", self._school)

    @property
    def name(self) -> str:
        return self._school.get("school_name", "")

    @name.setter
    def name(self, value: str) -> None:
        self._school["school_name"] = value.strip()
        self.save_school()

    @property
    def school_days(self) -> list[int]:
        return list(self._school.get("school_days", [1, 2, 3, 4, 5]))

    @school_days.setter
    def school_days(self, days: list[int]) -> None:
        self._school["school_days"] = sorted({int(d) for d in days if 1 <= int(d) <= 7})
        self.save_school()

    @property
    def bell(self) -> list[dict]:
        return list(self._school.get("bell", []))

    @bell.setter
    def bell(self, rows: list[dict]) -> None:
        clean = []
        for r in rows:
            kind = r.get("kind", "class")
            if kind not in PERIOD_KINDS:
                raise ValueError(f"Unknown period type: {kind}")
            _parse_hhmm(r["start"])
            _parse_hhmm(r["end"])
            if _parse_hhmm(r["end"]) <= _parse_hhmm(r["start"]):
                raise ValueError(f"Period {r.get('number')}: end must be after start")
            clean.append({"number": int(r.get("number", 0)), "start": r["start"], "end": r["end"], "kind": kind})
        clean.sort(key=lambda r: _parse_hhmm(r["start"]))
        self._school["bell"] = clean
        self.save_school()

    def class_periods(self) -> list[dict]:
        return [p for p in self.bell if p["kind"] == "class"]

    @property
    def labs(self) -> list[dict]:
        return list(self._school.get("labs", []))

    def add_lab(self, code: str, name: str) -> None:
        if not valid_code(code):
            raise ValueError("Lab code may contain letters, digits, - and _ only (max 16).")
        if code in self.class_codes() or any(l["code"] == code for l in self.labs):
            raise ValueError(f"The code {code} is already used.")
        self._school.setdefault("labs", []).append({"code": code, "name": name})
        self.save_school()

    def remove_lab(self, code: str) -> None:
        self._school["labs"] = [l for l in self.labs if l["code"] != code]
        self.save_school()

    @property
    def settings(self) -> Settings:
        base = asdict(Settings())
        stored = self._school.get("settings", {})
        base.update(stored)
        if stored.get("settings_version", 1) < 2 and base["photos_per_student"] == 80:
            base["photos_per_student"] = 40  # the old default; capture is now shorter
        return Settings(**{k: base[k] for k in asdict(Settings())})

    @settings.setter
    def settings(self, s: Settings) -> None:
        self._school["settings"] = asdict(s)
        self.save_school()

    def board_token(self, board_code: str) -> str:
        tokens = self._school.setdefault("board_tokens", {})
        if board_code not in tokens:
            tokens[board_code] = secrets.token_urlsafe(32)
            self.save_school()
        return tokens[board_code]

    def new_board_token(self, board_code: str) -> None:
        """Replace a board's server key, e.g. after a USB stick was lost."""
        self._school.setdefault("board_tokens", {})[board_code] = secrets.token_urlsafe(32)
        self.save_school()

    # ----- classes -----
    def class_codes(self) -> list[str]:
        return sorted(p.name for p in self.screens.iterdir() if (p / "class.json").exists())

    def class_dir(self, code: str) -> Path:
        return self.screens / code

    def load_class(self, code: str) -> SchoolClass:
        return SchoolClass.from_json(_read_json(self.class_dir(code) / "class.json", None))

    def save_class(self, c: SchoolClass) -> None:
        _write_json(self.class_dir(c.code) / "class.json", c.to_json())

    def add_class(self, code: str, grade: int, track: str, section: int, room: str = "") -> SchoolClass:
        if not valid_code(code):
            raise ValueError("Class code may contain letters, digits, - and _ only (max 16), e.g. 9A1.")
        if (self.class_dir(code) / "class.json").exists() or any(l["code"] == code for l in self.labs):
            raise ValueError(f"The code {code} is already used.")
        c = SchoolClass(code=code, grade=grade, track=track, section=section, room=room)
        self.save_class(c)
        return c

    def delete_class(self, code: str) -> None:
        shutil.rmtree(self.class_dir(code), ignore_errors=True)

    # ----- students -----
    def add_student(self, code: str, name: str) -> Student:
        name = " ".join(name.split())
        if not name:
            raise ValueError("Student name is empty.")
        c = self.load_class(code)
        if any(s.name == name for s in c.students):
            raise ValueError(f"{name} is already in {code}.")
        folder = safe_folder_name(name)
        existing = {s.folder for s in c.students}
        base, n = folder, 2
        while folder in existing:
            folder = f"{base} ({n})"
            n += 1
        num = 1 + max([int(s.id.rsplit("-", 1)[-1]) for s in c.students if s.id.rsplit("-", 1)[-1].isdigit()] or [0])
        st = Student(id=f"{code}-{num:03d}", name=name, folder=folder)
        c.students.append(st)
        (self.class_dir(code) / folder).mkdir(parents=True, exist_ok=True)
        self.save_class(c)
        return st

    def rename_student(self, code: str, student_id: str, new_name: str) -> None:
        c = self.load_class(code)
        for s in c.students:
            if s.id == student_id:
                s.name = " ".join(new_name.split())
        self.save_class(c)

    def remove_student(self, code: str, student_id: str) -> None:
        c = self.load_class(code)
        keep = []
        for s in c.students:
            if s.id == student_id:
                shutil.rmtree(self.class_dir(code) / s.folder, ignore_errors=True)
            else:
                keep.append(s)
        c.students = keep
        self.save_class(c)

    def student_dir(self, code: str, student: Student) -> Path:
        return self.class_dir(code) / student.folder

    def photos(self, code: str, student: Student) -> list[Path]:
        d = self.student_dir(code, student)
        return sorted(d.glob(f"*{PHOTO_EXT}")) if d.exists() else []

    def clear_photos(self, code: str, student: Student) -> None:
        for p in self.photos(code, student):
            p.unlink(missing_ok=True)

    # ----- model -----
    def model_dir(self, code: str) -> Path:
        return self.class_dir(code) / "model"

    def report(self, code: str) -> dict | None:
        return _read_json(self.model_dir(code) / "report.json", None)


def import_students(path: Path) -> list[str]:
    """Read student names from .xlsx / .csv / .txt (first column, header row optional)."""
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

        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.reader(f):
                if row and row[0].strip():
                    names.append(row[0])
    names = [" ".join(n.split()) for n in names if n and n.strip()]
    if names and names[0].lower() in {"name", "student", "student name", "الاسم", "اسم الطالب"}:
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

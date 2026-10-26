"""School days, bell times, labs and the weekly timetable of each class."""

from __future__ import annotations

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QListWidget,
    QPushButton, QSpinBox, QTableWidget, QTimeEdit, QVBoxLayout, QWidget, QScrollArea,
)

from ..core.export import board_plans
from ..core.storage import DAY_NAMES, PERIOD_KINDS
from .common import danger, error, info, muted, primary, title
from .context import AppContext

KIND_LABELS = {"class": "Lesson (counted)", "break": "Break", "assembly": "Assembly", "pe": "PE / sports", "other": "Other (not counted)"}
HERE = "Counted in class"
SKIP = "Not counted"


class ScheduleTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        scroll.setWidget(inner)
        root = QVBoxLayout(inner)
        root.addWidget(title("Schedule"))
        root.addWidget(muted(
            "Each board reads its own timetable from the USB. The camera opens a few minutes after a counted "
            "lesson starts, takes attendance once, then closes. Breaks, assembly and PE are never counted."
        ))

        top = QHBoxLayout()
        days = QGroupBox("School days")
        dl = QHBoxLayout(days)
        self.day_boxes = {}
        for d, name in DAY_NAMES.items():
            cb = QCheckBox(name)
            cb.toggled.connect(self.save_days)
            self.day_boxes[d] = cb
            dl.addWidget(cb)
        top.addWidget(days, 2)
        labs = QGroupBox("Labs with a board")
        ll = QVBoxLayout(labs)
        self.lab_list = QListWidget()
        self.lab_list.setMaximumHeight(90)
        ll.addWidget(self.lab_list)
        lr = QHBoxLayout()
        add_lab = QPushButton("Add lab")
        add_lab.clicked.connect(self.add_lab)
        rm_lab = danger("Remove")
        rm_lab.clicked.connect(self.remove_lab)
        lr.addWidget(add_lab)
        lr.addWidget(rm_lab)
        ll.addLayout(lr)
        top.addWidget(labs, 1)
        root.addLayout(top)

        bell = QGroupBox("Bell times (same every school day)")
        bl = QVBoxLayout(bell)
        self.bell_table = QTableWidget(0, 4)
        self.bell_table.setHorizontalHeaderLabels(["Period no.", "Start", "End", "Type"])
        self.bell_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.bell_table.verticalHeader().setVisible(False)
        self.bell_table.setMinimumHeight(260)
        bl.addWidget(self.bell_table)
        br = QHBoxLayout()
        add_p = QPushButton("Add row")
        add_p.clicked.connect(lambda: self._add_bell_row({"number": self.bell_table.rowCount() + 1, "start": "08:00", "end": "08:45", "kind": "class"}))
        rm_p = danger("Remove selected row")
        rm_p.clicked.connect(lambda: self.bell_table.removeRow(self.bell_table.currentRow()))
        save_b = primary("Save bell times")
        save_b.clicked.connect(self.save_bell)
        br.addWidget(add_p)
        br.addWidget(rm_p)
        br.addStretch(1)
        br.addWidget(save_b)
        bl.addLayout(br)
        root.addWidget(bell)

        tt = QGroupBox("Weekly timetable of a class")
        tl = QVBoxLayout(tt)
        tr = QHBoxLayout()
        self.class_box = QComboBox()
        self.class_box.currentTextChanged.connect(self.load_timetable)
        tr.addWidget(QLabel("Class"))
        tr.addWidget(self.class_box, 1)
        save_t = primary("Save timetable")
        save_t.clicked.connect(self.save_timetable)
        tr.addWidget(save_t)
        tl.addLayout(tr)
        tl.addWidget(muted(f"“{HERE}” = the class's own board takes attendance. “{SKIP}” = PE or another lesson "
                           "outside a room with a board. A lab name = the lab's board takes attendance."))
        self.tt_table = QTableWidget(0, 0)
        self.tt_table.setMinimumHeight(260)
        tl.addWidget(self.tt_table)
        self.problems = muted("")
        tl.addWidget(self.problems)
        root.addWidget(tt)

        ctx.classes_changed.connect(self.refresh)
        ctx.settings_changed.connect(self.refresh)
        self.refresh()

    # ----- load -----
    def refresh(self):
        school = self.ctx.school
        for d, cb in self.day_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(d in school.school_days)
            cb.blockSignals(False)
        self.lab_list.clear()
        for l in school.labs:
            self.lab_list.addItem(f"{l['code']} — {l['name']}")
        self.bell_table.setRowCount(0)
        for row in school.bell:
            self._add_bell_row(row)
        cur = self.class_box.currentText()
        self.class_box.blockSignals(True)
        self.class_box.clear()
        self.class_box.addItems(school.class_codes())
        if cur:
            self.class_box.setCurrentText(cur)
        self.class_box.blockSignals(False)
        self.load_timetable(self.class_box.currentText())

    def _add_bell_row(self, row: dict):
        r = self.bell_table.rowCount()
        self.bell_table.insertRow(r)
        num = QSpinBox()
        num.setRange(0, 20)
        num.setValue(int(row["number"]))
        start = QTimeEdit(QTime.fromString(row["start"], "HH:mm"))
        start.setDisplayFormat("HH:mm")
        end = QTimeEdit(QTime.fromString(row["end"], "HH:mm"))
        end.setDisplayFormat("HH:mm")
        kind = QComboBox()
        for k in PERIOD_KINDS:
            kind.addItem(KIND_LABELS[k], k)
        kind.setCurrentIndex(PERIOD_KINDS.index(row["kind"]))
        for c, w in enumerate((num, start, end, kind)):
            self.bell_table.setCellWidget(r, c, w)

    def load_timetable(self, code: str):
        school = self.ctx.school
        days = school.school_days
        periods = school.class_periods()
        self.tt_table.clear()
        self.tt_table.setColumnCount(len(days))
        self.tt_table.setRowCount(len(periods))
        self.tt_table.setHorizontalHeaderLabels([DAY_NAMES[d] for d in days])
        self.tt_table.setVerticalHeaderLabels([f"Period {p['number']}  {p['start']}–{p['end']}" for p in periods])
        self.tt_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if not code:
            return
        c = school.load_class(code)
        labs = [l["code"] for l in school.labs]
        for r, p in enumerate(periods):
            for col, d in enumerate(days):
                box = QComboBox()
                box.addItem(HERE, "here")
                box.addItem(SKIP, "skip")
                for lab in labs:
                    box.addItem(f"In {lab}", lab)
                val = c.timetable.get(str(d), {}).get(str(p["number"]), "here")
                i = box.findData(val)
                box.setCurrentIndex(i if i >= 0 else 0)
                self.tt_table.setCellWidget(r, col, box)
        self._show_problems()

    def _show_problems(self):
        _, problems = board_plans(self.ctx.school)
        self.problems.setText("⚠ " + " · ".join(problems) if problems else "No timetable conflicts.")

    # ----- save -----
    def save_days(self):
        self.ctx.school.school_days = [d for d, cb in self.day_boxes.items() if cb.isChecked()]
        self.load_timetable(self.class_box.currentText())

    def save_bell(self):
        rows = []
        for r in range(self.bell_table.rowCount()):
            num, start, end, kind = (self.bell_table.cellWidget(r, c) for c in range(4))
            rows.append({"number": num.value(), "start": start.time().toString("HH:mm"),
                         "end": end.time().toString("HH:mm"), "kind": kind.currentData()})
        numbers = [r["number"] for r in rows if r["kind"] == "class"]
        if len(numbers) != len(set(numbers)):
            return error(self, "Two lessons have the same period number.")
        try:
            self.ctx.school.bell = rows
        except ValueError as e:
            return error(self, str(e))
        self.ctx.settings_changed.emit()
        info(self, "Bell times saved.")

    def save_timetable(self):
        code = self.class_box.currentText()
        if not code:
            return
        school = self.ctx.school
        c = school.load_class(code)
        tt: dict[str, dict[str, str]] = {}
        for r, p in enumerate(school.class_periods()):
            for col, d in enumerate(school.school_days):
                val = self.tt_table.cellWidget(r, col).currentData()
                if val != "here":
                    tt.setdefault(str(d), {})[str(p["number"])] = val
        c.timetable = tt
        school.save_class(c)
        self._show_problems()
        info(self, f"Timetable of {code} saved.")

    def add_lab(self):
        code, ok = QInputDialog.getText(self, "Add lab", "Lab code (e.g. LAB1):")
        if not ok or not code.strip():
            return
        name, ok = QInputDialog.getText(self, "Add lab", "Lab name (e.g. Physics lab):")
        try:
            self.ctx.school.add_lab(code.strip(), name.strip() if ok else "")
        except ValueError as e:
            return error(self, str(e))
        self.refresh()

    def remove_lab(self):
        it = self.lab_list.currentItem()
        if it:
            self.ctx.school.remove_lab(it.text().split(" — ")[0])
            self.refresh()

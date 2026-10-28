"""School days, bell times, labs and the weekly timetable of each class."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QListWidget,
    QPushButton, QTableWidget, QTimeEdit, QVBoxLayout, QWidget, QScrollArea,
)

from ..core.export import board_plans
from ..core.storage import DAY_NAMES, PERIOD_KINDS
from .common import confirm, danger, error, info, muted, primary, title
from .context import AppContext

KIND_LABELS = {"class": "Lesson (counted)", "break": "Break", "assembly": "Assembly", "pe": "PE / sports", "other": "Other (not counted)"}
HERE = "Here"
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
        top.addWidget(days, 2, Qt.AlignTop)
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
        top.addWidget(labs, 1, Qt.AlignTop)
        root.addLayout(top)

        bell = QGroupBox("Bell times (same every school day)")
        bl = QVBoxLayout(bell)
        bl.addWidget(muted("Lessons are numbered automatically in time order. Only “Lesson” rows take attendance."))
        self.bell_table = QTableWidget(0, 4)
        self.bell_table.setHorizontalHeaderLabels(["Lesson", "Start", "End", "Type"])
        head = self.bell_table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.Fixed)
        head.setSectionResizeMode(3, QHeaderView.Stretch)
        for col, w in ((0, 90), (1, 130), (2, 130)):
            self.bell_table.setColumnWidth(col, w)
        self.bell_table.verticalHeader().setVisible(False)
        self.bell_table.verticalHeader().setDefaultSectionSize(40)
        self.bell_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.bell_table.setMinimumHeight(340)
        bl.addWidget(self.bell_table)
        br = QHBoxLayout()
        add_p = QPushButton("Add row")
        add_p.clicked.connect(self.add_bell_row)
        rm_p = danger("Remove selected row")
        rm_p.clicked.connect(self.remove_bell_row)
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
        copy_t = QPushButton("Copy to all classes")
        copy_t.setToolTip("Give every class the same timetable as this one")
        copy_t.clicked.connect(self.copy_timetable)
        save_t = primary("Save timetable")
        save_t.clicked.connect(self.save_timetable)
        tr.addWidget(copy_t)
        tr.addWidget(save_t)
        tl.addLayout(tr)
        tl.addWidget(muted(f"“{HERE}” = the class's own board takes attendance. “{SKIP}” (amber) = PE or another lesson "
                           "outside a room with a board. “In LAB…” (teal) = the lab's board takes attendance."))
        self.tt_table = QTableWidget(0, 0)
        self.tt_table.setMinimumHeight(300)
        self.tt_table.verticalHeader().setDefaultSectionSize(38)
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
        number = QLabel()
        number.setAlignment(Qt.AlignCenter)
        start = QTimeEdit(QTime.fromString(row["start"], "HH:mm"))
        start.setDisplayFormat("HH:mm")
        end = QTimeEdit(QTime.fromString(row["end"], "HH:mm"))
        end.setDisplayFormat("HH:mm")
        kind = QComboBox()
        for k in PERIOD_KINDS:
            kind.addItem(KIND_LABELS[k], k)
        kind.setCurrentIndex(PERIOD_KINDS.index(row["kind"]))
        kind.currentIndexChanged.connect(self._renumber)
        for c, w in enumerate((number, start, end, kind)):
            self.bell_table.setCellWidget(r, c, w)
        self._renumber()

    def _renumber(self, *_):
        """Lessons are numbered 1, 2, 3… in table order. The other rows show a dash."""
        n = 0
        for r in range(self.bell_table.rowCount()):
            label = self.bell_table.cellWidget(r, 0)
            if self.bell_table.cellWidget(r, 3).currentData() == "class":
                n += 1
                label.setText(str(n))
            else:
                label.setText("—")

    def add_bell_row(self):
        count = self.bell_table.rowCount()
        start = QTime(8, 0)
        if count:
            start = self.bell_table.cellWidget(count - 1, 2).time().addSecs(5 * 60)
        self._add_bell_row({"number": 0, "start": start.toString("HH:mm"),
                            "end": start.addSecs(45 * 60).toString("HH:mm"), "kind": "class"})
        self.bell_table.selectRow(count)

    def remove_bell_row(self):
        r = self.bell_table.currentRow()
        if r >= 0:
            self.bell_table.removeRow(r)
            self._renumber()

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
                box.currentIndexChanged.connect(lambda _i, b=box: self._paint_cell(b))
                self._paint_cell(box)
                self.tt_table.setCellWidget(r, col, box)
        self._show_problems()

    @staticmethod
    def _paint_cell(box: QComboBox):
        val = box.currentData()
        box.setProperty("cell", "here" if val == "here" else "skip" if val == "skip" else "lab")
        box.style().unpolish(box)
        box.style().polish(box)

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
            _, start, end, kind = (self.bell_table.cellWidget(r, c) for c in range(4))
            rows.append({"number": 0, "start": start.time().toString("HH:mm"),
                         "end": end.time().toString("HH:mm"), "kind": kind.currentData()})
        rows.sort(key=lambda x: x["start"])
        n = 0
        for row in rows:
            if row["kind"] == "class":
                n += 1
                row["number"] = n
        try:
            self.ctx.school.bell = rows
        except ValueError as e:
            return error(self, str(e))
        self.ctx.settings_changed.emit()
        info(self, "Bell times saved.")

    def save_timetable(self, quiet: bool = False):
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
        if quiet is not True:
            info(self, f"Timetable of {code} saved.")

    def copy_timetable(self):
        code = self.class_box.currentText()
        codes = [c for c in self.ctx.school.class_codes() if c != code]
        if not code or not codes:
            return error(self, "There is no other class to copy to.")
        if not confirm(self, f"Give all {len(codes)} other classes the same timetable as {code}?\n"
                             "Their current timetables will be replaced."):
            return
        self.save_timetable(quiet=True)
        tt = self.ctx.school.load_class(code).timetable
        for other in codes:
            c = self.ctx.school.load_class(other)
            c.timetable = {d: dict(v) for d, v in tt.items()}
            self.ctx.school.save_class(c)
        self._show_problems()
        info(self, f"Timetable of {code} copied to {len(codes)} classes.")

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

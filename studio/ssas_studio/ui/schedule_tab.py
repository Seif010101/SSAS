"""Working days, session times, shared rooms and the weekly timetable of each group."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..core.export import board_plans
from ..core.storage import DAY_NAMES, SESSION_KINDS
from .common import GroupPicker, confirm, danger, error, info, muted, primary, title
from .context import AppContext

KIND_LABELS = {
    "session": "Session (attendance taken)",
    "break": "Break",
    "other": "Other (not counted)",
}
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
        root.addWidget(
            muted(
                "Each screen reads its own timetable from the USB. The camera opens a few minutes after a session "
                "starts, takes attendance once, then closes. Breaks and “Other” rows are never counted."
            )
        )

        top = QHBoxLayout()
        days = QGroupBox("Working days")
        dl = QHBoxLayout(days)
        self.day_boxes = {}
        for d, name in DAY_NAMES.items():
            cb = QCheckBox(name)
            cb.toggled.connect(self.save_days)
            self.day_boxes[d] = cb
            dl.addWidget(cb)
        top.addWidget(days, 2, Qt.AlignTop)
        rooms = QGroupBox("Shared rooms with a screen (a lab, a hall…)")
        ll = QVBoxLayout(rooms)
        self.room_list = QListWidget()
        self.room_list.setMaximumHeight(90)
        ll.addWidget(self.room_list)
        lr = QHBoxLayout()
        add_room = QPushButton("Add room")
        add_room.clicked.connect(self.add_room)
        rm_room = danger("Remove")
        rm_room.clicked.connect(self.remove_room)
        lr.addWidget(add_room)
        lr.addWidget(rm_room)
        ll.addLayout(lr)
        top.addWidget(rooms, 1, Qt.AlignTop)
        root.addLayout(top)

        times = QGroupBox("Session times (the same every working day)")
        bl = QVBoxLayout(times)
        bl.addWidget(muted("Sessions are numbered automatically in time order. Only “Session” rows take attendance."))
        self.times_table = QTableWidget(0, 4)
        self.times_table.setHorizontalHeaderLabels(["Session", "Start", "End", "Type"])
        head = self.times_table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.Fixed)
        head.setSectionResizeMode(3, QHeaderView.Stretch)
        for col, w in ((0, 90), (1, 130), (2, 130)):
            self.times_table.setColumnWidth(col, w)
        self.times_table.verticalHeader().setVisible(False)
        self.times_table.verticalHeader().setDefaultSectionSize(40)
        self.times_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.times_table.setMinimumHeight(340)
        bl.addWidget(self.times_table)
        br = QHBoxLayout()
        add_p = QPushButton("Add row")
        add_p.clicked.connect(self.add_time_row)
        rm_p = danger("Remove selected row")
        rm_p.clicked.connect(self.remove_time_row)
        save_b = primary("Save session times")
        save_b.clicked.connect(self.save_times)
        br.addWidget(add_p)
        br.addWidget(rm_p)
        br.addStretch(1)
        br.addWidget(save_b)
        bl.addLayout(br)
        root.addWidget(times)

        tt = QGroupBox("Weekly timetable of a group")
        tl = QVBoxLayout(tt)
        tr = QHBoxLayout()
        self.group_box = GroupPicker(ctx)
        self.group_box.changed.connect(self.load_timetable)
        tr.addWidget(QLabel("Group"))
        tr.addWidget(self.group_box, 1)
        copy_t = QPushButton("Copy to all groups")
        copy_t.setToolTip("Give every group the same timetable as this one")
        copy_t.clicked.connect(self.copy_timetable)
        save_t = primary("Save timetable")
        save_t.clicked.connect(self.save_timetable)
        tr.addWidget(copy_t)
        tr.addWidget(save_t)
        tl.addLayout(tr)
        tl.addWidget(
            muted(
                f"“{HERE}” = the screen in the group's own room takes attendance. “{SKIP}” (amber) = the group is "
                "somewhere without a screen. “In ROOM…” (teal) = the screen of that shared room takes attendance."
            )
        )
        self.tt_table = QTableWidget(0, 0)
        self.tt_table.setMinimumHeight(300)
        self.tt_table.verticalHeader().setDefaultSectionSize(38)
        tl.addWidget(self.tt_table)
        self.problems = muted("")
        tl.addWidget(self.problems)
        root.addWidget(tt)

        ctx.groups_changed.connect(self.refresh)
        ctx.settings_changed.connect(self.refresh)
        self.refresh()

    # ----- load -----
    def refresh(self):
        org = self.ctx.org
        for d, cb in self.day_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(d in org.days)
            cb.blockSignals(False)
        self.room_list.clear()
        for room in org.shared_rooms:
            self.room_list.addItem(f"{room['code']} — {room['name']}")
        self.times_table.setRowCount(0)
        for row in org.sessions:
            self._add_time_row(row)
        self.load_timetable(self.group_box.code)

    def _add_time_row(self, row: dict):
        r = self.times_table.rowCount()
        self.times_table.insertRow(r)
        number = QLabel()
        number.setAlignment(Qt.AlignCenter)
        start = QTimeEdit(QTime.fromString(row["start"], "HH:mm"))
        start.setDisplayFormat("HH:mm")
        end = QTimeEdit(QTime.fromString(row["end"], "HH:mm"))
        end.setDisplayFormat("HH:mm")
        kind = QComboBox()
        for k in SESSION_KINDS:
            kind.addItem(KIND_LABELS[k], k)
        kind.setCurrentIndex(SESSION_KINDS.index(row["kind"]))
        kind.currentIndexChanged.connect(self._renumber)
        for c, w in enumerate((number, start, end, kind)):
            self.times_table.setCellWidget(r, c, w)
        self._renumber()

    def _renumber(self, *_):
        """Sessions are numbered 1, 2, 3… in table order. The other rows show a dash."""
        n = 0
        for r in range(self.times_table.rowCount()):
            label = self.times_table.cellWidget(r, 0)
            if self.times_table.cellWidget(r, 3).currentData() == "session":
                n += 1
                label.setText(str(n))
            else:
                label.setText("—")

    def add_time_row(self):
        count = self.times_table.rowCount()
        start = QTime(8, 0)
        if count:
            start = self.times_table.cellWidget(count - 1, 2).time().addSecs(5 * 60)
        self._add_time_row(
            {
                "number": 0,
                "start": start.toString("HH:mm"),
                "end": start.addSecs(45 * 60).toString("HH:mm"),
                "kind": "session",
            }
        )
        self.times_table.selectRow(count)

    def remove_time_row(self):
        r = self.times_table.currentRow()
        if r >= 0:
            self.times_table.removeRow(r)
            self._renumber()

    def load_timetable(self, code: str):
        org = self.ctx.org
        days = org.days
        sessions = org.attendance_sessions()
        self.tt_table.clear()
        self.tt_table.setColumnCount(len(days))
        self.tt_table.setRowCount(len(sessions))
        self.tt_table.setHorizontalHeaderLabels([DAY_NAMES[d] for d in days])
        self.tt_table.setVerticalHeaderLabels([f"Session {s['number']}  {s['start']}–{s['end']}" for s in sessions])
        self.tt_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        if not code:
            return
        g = org.load_group(code)
        rooms = [room["code"] for room in org.shared_rooms]
        for r, s in enumerate(sessions):
            for col, d in enumerate(days):
                box = QComboBox()
                box.addItem(HERE, "here")
                box.addItem(SKIP, "skip")
                for room in rooms:
                    box.addItem(f"In {room}", room)
                val = g.timetable.get(str(d), {}).get(str(s["number"]), "here")
                i = box.findData(val)
                box.setCurrentIndex(i if i >= 0 else 0)
                box.currentIndexChanged.connect(lambda _i, b=box: self._paint_cell(b))
                self._paint_cell(box)
                self.tt_table.setCellWidget(r, col, box)
        self._show_problems()

    @staticmethod
    def _paint_cell(box: QComboBox):
        val = box.currentData()
        box.setProperty("cell", "here" if val == "here" else "skip" if val == "skip" else "room")
        box.style().unpolish(box)
        box.style().polish(box)

    def _show_problems(self):
        _, problems = board_plans(self.ctx.org)
        self.problems.setText("⚠ " + " · ".join(problems) if problems else "No timetable conflicts.")

    # ----- save -----
    def save_days(self):
        self.ctx.org.days = [d for d, cb in self.day_boxes.items() if cb.isChecked()]
        self.load_timetable(self.group_box.code)

    def save_times(self):
        rows = []
        for r in range(self.times_table.rowCount()):
            _, start, end, kind = (self.times_table.cellWidget(r, c) for c in range(4))
            rows.append(
                {
                    "number": 0,
                    "start": start.time().toString("HH:mm"),
                    "end": end.time().toString("HH:mm"),
                    "kind": kind.currentData(),
                }
            )
        rows.sort(key=lambda x: x["start"])
        n = 0
        for row in rows:
            if row["kind"] == "session":
                n += 1
                row["number"] = n
        try:
            self.ctx.org.sessions = rows
        except ValueError as e:
            return error(self, str(e))
        self.ctx.settings_changed.emit()
        info(self, "Session times saved.")

    def save_timetable(self, quiet: bool = False):
        code = self.group_box.code
        if not code:
            return
        org = self.ctx.org
        g = org.load_group(code)
        tt: dict[str, dict[str, str]] = {}
        for r, s in enumerate(org.attendance_sessions()):
            for col, d in enumerate(org.days):
                val = self.tt_table.cellWidget(r, col).currentData()
                if val != "here":
                    tt.setdefault(str(d), {})[str(s["number"])] = val
        g.timetable = tt
        org.save_group(g)
        self._show_problems()
        if quiet is not True:
            info(self, f"Timetable of {code} saved.")

    def copy_timetable(self):
        code = self.group_box.code
        codes = [c for c in self.ctx.org.group_codes() if c != code]
        if not code or not codes:
            return error(self, "There is no other group to copy to.")
        if not confirm(
            self,
            f"Give all {len(codes)} other groups the same timetable as {code}?\n"
            "Their current timetables will be replaced.",
        ):
            return
        self.save_timetable(quiet=True)
        tt = self.ctx.org.load_group(code).timetable
        for other in codes:
            g = self.ctx.org.load_group(other)
            g.timetable = {d: dict(v) for d, v in tt.items()}
            self.ctx.org.save_group(g)
        self._show_problems()
        info(self, f"Timetable of {code} copied to {len(codes)} groups.")

    def add_room(self):
        code, ok = QInputDialog.getText(self, "Add shared room", "Room code (e.g. LAB1, HALL):")
        if not ok or not code.strip():
            return
        name, ok = QInputDialog.getText(self, "Add shared room", "Room name (e.g. Physics lab, Main hall):")
        try:
            self.ctx.org.add_shared_room(code.strip(), name.strip() if ok else "")
        except ValueError as e:
            return error(self, str(e))
        self.refresh()

    def remove_room(self):
        it = self.room_list.currentItem()
        if it:
            self.ctx.org.remove_shared_room(it.text().split(" — ")[0])
            self.refresh()

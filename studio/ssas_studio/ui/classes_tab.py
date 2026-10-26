"""Classes and students."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog,
    QLineEdit, QListWidget, QListWidgetItem, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QAbstractItemView, QGroupBox,
)

from ..core.storage import import_students, valid_code
from . import theme
from .common import confirm, danger, error, info, muted, open_folder, primary, title
from .context import AppContext

TRACKS = ["Advanced", "General", "Elite", "—"]


def suggest_code(grade: int, track: str, section: int) -> str:
    letter = track[:1].upper() if track and track[0].isalpha() else ""
    return f"{grade}{letter}{section}"


class ClassDialog(QDialog):
    def __init__(self, parent=None, existing: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Class" if existing else "Add class")
        form = QFormLayout(self)
        self.grade = QSpinBox()
        self.grade.setRange(1, 12)
        self.grade.setValue(9)
        self.track = QComboBox()
        self.track.setEditable(True)
        self.track.addItems(TRACKS)
        self.section = QSpinBox()
        self.section.setRange(1, 99)
        self.code = QLineEdit()
        self.code.setPlaceholderText("e.g. 9A1")
        self.room = QLineEdit()
        self.room.setPlaceholderText("optional, e.g. Room 12")
        form.addRow("Grade", self.grade)
        form.addRow("Track", self.track)
        form.addRow("Section", self.section)
        form.addRow("Class code (folder name)", self.code)
        form.addRow("Room", self.room)
        self._auto = True
        if existing:
            self.grade.setValue(existing["grade"])
            self.track.setCurrentText(existing["track"])
            self.section.setValue(existing["section"])
            self.code.setText(existing["code"])
            self.code.setEnabled(False)
            self.room.setText(existing.get("room", ""))
            self._auto = False
        for w in (self.grade, self.section):
            w.valueChanged.connect(self._suggest)
        self.track.currentTextChanged.connect(self._suggest)
        self.code.textEdited.connect(lambda _: setattr(self, "_auto", False))
        self._suggest()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _suggest(self):
        if self._auto:
            self.code.setText(suggest_code(self.grade.value(), self.track.currentText(), self.section.value()))

    def _accept(self):
        if not valid_code(self.code.text().strip()):
            error(self, "The class code may only contain letters, digits, - and _ (max 16), e.g. 9A1.")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "code": self.code.text().strip(),
            "grade": self.grade.value(),
            "track": self.track.currentText().strip(),
            "section": self.section.value(),
            "room": self.room.text().strip(),
        }


class ClassesTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(title("Classes"))
        self.class_list = QListWidget()
        self.class_list.currentItemChanged.connect(lambda *_: self.refresh_students())
        left.addWidget(self.class_list, 1)
        row = QHBoxLayout()
        add = primary("Add class")
        add.clicked.connect(self.add_class)
        edit = self._btn("Edit", self.edit_class)
        delete = danger("Delete")
        delete.clicked.connect(self.delete_class)
        row.addWidget(add)
        row.addWidget(edit)
        row.addWidget(delete)
        left.addLayout(row)
        root.addLayout(left, 1)

        right = QVBoxLayout()
        self.class_title = title("—")
        self.class_info = muted()
        right.addWidget(self.class_title)
        right.addWidget(self.class_info)

        box = QGroupBox("Students")
        bl = QVBoxLayout(box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Photos", "Test accuracy"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        bl.addWidget(self.table)
        r2 = QHBoxLayout()
        r2.addWidget(self._btn("Add student", self.add_student, primary=True))
        r2.addWidget(self._btn("Import from Excel / CSV", self.import_students))
        r2.addWidget(self._btn("Rename", self.rename_student))
        rm = danger("Remove")
        rm.clicked.connect(self.remove_student)
        r2.addWidget(rm)
        r2.addStretch(1)
        r2.addWidget(self._btn("Open class folder", self.open_class_folder))
        bl.addLayout(r2)
        right.addWidget(box, 1)
        self.model_label = muted()
        right.addWidget(self.model_label)
        root.addLayout(right, 3)

        ctx.classes_changed.connect(self.refresh)
        ctx.photos_changed.connect(lambda _: self.refresh_students())
        ctx.model_changed.connect(lambda _: self.refresh_students())
        self.refresh()

    def _btn(self, text, fn, primary=False):
        from PySide6.QtWidgets import QPushButton

        b = QPushButton(text)
        if primary:
            b.setProperty("primary", True)
        b.clicked.connect(fn)
        return b

    # ----- data -----
    def current_code(self) -> str | None:
        it = self.class_list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def refresh(self):
        current = self.current_code()
        self.class_list.blockSignals(True)
        self.class_list.clear()
        school = self.ctx.school
        for code in school.class_codes():
            c = school.load_class(code)
            it = QListWidgetItem(f"{code}   ·   Grade {c.grade} {c.track} {c.section}   ·   {len(c.students)} students")
            it.setData(Qt.UserRole, code)
            self.class_list.addItem(it)
            if code == current:
                self.class_list.setCurrentItem(it)
        self.class_list.blockSignals(False)
        if self.class_list.currentItem() is None and self.class_list.count():
            self.class_list.setCurrentRow(0)
        self.refresh_students()

    def refresh_students(self):
        code = self.current_code()
        self.table.setRowCount(0)
        if not code:
            self.class_title.setText("No classes yet")
            self.class_info.setText("Click “Add class” to create the first class (for example 9A1).")
            self.model_label.setText("")
            return
        school = self.ctx.school
        c = school.load_class(code)
        self.class_title.setText(f"Class {code}")
        self.class_info.setText(f"Grade {c.grade} · {c.track} · Section {c.section}" + (f" · {c.room}" if c.room else ""))
        report = school.report(code)
        recall = {s["id"]: s.get("recall") for s in (report or {}).get("students", [])}
        target = school.settings.photos_per_student
        for s in c.students:
            n = len(school.photos(code, s))
            r = self.table.rowCount()
            self.table.insertRow(r)
            name = QTableWidgetItem(s.name)
            name.setData(Qt.UserRole, s.id)
            self.table.setItem(r, 0, name)
            p = QTableWidgetItem(f"{n} / {target}")
            p.setForeground(QColor(theme.OK if n >= target else theme.WARN if n else theme.BAD))
            self.table.setItem(r, 1, p)
            rc = recall.get(s.id)
            item = QTableWidgetItem("—" if rc is None else f"{rc * 100:.0f}%")
            if rc is not None:
                item.setForeground(QColor(theme.OK if rc >= 0.95 else theme.WARN if rc >= 0.9 else theme.BAD))
            self.table.setItem(r, 2, item)
        if report:
            m = report.get("metrics", {})
            self.model_label.setText(
                f"Model trained {report.get('created_at', '')[:16].replace('T', ' ')} · "
                f"accuracy {m.get('accuracy', 0) * 100:.1f}% · "
                + ("passed ✓" if report.get("passed") else "below the target — capture more photos and train again")
            )
        else:
            self.model_label.setText("No model yet — capture photos, then train this class.")

    def selected_student_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    # ----- actions -----
    def add_class(self):
        dlg = ClassDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        try:
            self.ctx.school.add_class(v["code"], v["grade"], v["track"], v["section"], v["room"])
        except ValueError as e:
            error(self, str(e))
            return
        self.ctx.classes_changed.emit()
        for i in range(self.class_list.count()):
            if self.class_list.item(i).data(Qt.UserRole) == v["code"]:
                self.class_list.setCurrentRow(i)

    def edit_class(self):
        code = self.current_code()
        if not code:
            return
        c = self.ctx.school.load_class(code)
        dlg = ClassDialog(self, {"code": c.code, "grade": c.grade, "track": c.track, "section": c.section, "room": c.room})
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        c.grade, c.track, c.section, c.room = v["grade"], v["track"], v["section"], v["room"]
        self.ctx.school.save_class(c)
        self.ctx.classes_changed.emit()

    def delete_class(self):
        code = self.current_code()
        if code and confirm(self, f"Delete class {code} with ALL its students, photos and model? This cannot be undone."):
            self.ctx.school.delete_class(code)
            self.ctx.classes_changed.emit()

    def add_student(self):
        code = self.current_code()
        if not code:
            return error(self, "Add a class first.")
        name, ok = QInputDialog.getText(self, "Add student", f"Student name ({code}):")
        if ok and name.strip():
            try:
                self.ctx.school.add_student(code, name)
            except ValueError as e:
                return error(self, str(e))
            self.ctx.classes_changed.emit()

    def import_students(self):
        code = self.current_code()
        if not code:
            return error(self, "Add a class first.")
        path, _ = QFileDialog.getOpenFileName(self, "Student list", "", "Excel or CSV (*.xlsx *.csv *.txt)")
        if not path:
            return
        try:
            names = import_students(path)
        except Exception as e:
            return error(self, f"Could not read the file: {e}")
        existing = {s.name for s in self.ctx.school.load_class(code).students}
        added = 0
        for n in names:
            if n not in existing:
                self.ctx.school.add_student(code, n)
                added += 1
        self.ctx.classes_changed.emit()
        info(self, f"Added {added} students to {code} (names are read from the first column).")

    def rename_student(self):
        code, sid = self.current_code(), self.selected_student_id()
        if not (code and sid):
            return
        old = next(s.name for s in self.ctx.school.load_class(code).students if s.id == sid)
        name, ok = QInputDialog.getText(self, "Rename student", "New name:", text=old)
        if ok and name.strip():
            self.ctx.school.rename_student(code, sid, name)
            self.ctx.classes_changed.emit()

    def remove_student(self):
        code, sid = self.current_code(), self.selected_student_id()
        if not (code and sid):
            return
        name = next(s.name for s in self.ctx.school.load_class(code).students if s.id == sid)
        if confirm(self, f"Remove {name} and delete their photos?"):
            self.ctx.school.remove_student(code, sid)
            self.ctx.classes_changed.emit()

    def open_class_folder(self):
        code = self.current_code()
        if code:
            open_folder(self.ctx.school.class_dir(code))

"""Groups and their people (a group can be a class, a team, a shift, a course...)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.storage import import_people, valid_code
from . import theme
from .common import confirm, danger, error, info, muted, open_folder, primary, title
from .context import AppContext


class GroupDialog(QDialog):
    """Add a group, or edit the name and room of an existing one (the code is its folder name and stays)."""

    def __init__(self, parent=None, existing: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Group" if existing else "Add group")
        form = QFormLayout(self)
        self.code = QLineEdit()
        self.code.setPlaceholderText("short code, e.g. 9A1, TEAM-A, NIGHT-2")
        self.name = QLineEdit()
        self.name.setPlaceholderText("optional, e.g. Grade 9 Advanced 1, Sales team")
        self.room = QLineEdit()
        self.room.setPlaceholderText("optional, e.g. Room 12")
        form.addRow("Code (letters, digits, - and _)", self.code)
        form.addRow("Name", self.name)
        form.addRow("Room", self.room)
        if existing:
            self.code.setText(existing["code"])
            self.code.setEnabled(False)
            self.name.setText(existing.get("name", ""))
            self.room.setText(existing.get("room", ""))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self):
        if not valid_code(self.code.text().strip()):
            error(self, "The code may only contain letters, digits, - and _ (max 16), e.g. 9A1 or TEAM-A.")
            return
        self.accept()

    def values(self) -> dict:
        return {"code": self.code.text().strip(), "name": self.name.text().strip(), "room": self.room.text().strip()}


class GroupsTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        root = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(title("Groups"))
        self.group_list = QListWidget()
        self.group_list.currentItemChanged.connect(lambda *_: self.refresh_people())
        left.addWidget(self.group_list, 1)
        row = QHBoxLayout()
        add = primary("Add group")
        add.clicked.connect(self.add_group)
        edit = self._btn("Edit", self.edit_group)
        delete = danger("Delete")
        delete.clicked.connect(self.delete_group)
        row.addWidget(add)
        row.addWidget(edit)
        row.addWidget(delete)
        left.addLayout(row)
        root.addLayout(left, 1)

        right = QVBoxLayout()
        self.group_title = title("—")
        self.group_info = muted()
        right.addWidget(self.group_title)
        right.addWidget(self.group_info)

        box = QGroupBox("People")
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
        r2.addWidget(self._btn("Add person", self.add_person, primary=True))
        r2.addWidget(self._btn("Import from Excel / CSV", self.import_people))
        r2.addWidget(self._btn("Rename", self.rename_person))
        rm = danger("Remove")
        rm.clicked.connect(self.remove_person)
        r2.addWidget(rm)
        r2.addStretch(1)
        r2.addWidget(self._btn("Open group folder", self.open_group_folder))
        bl.addLayout(r2)
        right.addWidget(box, 1)
        self.model_label = muted()
        right.addWidget(self.model_label)
        root.addLayout(right, 3)

        ctx.groups_changed.connect(self.refresh)
        ctx.photos_changed.connect(lambda _: self.refresh_people())
        ctx.model_changed.connect(lambda _: self.refresh_people())
        self.refresh()

    def _btn(self, text, fn, primary=False):
        b = QPushButton(text)
        if primary:
            b.setProperty("primary", True)
        b.clicked.connect(fn)
        return b

    # ----- data -----
    def current_code(self) -> str | None:
        it = self.group_list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def refresh(self):
        current = self.current_code()
        self.group_list.blockSignals(True)
        self.group_list.clear()
        org = self.ctx.org
        for code in org.group_codes():
            g = org.load_group(code)
            it = QListWidgetItem(f"{g.label}   ·   {len(g.people)} people")
            it.setData(Qt.UserRole, code)
            self.group_list.addItem(it)
            if code == current:
                self.group_list.setCurrentItem(it)
        self.group_list.blockSignals(False)
        if self.group_list.currentItem() is None and self.group_list.count():
            self.group_list.setCurrentRow(0)
        self.refresh_people()

    def refresh_people(self):
        code = self.current_code()
        self.table.setRowCount(0)
        if not code:
            self.group_title.setText("No groups yet")
            self.group_info.setText("Click “Add group” to create the first group (a class, a team, a shift...).")
            self.model_label.setText("")
            return
        org = self.ctx.org
        g = org.load_group(code)
        self.group_title.setText(f"Group {g.label}")
        self.group_info.setText(f"Room: {g.room}" if g.room else "")
        report = org.report(code)
        recall = {p["id"]: p.get("recall") for p in (report or {}).get("people", [])}
        target = org.settings.photos_per_person
        for person in g.people:
            n = len(org.photos(code, person))
            r = self.table.rowCount()
            self.table.insertRow(r)
            name = QTableWidgetItem(person.name)
            name.setData(Qt.UserRole, person.id)
            self.table.setItem(r, 0, name)
            p = QTableWidgetItem(f"{n} / {target}")
            p.setForeground(QColor(theme.OK if n >= target else theme.WARN if n else theme.BAD))
            self.table.setItem(r, 1, p)
            rc = recall.get(person.id)
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
            self.model_label.setText("No model yet — capture photos, then train this group.")

    def selected_person_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)

    # ----- actions -----
    def add_group(self):
        dlg = GroupDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        try:
            self.ctx.org.add_group(v["code"], v["name"], v["room"])
        except ValueError as e:
            error(self, str(e))
            return
        self.ctx.groups_changed.emit()
        for i in range(self.group_list.count()):
            if self.group_list.item(i).data(Qt.UserRole) == v["code"]:
                self.group_list.setCurrentRow(i)

    def edit_group(self):
        code = self.current_code()
        if not code:
            return
        g = self.ctx.org.load_group(code)
        dlg = GroupDialog(self, {"code": g.code, "name": g.name, "room": g.room})
        if dlg.exec() != QDialog.Accepted:
            return
        v = dlg.values()
        g.name, g.room = v["name"] or g.code, v["room"]
        self.ctx.org.save_group(g)
        self.ctx.groups_changed.emit()

    def delete_group(self):
        code = self.current_code()
        if code and confirm(self, f"Delete group {code} with ALL its people, photos and model? This cannot be undone."):
            self.ctx.org.delete_group(code)
            self.ctx.groups_changed.emit()

    def add_person(self):
        code = self.current_code()
        if not code:
            return error(self, "Add a group first.")
        name, ok = QInputDialog.getText(self, "Add person", f"Name ({code}):")
        if ok and name.strip():
            try:
                self.ctx.org.add_person(code, name)
            except ValueError as e:
                return error(self, str(e))
            self.ctx.groups_changed.emit()

    def import_people(self):
        code = self.current_code()
        if not code:
            return error(self, "Add a group first.")
        path, _ = QFileDialog.getOpenFileName(self, "List of names", "", "Excel or CSV (*.xlsx *.csv *.txt)")
        if not path:
            return
        try:
            names = import_people(path)
        except Exception as e:
            return error(self, f"Could not read the file: {e}")
        existing = {p.name for p in self.ctx.org.load_group(code).people}
        added = 0
        for n in names:
            if n not in existing:
                self.ctx.org.add_person(code, n)
                added += 1
        self.ctx.groups_changed.emit()
        info(self, f"Added {added} people to {code} (names are read from the first column).")

    def rename_person(self):
        code, pid = self.current_code(), self.selected_person_id()
        if not (code and pid):
            return
        old = next(p.name for p in self.ctx.org.load_group(code).people if p.id == pid)
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old)
        if ok and name.strip():
            self.ctx.org.rename_person(code, pid, name)
            self.ctx.groups_changed.emit()

    def remove_person(self):
        code, pid = self.current_code(), self.selected_person_id()
        if not (code and pid):
            return
        name = next(p.name for p in self.ctx.org.load_group(code).people if p.id == pid)
        if confirm(self, f"Remove {name} and delete their photos?"):
            self.ctx.org.remove_person(code, pid)
            self.ctx.groups_changed.emit()

    def open_group_folder(self):
        code = self.current_code()
        if code:
            open_folder(self.ctx.org.group_dir(code))

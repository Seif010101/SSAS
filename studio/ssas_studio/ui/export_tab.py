"""Copy the boards' packages to a USB stick."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStorageInfo, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.export import USB_FOLDER, board_plans, export_usb
from .common import confirm, error, info, muted, open_folder, primary, title
from .context import AppContext
from .workers import run_job

READY_ROLE = Qt.UserRole + 1  # list item data: trained and has lessons, so it can be exported


class ExportTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.job = None
        root = QVBoxLayout(self)
        root.addWidget(title("Export to USB"))
        root.addWidget(
            muted(
                f"Creates the folder {USB_FOLDER} on the USB stick with the board app, the models, and one folder per board "
                "(its timetable and the model of its class). Student photos are never copied. On the board, open SSAS Board "
                "→ Import from USB → choose this board."
            )
        )

        dest = QGroupBox("1. USB stick")
        dl = QHBoxLayout(dest)
        self.drive_box = QComboBox()
        self.drive_box.setEditable(True)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_drives)
        browse = QPushButton("Choose folder…")
        browse.clicked.connect(self.browse)
        dl.addWidget(self.drive_box, 1)
        dl.addWidget(refresh)
        dl.addWidget(browse)
        root.addWidget(dest)

        boards = QGroupBox("2. Boards to export")
        bl = QVBoxLayout(boards)
        self.board_list = QListWidget()
        bl.addWidget(self.board_list)
        row = QHBoxLayout()
        all_btn = QPushButton("Select all")
        all_btn.clicked.connect(lambda: self._check_all(True))
        none_btn = QPushButton("Select none")
        none_btn.clicked.connect(lambda: self._check_all(False))
        rekey_btn = QPushButton("New server keys…")
        rekey_btn.setToolTip("Use this if a USB stick with board files was lost.")
        rekey_btn.clicked.connect(self.new_keys)
        row.addWidget(all_btn)
        row.addWidget(none_btn)
        row.addStretch(1)
        row.addWidget(rekey_btn)
        bl.addLayout(row)
        self.problems = muted("")
        bl.addWidget(self.problems)
        root.addWidget(boards, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.status = muted("")
        self.export_btn = primary("3. Export")
        self.export_btn.clicked.connect(self.export)
        root.addWidget(self.progress)
        root.addWidget(self.status)
        root.addWidget(self.export_btn)

        for sig in (ctx.classes_changed, ctx.model_changed, ctx.settings_changed):
            sig.connect(lambda *_: self.refresh())
        self.refresh_drives()
        self.refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()  # the boards' state can change in other tabs (training, timetable)

    def refresh_drives(self):
        self.drive_box.clear()
        for v in QStorageInfo.mountedVolumes():
            if not v.isValid() or not v.isReady() or v.isReadOnly():
                continue
            root = v.rootPath()
            if root in ("/", "C:/") or root.startswith(("/boot", "/snap", "/proc", "/sys", "/dev")):
                continue
            if root.startswith("/run/") and not root.startswith("/run/media/"):
                continue
            free = v.bytesAvailable() / 1e9
            self.drive_box.addItem(f"{root}   ({v.displayName()}, {free:.1f} GB free)", root)

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, "Choose the USB stick or a folder")
        if d:
            self.drive_box.insertItem(0, d, d)
            self.drive_box.setCurrentIndex(0)

    def refresh(self):
        plans, problems = board_plans(self.ctx.school)
        # Keep the user's choice for boards that could already be exported; newly ready boards start ticked.
        ticked = {
            item.data(Qt.UserRole): item.checkState()
            for item in (self.board_list.item(i) for i in range(self.board_list.count()))
            if item.data(READY_ROLE)
        }
        self.board_list.clear()
        for code, plan in sorted(plans.items()):
            missing = [
                c for c in sorted(plan.classes) if not (self.ctx.school.model_dir(c) / "class-model.json").exists()
            ]
            kind = "class board" if plan.kind == "class" else f"lab board ({plan.name})"
            n = len(plan.slots)
            text = f"{code}  —  {kind}  ·  {n} lesson{'' if n == 1 else 's'} per week"
            if missing:
                text += f"  ·  ⚠ not trained: {', '.join(missing)} (use the Train tab)"
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, code)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            ready = bool(plan.slots) and not missing
            it.setData(READY_ROLE, ready)
            it.setCheckState(ticked.get(code, Qt.Checked) if ready else Qt.Unchecked)
            self.board_list.addItem(it)
        self.problems.setText("⚠ " + " · ".join(problems) if problems else "")

    def _check_all(self, on: bool):
        for i in range(self.board_list.count()):
            self.board_list.item(i).setCheckState(Qt.Checked if on else Qt.Unchecked)

    def _checked(self) -> list[str]:
        return [
            self.board_list.item(i).data(Qt.UserRole)
            for i in range(self.board_list.count())
            if self.board_list.item(i).checkState() == Qt.Checked
        ]

    def new_keys(self):
        boards = self._checked()
        if not boards:
            return error(self, "Tick the boards that need new keys.")
        if not confirm(
            self,
            f"Give {len(boards)} board(s) a new server key?\n\nThe old keys stop working once you upload "
            "the new server/boards.json to the server. Then export again and import on each of these boards.",
        ):
            return
        for code in boards:
            self.ctx.school.new_board_token(code)
        info(
            self,
            "New keys made. Export now, upload server/boards.json on the server's Boards page, "
            "then import on each board.",
        )

    def export(self):
        target = self.drive_box.currentData() or self.drive_box.currentText().split("   (")[0].strip()
        if not target or not Path(target).exists():
            return error(self, "Choose the USB stick (or a folder) first.")
        boards = self._checked()
        if not boards:
            return error(self, "Tick at least one board.")
        if not self.ctx.models_ready:
            return error(self, "Download the face models first (Settings tab).")
        apk = self.ctx.apk_path
        self.export_btn.setEnabled(False)

        def work(progress, _cancelled):
            return export_usb(self.ctx.school, Path(target), boards, self.ctx.models_dir, apk, progress)

        self.job = run_job(work, on_progress=self._on_progress, on_done=self._done, on_error=self._on_error)

    def _on_progress(self, message: str, fraction: float) -> None:
        self.progress.setValue(int(fraction * 1000))
        self.status.setText(message)

    def _on_error(self, message: str) -> None:
        self.job = None
        self.export_btn.setEnabled(True)
        error(self, message)

    def _done(self, summary: dict):
        self.job = None
        self.export_btn.setEnabled(True)
        self.status.setText(f"Exported {len(summary['boards'])} boards to {summary['folder']}")
        note = (
            ""
            if self.ctx.apk_path
            else "\n\nNote: the board app (APK) was not found next to Studio; copy ssas-board.apk to the USB yourself."
        )
        info(self, f"Done. {len(summary['boards'])} boards exported to\n{summary['folder']}{note}")
        open_folder(Path(summary["folder"]))

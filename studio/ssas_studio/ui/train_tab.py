"""Train the class models and show the report."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.pipeline import train_and_save
from . import theme
from .common import ClassPicker, error, muted, primary, title
from .context import AppContext
from .workers import JobHandle, run_job

MIN_STUDENTS_WITH_PHOTOS = 2


class TrainTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.job: JobHandle | None = None  # the running training, if any
        self.queue: list[str] = []  # classes waiting to be trained
        self.current = ""  # class being trained now

        root = QVBoxLayout(self)
        root.addWidget(title("Train"))
        root.addWidget(
            muted(
                "Each class gets its own model, trained only on its students. Every photo is turned into many "
                "classroom-like versions (small, blurry, darker…), then the model trains over all of them for the number "
                "of rounds set in Settings, and is tested with cross-validation. Students of the other classes are used "
                "as strangers so the board will not confuse them."
            )
        )
        row = QHBoxLayout()
        self.class_box = ClassPicker(ctx)
        self.train_btn = primary("Train this class")
        self.train_btn.clicked.connect(self.train_selected)
        self.all_btn = primary("Train all classes")
        self.all_btn.clicked.connect(self.train_all)
        self.stop_btn = QPushButton("Cancel")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.cancel)
        row.addWidget(QLabel("Class"))
        row.addWidget(self.class_box, 1)
        for button in (self.train_btn, self.all_btn, self.stop_btn):
            row.addWidget(button)
        root.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.status = muted("")
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        for widget in (self.progress, self.status, self.summary):
            root.addWidget(widget)

        body = QHBoxLayout()
        students_box = QGroupBox("Students")
        sl = QVBoxLayout(students_box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Photos", "Recognised in tests"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        sl.addWidget(self.table)
        body.addWidget(students_box, 2)
        warnings_box = QGroupBox("Warnings")
        wl = QVBoxLayout(warnings_box)
        self.warnings = QListWidget()
        wl.addWidget(self.warnings)
        body.addWidget(warnings_box, 1)
        root.addLayout(body, 1)

        self.class_box.changed.connect(self.show_report)
        ctx.photos_changed.connect(self.show_report)
        self.show_report(self.class_box.code)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self.job:
            self.show_report(self.class_box.code)  # always show what is on disk now

    # ----- what the tab shows -----
    def show_report(self, code: str) -> None:
        """Students of ``code`` (always), plus the last training report when there is one."""
        if code != self.class_box.code:
            return
        school = self.ctx.school
        self.table.setRowCount(0)
        self.warnings.clear()
        if not code:
            self.summary.setText("Add a class and its students in the Classes tab first.")
            return
        report = school.report(code)
        recall = {s["id"]: s.get("recall") for s in report["students"]} if report else {}
        students = school.load_class(code).students
        without_photos = []
        for s in students:
            n = len(school.photos(code, s))
            if n == 0:
                without_photos.append(s.name)
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(s.name))
            self.table.setItem(row, 1, QTableWidgetItem(str(n)))
            self.table.setItem(row, 2, self._recall_item(recall.get(s.id)))

        if report:
            self.summary.setText(self._report_text(code, report))
            for name in report.get("weak_students", []):
                self.warnings.addItem(f"Retake photos: {name}")
            for pair in report.get("lookalikes", []):
                self.warnings.addItem(
                    f"Very similar faces: {pair['a']}  ↔  {pair['b']} ({pair['similarity']:.2f}) — same person twice?"
                )
            for p in report.get("photo_problems", [])[:50]:
                self.warnings.addItem(f"{p['student']}: {p['photo']} — {p['problem']}")
        else:
            ready = len(students) - len(without_photos)
            self.summary.setText(f"<b>{code}</b>: not trained yet · {ready} of {len(students)} students have photos.")
        for name in without_photos:
            self.warnings.addItem(f"No photos yet: {name}")
        if self.warnings.count() == 0:
            self.warnings.addItem("No warnings.")

    @staticmethod
    def _recall_item(recall: float | None) -> QTableWidgetItem:
        if recall is None:
            return QTableWidgetItem("—")
        item = QTableWidgetItem(f"{recall * 100:.0f}%")
        item.setForeground(QColor(theme.OK if recall >= 0.95 else theme.WARN if recall >= 0.9 else theme.BAD))
        return item

    @staticmethod
    def _report_text(code: str, r: dict) -> str:
        m = r["metrics"]
        strangers = m.get("stranger_accept_rate")
        verdict = (
            f"<span style='color:{theme.OK}'><b>Passed</b></span>"
            if r.get("passed")
            else f"<span style='color:{theme.BAD}'><b>Below target</b></span> — capture more photos of the weak students and train again"
        )
        return (
            f"<b>{code}</b> · trained {r['created_at'][:16].replace('T', ' ')} on {r['device']} in {r['duration_s']:.0f} s · "
            f"{r['epochs']} rounds × {r['folds']}-fold check × {r['seeds']} repeats · method: {r['method']}<br>"
            f"Correct recognition in tests: <b>{m['accuracy'] * 100:.1f}%</b> · "
            f"wrong student: {m['wrong_student_rate'] * 100:.2f}% · "
            f"strangers accepted: {'—' if strangers is None else f'{strangers * 100:.2f}%'} · {verdict}"
        )

    # ----- starting and stopping -----
    def train_selected(self) -> None:
        self.start([self.class_box.code])

    def train_all(self) -> None:
        self.start(self.ctx.school.class_codes())

    def trainable(self, code: str) -> bool:
        school = self.ctx.school
        with_photos = sum(1 for s in school.load_class(code).students if school.photos(code, s))
        return with_photos >= MIN_STUDENTS_WITH_PHOTOS

    def start(self, codes: list[str]) -> None:
        codes = [c for c in codes if c]
        if not codes:
            return error(self, "Add a class first.")
        if not self.ctx.models_ready:
            return error(self, "Download the face models first (Settings tab).")
        ready = [c for c in codes if self.trainable(c)]
        skipped = [c for c in codes if c not in ready]
        if not ready:
            return error(
                self,
                f"{', '.join(skipped)}: at least two students need photos before a model can be trained. "
                "Capture photos in the Capture tab first.",
            )
        self.queue = ready
        self.status.setText(f"Skipped (not enough photos): {', '.join(skipped)}" if skipped else "")
        self._train_next()

    def _train_next(self) -> None:
        if not self.queue:
            self._set_busy(False)
            return
        code = self.current = self.queue.pop(0)
        self._set_busy(True)
        self.status.setText(f"Training {code}…")

        def work(progress, cancelled):
            return train_and_save(self.ctx.school, code, self.ctx.engine(), progress, cancelled)

        self.job = run_job(
            work,
            on_progress=self._on_progress,
            on_done=self._on_done,
            on_error=self._on_error,
            on_cancel=self._on_cancel,
        )

    def cancel(self) -> None:
        if self.job:
            self.job.cancel()

    # ----- job callbacks (always on the GUI thread) -----
    def _on_progress(self, message: str, fraction: float) -> None:
        self.progress.setValue(int(fraction * 1000))
        self.status.setText(f"{self.current}: {message}")

    def _on_done(self, _report: dict) -> None:
        self.ctx.model_changed.emit(self.current)
        self.class_box.setCurrentText(self.current)
        self.show_report(self.current)
        self._train_next()

    def _on_error(self, message: str) -> None:
        self.queue.clear()
        self._set_busy(False)
        self.status.setText(f"{self.current}: training failed")
        error(self, f"{self.current}: {message}")

    def _on_cancel(self) -> None:
        self.queue.clear()
        self._set_busy(False)
        self.status.setText("Cancelled.")

    def _set_busy(self, busy: bool) -> None:
        for widget in (self.train_btn, self.all_btn, self.class_box):
            widget.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        if not busy:
            self.job = None
            self.progress.setValue(0)

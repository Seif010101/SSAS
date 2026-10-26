"""Train the class models and show the report."""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QListWidget, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..core.pipeline import train_and_save
from . import theme
from .common import error, muted, primary, title
from .context import AppContext
from .workers import start_job


class TrainTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.job = None
        self.queue: list[str] = []
        root = QVBoxLayout(self)
        root.addWidget(title("Train"))
        root.addWidget(muted(
            "Each class gets its own model, trained only on its students. Every photo is turned into many "
            "classroom-like versions (small, blurry, darker…), then the model trains over all of them for the number "
            "of rounds set in Settings, and is tested with cross-validation. Students of the other classes are used "
            "as strangers so the board will not confuse them."
        ))
        row = QHBoxLayout()
        self.class_box = QComboBox()
        row.addWidget(QLabel("Class"))
        row.addWidget(self.class_box, 1)
        self.train_btn = primary("Train this class")
        self.train_btn.clicked.connect(lambda: self.start([self.class_box.currentText()]))
        self.all_btn = primary("Train all classes")
        self.all_btn.clicked.connect(lambda: self.start(self.ctx.school.class_codes()))
        self.stop_btn = QPushButton("Cancel")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.cancel)
        for b in (self.train_btn, self.all_btn, self.stop_btn):
            row.addWidget(b)
        root.addLayout(row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.status = muted("")
        root.addWidget(self.progress)
        root.addWidget(self.status)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)

        body = QHBoxLayout()
        box = QGroupBox("Students")
        bl = QVBoxLayout(box)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Photos used", "Recognised in tests"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        bl.addWidget(self.table)
        body.addWidget(box, 2)
        warn = QGroupBox("Warnings")
        wl = QVBoxLayout(warn)
        self.warnings = QListWidget()
        wl.addWidget(self.warnings)
        body.addWidget(warn, 1)
        root.addLayout(body, 1)

        ctx.classes_changed.connect(self.refresh_classes)
        self.class_box.currentTextChanged.connect(self.show_report)
        self.refresh_classes()

    def refresh_classes(self):
        cur = self.class_box.currentText()
        self.class_box.blockSignals(True)
        self.class_box.clear()
        self.class_box.addItems(self.ctx.school.class_codes())
        if cur:
            self.class_box.setCurrentText(cur)
        self.class_box.blockSignals(False)
        self.show_report(self.class_box.currentText())

    def show_report(self, code: str):
        self.table.setRowCount(0)
        self.warnings.clear()
        if not code:
            self.summary.setText("")
            return
        r = self.ctx.school.report(code)
        if not r:
            self.summary.setText(f"<b>{code}</b>: not trained yet.")
            return
        m = r["metrics"]
        sa = m.get("stranger_accept_rate")
        verdict = (f"<span style='color:{theme.OK}'><b>Passed</b></span>" if r.get("passed")
                   else f"<span style='color:{theme.BAD}'><b>Below target</b></span> — capture more photos of the weak students and train again")
        self.summary.setText(
            f"<b>{code}</b> · trained {r['created_at'][:16].replace('T', ' ')} on {r['device']} in {r['duration_s']:.0f} s · "
            f"{r['epochs']} rounds × {r['folds']}-fold check × {r['seeds']} repeats · method: {r['method']}<br>"
            f"Correct recognition in tests: <b>{m['accuracy'] * 100:.1f}%</b> · "
            f"wrong student: {m['wrong_student_rate'] * 100:.2f}% · "
            f"strangers accepted: {'—' if sa is None else f'{sa * 100:.2f}%'} · {verdict}"
        )
        for s in r["students"]:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(s["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(str(s["photos"])))
            rc = s.get("recall")
            it = QTableWidgetItem("—" if rc is None else f"{rc * 100:.0f}%")
            if rc is not None:
                it.setForeground(QColor(theme.OK if rc >= 0.95 else theme.WARN if rc >= 0.9 else theme.BAD))
            self.table.setItem(row, 2, it)
        for name in r.get("weak_students", []):
            self.warnings.addItem(f"Retake photos: {name}")
        for la in r.get("lookalikes", []):
            self.warnings.addItem(f"Very similar faces: {la['a']}  ↔  {la['b']} ({la['similarity']:.2f}) — same person twice?")
        for p in r.get("photo_problems", [])[:50]:
            self.warnings.addItem(f"{p['student']}: {p['photo']} — {p['problem']}")
        if self.warnings.count() == 0:
            self.warnings.addItem("No warnings.")

    def start(self, codes: list[str]):
        codes = [c for c in codes if c]
        if not codes:
            return error(self, "Add a class first.")
        if not self.ctx.models_ready:
            return error(self, "Download the face models first (Settings tab).")
        self.queue = list(codes)
        self._next()

    def _next(self):
        if not self.queue:
            self._set_busy(False)
            return
        code = self.queue.pop(0)
        self._set_busy(True)
        self.status.setText(f"Training {code}…")

        def work(progress, cancelled):
            return train_and_save(self.ctx.school, code, self.ctx.engine(), progress, cancelled)

        self.job, self._thread = start_job(self, work)
        self.job.progress.connect(lambda msg, f: (self.progress.setValue(int(f * 1000)), self.status.setText(f"{code}: {msg}")))
        self.job.finished.connect(lambda _r: self._done(code))
        self.job.failed.connect(lambda msg: (self._set_busy(False), self.queue.clear(), error(self, f"{code}: {msg}")))
        self.job.cancelled.connect(lambda: (self._set_busy(False), self.queue.clear(), self.status.setText("Cancelled.")))

    def _done(self, code: str):
        self.ctx.model_changed.emit(code)
        self.class_box.setCurrentText(code)
        self.show_report(code)
        self._next()

    def cancel(self):
        if self.job:
            self.job.cancel()

    def _set_busy(self, busy: bool):
        self.train_btn.setEnabled(not busy)
        self.all_btn.setEnabled(not busy)
        self.class_box.setEnabled(not busy)
        self.stop_btn.setEnabled(busy)
        if not busy:
            self.job = None
            self.progress.setValue(0)

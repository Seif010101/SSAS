"""Settings, data folder and the one-time model download."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ..core.models import MODELS, available_providers, download_models, verify_models
from .common import confirm, error, info, muted, open_folder, primary, title
from .context import AppContext
from .workers import start_job


class SettingsTab(QWidget):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.job = None
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget()
        scroll.setWidget(inner)
        root = QVBoxLayout(inner)
        root.addWidget(title("Settings"))

        models = QGroupBox("Face models (download once, about 200 MB)")
        ml = QVBoxLayout(models)
        self.models_status = muted("")
        ml.addWidget(self.models_status)
        self.dl_progress = QProgressBar()
        self.dl_progress.setRange(0, 1000)
        self.dl_progress.hide()
        ml.addWidget(self.dl_progress)
        mr = QHBoxLayout()
        self.dl_btn = primary("Download models")
        self.dl_btn.clicked.connect(self.download)
        open_m = QPushButton("Open models folder")
        open_m.clicked.connect(lambda: open_folder(self.ctx.models_dir))
        mr.addWidget(self.dl_btn)
        mr.addWidget(open_m)
        mr.addStretch(1)
        ml.addLayout(mr)
        ml.addWidget(muted("The face models are © InsightFace (non-commercial research licence) and RTMO © OpenMMLab. "
                           "They are downloaded from their official pages and are not part of SSAS."))
        root.addWidget(models)

        school = QGroupBox("School")
        sf = QFormLayout(school)
        self.school_name = QLineEdit()
        sf.addRow("School name", self.school_name)
        drow = QHBoxLayout()
        self.data_dir = QLabel()
        change = QPushButton("Change…")
        change.clicked.connect(self.change_data_dir)
        openb = QPushButton("Open")
        openb.clicked.connect(lambda: open_folder(self.ctx.data_dir))
        drow.addWidget(self.data_dir, 1)
        drow.addWidget(change)
        drow.addWidget(openb)
        sf.addRow("Data folder", drow)
        root.addWidget(school)

        cap = QGroupBox("Board camera")
        cf = QFormLayout(cap)
        self.offset = QDoubleSpinBox()
        self.offset.setRange(0, 30)
        self.offset.setSuffix(" min after the lesson starts")
        self.window = QDoubleSpinBox()
        self.window.setRange(0.5, 15)
        self.window.setSuffix(" min at most")
        self.pin = QLineEdit()
        self.pin.setMaxLength(8)
        self.sound = QCheckBox("Play a soft sound when the camera starts and stops")
        cf.addRow("Open the camera", self.offset)
        cf.addRow("Keep it open", self.window)
        cf.addRow("Board admin PIN", self.pin)
        cf.addRow("", self.sound)
        root.addWidget(cap)

        tr = QGroupBox("Training")
        tf = QFormLayout(tr)
        self.epochs = QSpinBox()
        self.epochs.setRange(10, 2000)
        self.epochs.setSuffix(" rounds")
        self.aug = QSpinBox()
        self.aug.setRange(0, 40)
        self.aug.setSuffix(" variants per photo")
        self.folds = QSpinBox()
        self.folds.setRange(2, 10)
        self.seeds = QSpinBox()
        self.seeds.setRange(1, 10)
        self.min_acc = QDoubleSpinBox()
        self.min_acc.setRange(50, 100)
        self.min_acc.setSuffix(" %")
        self.photos = QSpinBox()
        self.photos.setRange(20, 300)
        self.photos.setSuffix(" photos (40 is enough)")
        self.strict = QCheckBox("Strict capture: the student must follow the circle in a random order (slower)")
        self.gpu = QCheckBox("Use the graphics card (GPU) when available")
        tf.addRow("Training rounds (epochs)", self.epochs)
        tf.addRow("Classroom-like variants", self.aug)
        tf.addRow("Cross-validation folds", self.folds)
        tf.addRow("Repeats (seeds)", self.seeds)
        tf.addRow("Minimum accuracy to pass", self.min_acc)
        tf.addRow("Photos per student", self.photos)
        tf.addRow("", self.strict)
        tf.addRow("", self.gpu)
        self.providers = muted("")
        tf.addRow("Available", self.providers)
        root.addWidget(tr)

        srv = QGroupBox("Server (optional — boards keep results on the board when empty)")
        vf = QFormLayout(srv)
        self.server_url = QLineEdit()
        self.server_url.setPlaceholderText("https://192.168.1.10")
        self.server_fp = QLineEdit()
        self.server_fp.setPlaceholderText("SHA-256 fingerprint shown by the server (for its own certificate)")
        vf.addRow("Server address", self.server_url)
        vf.addRow("Certificate fingerprint", self.server_fp)
        root.addWidget(srv)

        save = primary("Save settings")
        save.clicked.connect(self.save)
        root.addWidget(save)
        root.addStretch(1)

        ctx.settings_changed.connect(self.load)
        self.load()

    def load(self):
        s = self.ctx.school.settings
        self.school_name.setText(self.ctx.school.name)
        self.data_dir.setText(str(self.ctx.data_dir))
        self.offset.setValue(s.capture_offset_min)
        self.window.setValue(s.capture_window_min)
        self.pin.setText(s.board_admin_pin)
        self.sound.setChecked(s.sound)
        self.epochs.setValue(s.epochs)
        self.aug.setValue(s.augment_per_photo)
        self.folds.setValue(s.folds)
        self.seeds.setValue(s.seeds)
        self.min_acc.setValue(s.min_accuracy * 100)
        self.photos.setValue(s.photos_per_student)
        self.strict.setChecked(s.strict_order)
        self.gpu.setChecked(self.ctx.prefer_gpu)
        self.server_url.setText(s.server_url)
        self.server_fp.setText(s.server_cert_sha256)
        prov = available_providers()
        self.providers.setText("GPU (DirectML) ✓" if "DmlExecutionProvider" in prov
                               else "GPU (CUDA) ✓" if "CUDAExecutionProvider" in prov else "CPU only")
        self.refresh_models()

    def refresh_models(self):
        status = verify_models(self.ctx.models_dir)
        lines = [f"{'✓' if v == 'ok' else '✗'} {MODELS[k].purpose} — {v}" for k, v in status.items()]
        self.models_status.setText("\n".join(lines))
        self.dl_btn.setText("Download models" if not self.ctx.models_ready else "Download again / missing models")

    def save(self):
        if not self.pin.text().isdigit() or len(self.pin.text()) < 4:
            return error(self, "The board admin PIN must be 4 to 8 digits.")
        s = self.ctx.school.settings
        s.capture_offset_min = self.offset.value()
        s.capture_window_min = self.window.value()
        s.board_admin_pin = self.pin.text()
        s.sound = self.sound.isChecked()
        s.epochs = self.epochs.value()
        s.augment_per_photo = self.aug.value()
        s.folds = self.folds.value()
        s.seeds = self.seeds.value()
        s.min_accuracy = self.min_acc.value() / 100
        s.photos_per_student = self.photos.value()
        s.strict_order = self.strict.isChecked()
        s.server_url = self.server_url.text().strip().rstrip("/")
        s.server_cert_sha256 = self.server_fp.text().strip().replace(":", "").lower()
        self.ctx.school.settings = s
        if self.school_name.text().strip():
            self.ctx.school.name = self.school_name.text()
        self.ctx.prefer_gpu = self.gpu.isChecked()
        self.ctx.settings_changed.emit()
        info(self, "Settings saved. Export the boards again so they get the new settings.")

    def change_data_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose the data folder")
        if d and confirm(self, f"Use {d} as the data folder? (The current data is not moved.)"):
            self.ctx.set_data_dir(Path(d))

    def download(self):
        self.dl_btn.setEnabled(False)
        self.dl_progress.show()

        def work(progress, _cancelled):
            download_models(self.ctx.models_dir, progress)
            return True

        self.job, self._thread = start_job(self, work)
        self.job.progress.connect(lambda m, f: (self.dl_progress.setValue(int(f * 1000)), self.models_status.setText(f"Downloading {m}…")))
        self.job.finished.connect(self._downloaded)
        self.job.failed.connect(self._download_failed)

    def _downloaded(self, _):
        self.dl_btn.setEnabled(True)
        self.dl_progress.hide()
        self.ctx.reset_engine()
        self.refresh_models()
        info(self, "Models downloaded.")

    def _download_failed(self, msg: str):
        self.dl_btn.setEnabled(True)
        self.dl_progress.hide()
        self.refresh_models()
        if self.ctx.models_ready:
            info(self, f"The face models are ready. The body-pose model could not be downloaded ({msg}); "
                       "boards will still work, without stick figures and head count.")
        else:
            error(self, f"Download failed: {msg}\nCheck the internet connection and try again.")

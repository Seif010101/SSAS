"""Shared state for all tabs."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal

from ..core.models import missing_models
from ..core.storage import School
from ..resources import ORG_NAME, APP_NAME, bundled_apk, default_data_dir, default_models_dir


class AppContext(QObject):
    classes_changed = Signal()  # classes or students were added / removed / renamed
    photos_changed = Signal(str)  # class code
    model_changed = Signal(str)  # class code
    settings_changed = Signal()

    def __init__(self, data_dir: Path | None = None, models_dir: Path | None = None):
        super().__init__()
        self.qsettings = QSettings(ORG_NAME, APP_NAME)
        data_dir = data_dir or Path(self.qsettings.value("data_dir", str(default_data_dir())))
        self.models_dir = Path(models_dir or default_models_dir())
        self.school = School(data_dir)
        self._engine = None

    @property
    def data_dir(self) -> Path:
        return self.school.root

    def set_data_dir(self, path: Path) -> None:
        self.qsettings.setValue("data_dir", str(path))
        self.school = School(path)
        self.classes_changed.emit()
        self.settings_changed.emit()

    @property
    def models_ready(self) -> bool:
        return not missing_models(self.models_dir)

    @property
    def prefer_gpu(self) -> bool:
        return self.qsettings.value("prefer_gpu", "true") in (True, "true", "1")

    @prefer_gpu.setter
    def prefer_gpu(self, v: bool) -> None:
        self.qsettings.setValue("prefer_gpu", "true" if v else "false")
        self._engine = None

    def engine(self):
        """Face models, loaded once (slow the first time)."""
        if self._engine is None:
            from ..core.pipeline import FaceEngine

            self._engine = FaceEngine(self.models_dir, prefer_gpu=self.prefer_gpu)
        return self._engine

    def reset_engine(self) -> None:
        self._engine = None

    @property
    def apk_path(self) -> Path | None:
        return bundled_apk()

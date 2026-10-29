"""Small helpers shared by the tabs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QLabel, QMessageBox, QPushButton, QWidget

from .context import AppContext


def primary(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("primary", True)
    return b


def danger(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("danger", True)
    return b


def muted(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setProperty("muted", True)
    label.setWordWrap(True)
    return label


def title(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("title", True)
    return label


def error(parent: QWidget, message: str) -> None:
    QMessageBox.warning(parent, "SSAS Studio", message)


def info(parent: QWidget, message: str) -> None:
    QMessageBox.information(parent, "SSAS Studio", message)


def confirm(parent: QWidget, message: str) -> bool:
    return QMessageBox.question(parent, "SSAS Studio", message) == QMessageBox.Yes


def open_folder(path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


class ClassPicker(QComboBox):
    """Drop-down with the school's classes. Keeps the selection when classes are added or removed.

    ``changed(code)`` fires when the user picks a class and also after the list is reloaded.
    """

    changed = Signal(str)

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.currentTextChanged.connect(self.changed)
        ctx.classes_changed.connect(self.reload)
        self.reload()

    @property
    def code(self) -> str:
        return self.currentText()

    def reload(self) -> None:
        previous = self.code
        self.blockSignals(True)
        self.clear()
        self.addItems(self.ctx.school.class_codes())
        if previous:
            self.setCurrentText(previous)
        self.blockSignals(False)
        self.changed.emit(self.code)

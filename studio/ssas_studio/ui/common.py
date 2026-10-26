"""Small helpers shared by the tabs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton, QWidget


def primary(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("primary", True)
    return b


def danger(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("danger", True)
    return b


def muted(text: str = "") -> QLabel:
    l = QLabel(text)
    l.setProperty("muted", True)
    l.setWordWrap(True)
    return l


def title(text: str) -> QLabel:
    l = QLabel(text)
    l.setProperty("title", True)
    return l


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

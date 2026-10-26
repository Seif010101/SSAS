"""Where Studio keeps things on this computer."""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "SSAS Studio"
ORG_NAME = "SSAS"


def bundle_dir() -> Path:
    """Folder with files shipped next to the program (PyInstaller sets sys._MEIPASS)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def app_data_dir() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    d = base / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def default_models_dir() -> Path:
    return Path(os.environ.get("SSAS_MODELS_DIR", app_data_dir() / "models"))


def default_data_dir() -> Path:
    docs = Path.home() / "Documents"
    return (docs if docs.exists() else Path.home()) / "SSAS-Data"


def bundled_apk() -> Path | None:
    for p in (bundle_dir() / "board" / "ssas-board.apk", Path(sys.executable).parent / "board" / "ssas-board.apk"):
        if p.exists():
            return p
    return None

"""Colours, style sheet and the app icon (drawn in code, no image files needed)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap

PRIMARY = "#0f766e"
PRIMARY_DARK = "#115e59"
PRIMARY_SOFT = "#ccfbf1"
PRIMARY_TINT = "#f0fdfa"
BG = "#f4f6f8"
SURFACE = "#ffffff"
SURFACE_MUTED = "#f8fafc"
TEXT = "#0f172a"
MUTED = "#64748b"
BORDER = "#e2e8f0"
BORDER_STRONG = "#cbd5e1"
OK = "#16a34a"
WARN = "#d97706"
WARN_SOFT = "#fef3c7"
BAD = "#dc2626"

# Rule for this style sheet: a selector that sets a text colour also sets its background, so the
# program looks the same whatever the Windows light/dark setting is.
STYLE = f"""
* {{ font-size: 10.5pt; }}
QWidget {{ color: {TEXT}; }}
QMainWindow, QDialog, QMessageBox {{ background: {BG}; }}
QScrollArea {{ background: transparent; border: 0; }}
QScrollArea > QWidget > QWidget {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel[muted="true"] {{ color: {MUTED}; }}
QLabel[title="true"] {{ font-size: 15pt; font-weight: 800; }}
QToolTip {{ background: {TEXT}; color: white; border: 0; padding: 4px 8px; }}

QTabWidget::pane {{ border: 0; background: {BG}; }}
QTabBar::tab {{ padding: 10px 18px; margin-right: 2px; border: 0; background: transparent; color: {MUTED}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {TEXT}; background: transparent; }}
QTabBar::tab:selected {{ color: {PRIMARY}; background: transparent; border-bottom: 3px solid {PRIMARY}; }}

QGroupBox {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; margin-top: 22px; padding: 14px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 10px; top: 2px; padding: 0 6px; background: {BG}; color: {TEXT}; }}

QPushButton {{ padding: 7px 14px; border-radius: 8px; border: 1px solid {BORDER_STRONG}; background: {SURFACE}; color: {TEXT}; }}
QPushButton:hover {{ background: {PRIMARY_TINT}; border-color: {PRIMARY}; }}
QPushButton:pressed {{ background: {PRIMARY_SOFT}; }}
QPushButton:disabled {{ color: #94a3b8; background: {SURFACE_MUTED}; border-color: {BORDER}; }}
QPushButton[primary="true"] {{ background: {PRIMARY}; color: white; border: 0; font-weight: 700; }}
QPushButton[primary="true"]:hover {{ background: {PRIMARY_DARK}; }}
QPushButton[primary="true"]:disabled {{ background: #94a3b8; color: white; }}
QPushButton[danger="true"] {{ color: {BAD}; background: {SURFACE}; }}
QPushButton[danger="true"]:hover {{ background: #fef2f2; border-color: {BAD}; }}

QLineEdit, QAbstractSpinBox, QComboBox {{ padding: 4px 8px; min-height: 24px; border: 1px solid {BORDER_STRONG}; border-radius: 6px;
    background: {SURFACE}; color: {TEXT}; selection-background-color: {PRIMARY_SOFT}; selection-color: {TEXT}; }}
QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {{ border: 1px solid {PRIMARY}; }}
QLineEdit:disabled, QAbstractSpinBox:disabled, QComboBox:disabled {{ background: {SURFACE_MUTED}; color: #94a3b8; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
    selection-background-color: {PRIMARY_SOFT}; selection-color: {TEXT}; outline: 0; }}

QAbstractSpinBox {{ padding-right: 22px; }}
QAbstractSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 20px; border: 0; border-left: 1px solid {BORDER}; border-top-right-radius: 6px; background: {SURFACE_MUTED}; }}
QAbstractSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 20px; border: 0; border-left: 1px solid {BORDER}; border-bottom-right-radius: 6px; background: {SURFACE_MUTED}; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {PRIMARY_SOFT}; }}
QAbstractSpinBox::up-arrow {{ image: url(@UP@); width: 9px; height: 9px; }}
QAbstractSpinBox::down-arrow {{ image: url(@DOWN@); width: 9px; height: 9px; }}
QComboBox[cell="skip"] {{ background: {WARN_SOFT}; border-color: {WARN}; color: #92400e; }}
QComboBox[cell="lab"] {{ background: {PRIMARY_SOFT}; border-color: {PRIMARY}; color: {PRIMARY_DARK}; }}

QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {BORDER_STRONG}; border-radius: 4px; background: {SURFACE}; }}
QCheckBox::indicator:hover {{ border-color: {PRIMARY}; }}
QCheckBox::indicator:checked {{ background: {PRIMARY}; border-color: {PRIMARY}; image: url(@CHECK@); }}

QTableWidget, QListWidget, QTreeWidget {{ background: {SURFACE}; alternate-background-color: {SURFACE_MUTED}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 8px; gridline-color: {BORDER}; outline: 0;
    selection-background-color: {PRIMARY_SOFT}; selection-color: {TEXT}; }}
QListWidget::item {{ padding: 6px 8px; }}
QListWidget::item:selected, QTableWidget::item:selected {{ background: {PRIMARY_SOFT}; color: {TEXT}; }}
QHeaderView::section {{ background: {SURFACE_MUTED}; color: {TEXT}; padding: 6px; border: 0; border-bottom: 1px solid {BORDER}; font-weight: 600; }}
QTableCornerButton::section {{ background: {SURFACE_MUTED}; border: 0; }}

QProgressBar {{ border: 1px solid {BORDER_STRONG}; border-radius: 6px; background: {SURFACE}; color: {TEXT}; text-align: center; height: 20px; }}
QProgressBar::chunk {{ background: #5eead4; border-radius: 5px; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 5px; min-height: 30px; margin: 2px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDER_STRONG}; border-radius: 5px; min-width: 30px; margin: 2px; }}
QScrollBar::handle:horizontal:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""


def light_palette() -> QPalette:
    """The same colours for the widgets the style sheet does not reach (e.g. native dialogs)."""
    pal = QPalette()
    for role, col in (
        (QPalette.Window, BG), (QPalette.WindowText, TEXT), (QPalette.Base, SURFACE), (QPalette.AlternateBase, SURFACE_MUTED),
        (QPalette.Text, TEXT), (QPalette.Button, SURFACE), (QPalette.ButtonText, TEXT), (QPalette.ToolTipBase, TEXT),
        (QPalette.ToolTipText, "#ffffff"), (QPalette.Highlight, PRIMARY), (QPalette.HighlightedText, "#ffffff"),
        (QPalette.PlaceholderText, "#94a3b8"), (QPalette.BrightText, "#ffffff"),
    ):
        pal.setColor(role, QColor(col))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#94a3b8"))
    return pal


def apply(app) -> None:
    """Always the light theme, even when Windows is set to dark mode."""
    app.setStyle("Fusion")
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:  # Qt older than 6.8
        pass
    app.setPalette(light_palette())
    up, down = _arrow_images()
    app.setStyleSheet(STYLE.replace("@CHECK@", _check_image()).replace("@UP@", up).replace("@DOWN@", down))


def _arrow_images() -> tuple[str, str]:
    """Small chevrons for the up/down buttons of number and time boxes."""
    paths = []
    for name, ys in (("up", (13, 7, 13)), ("down", (7, 13, 7))):
        path = Path(tempfile.gettempdir()) / f"ssas-studio-{name}.png"
        pm = QPixmap(20, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(MUTED), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(5, ys[0]), QPointF(10, ys[1]), QPointF(15, ys[2])])
        p.end()
        pm.save(str(path))
        paths.append(path.as_posix())
    return paths[0], paths[1]


def _check_image() -> str:
    """The white tick inside a ticked box, drawn once and saved where the style sheet can load it."""
    path = Path(tempfile.gettempdir()) / "ssas-studio-check.png"
    pm = QPixmap(36, 36)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("white"), 4.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.drawPolyline([QPointF(9, 19), QPointF(15, 25), QPointF(27, 11)])
    p.end()
    pm.save(str(path))
    return path.as_posix()


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(icon_pixmap(size))
    return icon


def icon_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(0, 0, size, size)
    path = QPainterPath()
    path.addRoundedRect(r, size * 0.22, size * 0.22)
    p.fillPath(path, QColor(PRIMARY))
    pen = QPen(QColor("white"), max(1.5, size * 0.09), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.drawEllipse(QRectF(size * 0.2, size * 0.2, size * 0.6, size * 0.6))
    p.drawPolyline([QPointF(size * 0.36, size * 0.52), QPointF(size * 0.46, size * 0.62), QPointF(size * 0.65, size * 0.41)])
    p.end()
    return pm

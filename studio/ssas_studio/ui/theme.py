"""Colours, style sheet and the app icon (drawn in code, no image files needed)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

PRIMARY = "#0f766e"
PRIMARY_DARK = "#115e59"
PRIMARY_SOFT = "#ccfbf1"
BG = "#f4f6f8"
TEXT = "#0f172a"
MUTED = "#64748b"
BORDER = "#e2e8f0"
OK = "#16a34a"
WARN = "#d97706"
BAD = "#dc2626"

STYLE = f"""
QWidget {{ font-size: 10.5pt; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QTabWidget::pane {{ border: 0; background: {BG}; }}
QTabBar::tab {{ padding: 10px 18px; margin-right: 2px; border: 0; background: transparent; color: {MUTED}; font-weight: 600; }}
QTabBar::tab:selected {{ color: {PRIMARY}; border-bottom: 3px solid {PRIMARY}; }}
QGroupBox {{ background: white; border: 1px solid {BORDER}; border-radius: 10px; margin-top: 14px; padding: 12px; font-weight: 600; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
QPushButton {{ padding: 7px 14px; border-radius: 8px; border: 1px solid {BORDER}; background: white; }}
QPushButton:hover {{ background: #f8fafc; }}
QPushButton:disabled {{ color: #94a3b8; }}
QPushButton[primary="true"] {{ background: {PRIMARY}; color: white; border: 0; font-weight: 700; }}
QPushButton[primary="true"]:hover {{ background: {PRIMARY_DARK}; }}
QPushButton[primary="true"]:disabled {{ background: #94a3b8; }}
QPushButton[danger="true"] {{ color: {BAD}; }}
QLineEdit {{ padding: 5px 8px; border: 1px solid {BORDER}; border-radius: 6px; background: white; }}
QComboBox, QAbstractSpinBox {{ min-height: 24px; }}
QTableWidget, QListWidget, QTreeWidget {{ background: white; border: 1px solid {BORDER}; border-radius: 8px; gridline-color: {BORDER}; }}
QHeaderView::section {{ background: #f8fafc; padding: 6px; border: 0; border-bottom: 1px solid {BORDER}; font-weight: 600; }}
QProgressBar {{ border: 1px solid {BORDER}; border-radius: 6px; background: white; text-align: center; height: 20px; }}
QProgressBar::chunk {{ background: {PRIMARY}; border-radius: 6px; }}
QLabel[muted="true"] {{ color: {MUTED}; }}
QLabel[title="true"] {{ font-size: 15pt; font-weight: 800; }}
"""


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

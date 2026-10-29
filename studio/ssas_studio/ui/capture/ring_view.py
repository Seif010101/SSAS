"""The camera picture with the Face-ID-like ring painted on top."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ...core.capture_logic import RING_SEGMENTS
from ...core.student_capture import FrameResult
from .. import theme

BACKGROUND = QColor("#0b1220")
RING_IDLE = QColor(255, 255, 255, 70)
RING_RADIUS = 0.36  # of the shorter side of the picture
SEGMENT_GAP_DEG = 6
DONE_TINT = QColor(22, 163, 74, 90)
BANNER_NORMAL = QColor(0, 0, 0, 150)
BANNER_ERROR = QColor(185, 28, 28, 200)
BANNER_DONE = QColor(22, 163, 74, 210)


class RingView(QWidget):
    """Shows the (mirrored) picture, the face boxes, the ring, the student's name and a status banner."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(560, 420)
        self.image: QImage | None = None
        self.result: FrameResult | None = None
        self.boxes: list[list[float]] = []

    def show_frame(self, image: QImage, result: FrameResult, boxes: list[list[float]]) -> None:
        self.image, self.result, self.boxes = image, result, boxes
        self.update()

    def clear(self) -> None:
        self.image, self.result, self.boxes = None, None, []
        self.update()

    # ----- painting -----
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), BACKGROUND)
        if self.image is None or self.result is None:
            self._paint_hint(p)
            return
        picture = self._picture_rect()
        p.drawImage(picture, self.image)
        scale = picture.width() / self.image.width()
        self._paint_boxes(p, picture, scale)
        self._paint_ring(p, picture)
        if self.result.state == "done":
            p.fillRect(picture, DONE_TINT)
        self._paint_name(p, picture)
        self._paint_banner(p, picture)

    def _picture_rect(self) -> QRectF:
        scale = min(self.width() / self.image.width(), self.height() / self.image.height())
        w, h = self.image.width() * scale, self.image.height() * scale
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _paint_hint(self, p: QPainter) -> None:
        p.setPen(QColor("#94a3b8"))
        p.setFont(QFont(self.font().family(), 13))
        p.drawText(self.rect(), Qt.AlignCenter, "Press “Start camera”.\nThe camera stays on for the whole class.")

    def _paint_boxes(self, p: QPainter, picture: QRectF, scale: float) -> None:
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        for x1, y1, x2, y2 in self.boxes:
            p.drawRect(QRectF(picture.x() + x1 * scale, picture.y() + y1 * scale, (x2 - x1) * scale, (y2 - y1) * scale))

    def _paint_ring(self, p: QPainter, picture: QRectF) -> None:
        r = self.result
        cx, cy = picture.center().x(), picture.center().y()
        radius = min(picture.width(), picture.height()) * RING_RADIUS
        p.setPen(QPen(QColor(255, 255, 255, 60), 2))
        p.drawEllipse(QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius))

        arc_radius = radius + 18
        arc = QRectF(cx - arc_radius, cy - arc_radius, 2 * arc_radius, 2 * arc_radius)
        capturing = r.state == "capturing"
        filled = r.filled if capturing else [0.0] * RING_SEGMENTS
        span = 360 / RING_SEGMENTS
        for seg in range(RING_SEGMENTS):
            start = int((seg * span - span / 2 + SEGMENT_GAP_DEG / 2) * 16)
            length = (span - SEGMENT_GAP_DEG) * 16
            if seg == r.target and filled[seg] < 1.0:
                color, width = QColor(theme.OK), 16  # the part to go to
            elif filled[seg] >= 1.0:
                color, width = QColor(theme.PRIMARY), 12
            else:
                color, width = RING_IDLE, 10
            p.setPen(QPen(color, width, Qt.SolidLine, Qt.FlatCap))
            p.drawArc(arc, start, int(length))
            if 0 < filled[seg] < 1.0:  # partly filled
                p.setPen(QPen(QColor(theme.PRIMARY), 12, Qt.SolidLine, Qt.FlatCap))
                p.drawArc(arc, start, int(length * filled[seg]))

        if capturing and r.phase == "front":  # a dot in the middle: look straight at it
            p.setPen(QPen(QColor(theme.OK), 4))
            p.drawEllipse(QRectF(cx - 10, cy - 10, 20, 20))
        if r.state == "waiting" and r.hold > 0:  # the auto-start ring fills while the face is steady
            p.setPen(QPen(QColor(theme.OK), 8, Qt.SolidLine, Qt.RoundCap))
            inner = QRectF(cx - radius + 10, cy - radius + 10, 2 * radius - 20, 2 * radius - 20)
            p.drawArc(inner, 90 * 16, int(-360 * r.hold * 16))

    def _paint_name(self, p: QPainter, picture: QRectF) -> None:
        r = self.result
        if not r.name:
            return
        label = r.name + (f"   {r.saved} / {r.total}" if r.state == "capturing" else "")
        p.setFont(QFont(self.font().family(), 13, QFont.Bold))
        box = QRectF(picture.x() + 12, picture.y() + 12, p.fontMetrics().horizontalAdvance(label) + 28, 36)
        p.setPen(Qt.NoPen)
        p.setBrush(BANNER_NORMAL)
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignCenter, label)

    def _paint_banner(self, p: QPainter, picture: QRectF) -> None:
        r = self.result
        if not r.message:
            return
        p.setFont(QFont(self.font().family(), 15, QFont.Bold))
        box = QRectF(picture.x(), picture.bottom() - 60, picture.width(), 60)
        color = BANNER_ERROR if r.blocked else BANNER_DONE if r.state == "done" else BANNER_NORMAL
        p.fillRect(box, color)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignCenter, r.message)

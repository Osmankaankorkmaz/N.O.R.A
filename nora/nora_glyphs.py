"""Hand-drawn glyphs, in one place.

Every icon in the product is painted, never shipped as an image or an emoji:
it stays crisp at any DPI, needs no assets, and takes whatever pen the caller
gives it.  :class:`~nora.nora_glass.NavButton` draws them with a gradient
brush, the send button draws one into a pixmap, and the rail's five
destinations plus the compose action all come from this table.

The geometry is expressed in fractions of ``box``, so one function serves a
20 px chip and a 48 px rail button.
"""

from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF
from PyQt5.QtGui import QPainter, QPainterPath


def draw_glyph(painter: QPainter, kind: str, box: QRectF) -> None:
    """Draw ``kind`` inside ``box`` with the painter's current pen.

    The caller owns the pen (colour, weight, gradient) and the brush; this
    function only decides the shape.  Callers that want an outlined glyph pass
    ``Qt.NoBrush``; the send glyph is a filled paper plane instead.
    """
    c = box.center()
    w = min(box.width(), box.height())
    r = w * 0.24

    if kind == "chat":
        bubble = QRectF(c.x() - r * 1.15, c.y() - r, r * 2.3, r * 1.7)
        path = QPainterPath()
        path.addRoundedRect(bubble, r * 0.5, r * 0.5)
        path.moveTo(bubble.left() + r * 0.55, bubble.bottom())
        path.lineTo(bubble.left() + r * 0.45, bubble.bottom() + r * 0.62)
        path.lineTo(bubble.left() + r * 1.1, bubble.bottom())
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "notes":
        page = QRectF(c.x() - r * 0.85, c.y() - r * 1.05, r * 1.7, r * 2.1)
        painter.drawRoundedRect(page, r * 0.28, r * 0.28)
        for offset in (-0.35, 0.05, 0.45):
            y = c.y() + r * offset
            painter.drawLine(
                QPointF(page.left() + r * 0.35, y),
                QPointF(page.right() - r * 0.35, y),
            )
    elif kind == "tools":
        # two tracks, two knobs — the "settings-ish" tool glyph
        for dy, knob in ((-0.42, 0.35), (0.42, -0.3)):
            y = c.y() + r * dy
            painter.drawLine(QPointF(c.x() - r * 1.1, y), QPointF(c.x() + r * 1.1, y))
            painter.drawEllipse(QPointF(c.x() + r * knob, y), r * 0.26, r * 0.26)
    elif kind == "profile":
        painter.drawEllipse(QPointF(c.x(), c.y() - r * 0.5), r * 0.42, r * 0.42)
        path = QPainterPath()
        path.moveTo(c.x() - r * 0.85, c.y() + r * 1.05)
        path.quadTo(c.x(), c.y() + r * 0.15, c.x() + r * 0.85, c.y() + r * 1.05)
        painter.drawPath(path)
    elif kind == "settings":
        # a gear drawn as a ring plus six teeth
        painter.drawEllipse(c, r * 0.62, r * 0.62)
        for step in range(6):
            angle = math.radians(step * 60)
            inner = QPointF(
                c.x() + math.cos(angle) * r * 0.78,
                c.y() + math.sin(angle) * r * 0.78,
            )
            outer = QPointF(
                c.x() + math.cos(angle) * r * 1.12,
                c.y() + math.sin(angle) * r * 1.12,
            )
            painter.drawLine(inner, outer)
    elif kind == "screen":
        # a monitor: frame, stand, base
        frame = QRectF(c.x() - r * 1.15, c.y() - r * 0.95, r * 2.3, r * 1.6)
        painter.drawRoundedRect(frame, r * 0.22, r * 0.22)
        painter.drawLine(
            QPointF(c.x(), frame.bottom()), QPointF(c.x(), frame.bottom() + r * 0.36)
        )
        painter.drawLine(
            QPointF(c.x() - r * 0.5, frame.bottom() + r * 0.38),
            QPointF(c.x() + r * 0.5, frame.bottom() + r * 0.38),
        )
    elif kind == "clock":
        painter.drawEllipse(c, r * 1.08, r * 1.08)
        # hands: to ten past ten, the readable angle
        painter.drawLine(c, QPointF(c.x() + r * 0.06, c.y() - r * 0.62))
        painter.drawLine(c, QPointF(c.x() + r * 0.55, c.y() + r * 0.2))
    elif kind == "spark":
        # the same four-point sparkle as the mark
        size = r * 1.15
        path = QPainterPath()
        path.moveTo(c.x(), c.y() - size)
        path.quadTo(c.x() + size * 0.2, c.y() - size * 0.2, c.x() + size, c.y())
        path.quadTo(c.x() + size * 0.2, c.y() + size * 0.2, c.x(), c.y() + size)
        path.quadTo(c.x() - size * 0.2, c.y() + size * 0.2, c.x() - size, c.y())
        path.quadTo(c.x() - size * 0.2, c.y() - size * 0.2, c.x(), c.y() - size)
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "send":
        # A paper plane pointing right, filled.  Tip on the right, two swept
        # wings and a notch cut into the trailing edge — drawn rather than
        # typed as "↑" so it shares the brand ink instead of being a font run.
        tip = QPointF(c.x() + r * 1.25, c.y() - r * 1.05)
        upper = QPointF(c.x() - r * 1.15, c.y() - r * 0.12)
        notch = QPointF(c.x() - r * 0.32, c.y() + r * 0.02)
        lower = QPointF(c.x() - r * 1.15, c.y() + r * 1.05)
        tail = QPointF(c.x() - r * 0.18, c.y() + r * 0.42)
        path = QPainterPath()
        path.moveTo(tip)
        path.lineTo(upper)
        path.lineTo(notch)
        path.lineTo(lower)
        path.lineTo(tail)
        path.closeSubpath()
        painter.drawPath(path)
    else:  # pragma: no cover - guarded by the callers' tables
        raise ValueError(f"bilinmeyen glif: {kind}")

"""Nora's brand: the **aurora N** mark on a white canvas.

The mark is drawn, never loaded from a file, so it is sharp at every size and
identical on every platform.  It rests on four decisions:

* **A white canvas.** The whole product is white now: light glass, dark ink,
  and this mark as the only saturated thing on screen.  Nothing here is black.
* **Aurora gradient.** Violet → orchid → pink (``#7b5cff → #c44ff0 → #ff4d94``),
  the same three stops everywhere, so the icon, the header tile and the splash
  read as one brand.
* **A capsule N.** Three round-capped strokes drawn with a stroker, which means
  the letter stays legible at 20 px instead of collapsing into a slab.
* **A squircle tile.** The glyph sits on the gradient tile; the tile is the app
  icon, and the bare glyph is the wordmark / in-app tile.

Everything is expressed in fractions of the canvas, so the same code produces
the 16 px tray icon and the 1024 px installer icon.
"""

from __future__ import annotations

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QRadialGradient,
)

#: The three brand stops, in order: violet, orchid, pink.
BRAND_VIOLET = QColor("#7b5cff")
BRAND_ORCHID = QColor("#c44ff0")
BRAND_PINK = QColor("#ff4d94")

#: Ink used for type on the white canvas (never pure black).
INK = QColor("#1b1725")
INK_SOFT = QColor("#6a6380")

#: Gradient stops for the tile, 0 → 1.
GRADIENT_STOPS: tuple[tuple[float, QColor], ...] = (
    (0.0, BRAND_VIOLET),
    (0.5, BRAND_ORCHID),
    (1.0, BRAND_PINK),
)

#: Geometry of the letter, as fractions of the canvas.
STROKE = 0.128  # stroke weight
LETTER_LEFT = 0.272
LETTER_RIGHT = 0.728
LETTER_TOP = 0.266
LETTER_BOTTOM = 0.734

#: Geometry of the tile the letter sits on.
TILE_INSET = 0.040
TILE_RADIUS = 0.232

#: The product's corner language.  The launch card is drawn with this radius,
#: and every window that follows the card uses the same number — otherwise the
#: app looks like a hard rectangle glued to a soft one.
CARD_RADIUS = 30.0

#: How much smaller a nested card should be, so two rounded edges never fight.
CARD_RADIUS_INSET = 8.0


def gradient(stops: tuple[tuple[float, QColor], ...] = GRADIENT_STOPS):
    """The brand gradient across ``rect``."""
    grad = QLinearGradient(QPointF(0, 0), QPointF(1, 1))
    grad.setCoordinateMode(QLinearGradient.ObjectBoundingMode)
    for position, colour in stops:
        grad.setColorAt(position, colour)
    return grad


def tile_path(rect: QRectF, inset: float = TILE_INSET) -> QPainterPath:
    """The squircle the mark sits on."""
    size = min(rect.width(), rect.height())
    box = rect.adjusted(
        size * inset, size * inset, -size * inset, -size * inset
    )
    radius = size * TILE_RADIUS
    path = QPainterPath()
    path.addRoundedRect(box, radius, radius)
    return path


def n_path(rect: QRectF, stroke: float = STROKE) -> QPainterPath:
    """The **N**, as three round-capped strokes.

    Drawn with a stroker rather than as filled polygons: round joins keep the
    letter smooth at every size, and there is no font anywhere in the pipeline.
    """
    size = min(rect.width(), rect.height())
    x0 = rect.center().x() - size / 2.0
    y0 = rect.center().y() - size / 2.0
    weight = stroke * size

    left = x0 + LETTER_LEFT * size + weight / 2.0
    right = x0 + LETTER_RIGHT * size - weight / 2.0
    top = y0 + LETTER_TOP * size + weight / 2.0
    bottom = y0 + LETTER_BOTTOM * size - weight / 2.0

    spine = QPainterPath()
    spine.moveTo(left, top)
    spine.lineTo(left, bottom)
    spine.moveTo(right, top)
    spine.lineTo(right, bottom)
    spine.moveTo(left, top)
    spine.lineTo(right, bottom)

    stroker = QPainterPathStroker()
    stroker.setWidth(weight)
    stroker.setCapStyle(Qt.RoundCap)
    stroker.setJoinStyle(Qt.RoundJoin)
    return stroker.createStroke(spine)


def spark_path(rect: QRectF) -> QPainterPath:
    """Her one accent: a four-point sparkle, drawn from exact quadratics."""
    size = min(rect.width(), rect.height()) / 2.0
    cx, cy = rect.center().x(), rect.center().y()
    path = QPainterPath()
    path.moveTo(cx, cy - size)
    path.quadTo(cx + size * 0.18, cy - size * 0.18, cx + size, cy)
    path.quadTo(cx + size * 0.18, cy + size * 0.18, cx, cy + size)
    path.quadTo(cx - size * 0.18, cy + size * 0.18, cx - size, cy)
    path.quadTo(cx - size * 0.18, cy - size * 0.18, cx, cy - size)
    path.closeSubpath()
    return path


def _paint_tile(
    painter: QPainter,
    rect: QRectF,
    *,
    glow: bool = True,
    rim: bool = True,
) -> QPainterPath:
    """Paint the aurora tile and return its path (for clipping)."""
    size = min(rect.width(), rect.height())
    path = tile_path(rect)
    box = path.boundingRect()

    if glow:
        halo = QRadialGradient(box.center(), box.width() * 0.78)
        halo.setColorAt(0.0, QColor(150, 90, 255, 0))
        halo.setColorAt(0.72, QColor(200, 90, 240, 12))
        halo.setColorAt(1.0, QColor(255, 90, 160, 20))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawRoundedRect(
            box.adjusted(-size * 0.05, -size * 0.05, size * 0.05, size * 0.05),
            size * 0.28,
            size * 0.28,
        )

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(gradient()))
    painter.drawPath(path)

    # A soft top light so the tile reads as a lit object, not flat print.
    sheen = QRadialGradient(QPointF(box.center().x(), box.top()), box.width() * 0.92)
    sheen.setColorAt(0.0, QColor(255, 255, 255, 96))
    sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.setBrush(QBrush(sheen))
    painter.drawPath(path)

    if rim:
        inner = QPainterPath()
        pad = size * 0.028
        inner.addRoundedRect(
            box.adjusted(pad, pad, -pad, -pad),
            size * (TILE_RADIUS - 0.02),
            size * (TILE_RADIUS - 0.02),
        )
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 56), max(1.0, size * 0.010)))
        painter.drawPath(inner)
    return path


def draw_mark(
    painter: QPainter,
    size: int,
    *,
    tile: bool = True,
    glow: bool = True,
    spark: bool = False,
    letter_color: QColor | None = None,
) -> None:
    """Paint the mark in a ``size`` × ``size`` square.

    ``tile=True`` draws the app-icon form (gradient squircle + white N).
    ``tile=False`` draws the bare glyph (wordmark, in-app accent): the N in the
    brand gradient, on transparent, for a white background.
    """
    box = QRectF(0, 0, size, size)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    if tile:
        path = _paint_tile(painter, box, glow=glow and size >= 24)
        painter.setClipPath(path)
        painter.setPen(Qt.NoPen)
        painter.setBrush(letter_color or QColor(255, 255, 255))
        painter.drawPath(n_path(box))
        painter.setClipping(False)
        if spark and size >= 64:
            spark_size = size * 0.135
            spark_rect = QRectF(
                box.left() + size * 0.520 - spark_size / 2.0,
                box.top() + size * 0.318 - spark_size / 2.0,
                spark_size,
                spark_size,
            )
            painter.setBrush(QColor(255, 255, 255))
            painter.drawPath(spark_path(spark_rect))
    else:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient()))
        painter.drawPath(n_path(box, stroke=0.140))
        if spark and size >= 64:
            spark_size = size * 0.135
            spark_rect = QRectF(
                box.left() + size * 0.520 - spark_size / 2.0,
                box.top() + size * 0.318 - spark_size / 2.0,
                spark_size,
                spark_size,
            )
            painter.setBrush(QBrush(gradient()))
            painter.drawPath(spark_path(spark_rect))

    painter.restore()


def _render(size: int, opaque: bool, **kwargs) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.white if opaque else Qt.transparent)
    painter = QPainter(image)
    draw_mark(painter, size, **kwargs)
    painter.end()
    return image


def logo_pixmap(size: int, *, opaque: bool = False, **kwargs) -> QPixmap:
    """The mark as a pixmap.  ``opaque=True`` fills the square white first."""
    pixmap = QPixmap.fromImage(_render(size, opaque, **kwargs))
    return pixmap


def logo_image(size: int, *, opaque: bool = False, **kwargs) -> QImage:
    """The mark as an ARGB image — used by the icon exporter and tests."""
    return _render(size, opaque, **kwargs)


def wordmark_image(width: int = 640, height: int = 160) -> QImage:
    """The bare glyph, for README headers and the installer's white screen."""
    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(Qt.white)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    side = min(width, height)
    draw_mark(painter, side, tile=False)
    painter.end()
    return image


def splash_gradient(painter: QPainter, rect: QRectF) -> None:
    """The splash backdrop: white, warmed by an almost invisible brand bloom.

    Kept here so the launch card and the chat window cannot drift apart, and so
    no module grows its own copy of the palette.
    """
    painter.fillRect(rect, QColor("#ffffff"))
    bloom = QRadialGradient(
        QPointF(rect.left() + rect.width() * 0.30, rect.top() + rect.height() * 0.18),
        rect.width() * 1.15,
    )
    bloom.setColorAt(0.0, QColor(123, 92, 255, 26))
    bloom.setColorAt(0.55, QColor(255, 77, 148, 10))
    bloom.setColorAt(1.0, QColor(255, 255, 255, 0))
    painter.fillRect(rect, QBrush(bloom))


__all__ = [
    "BRAND_ORCHID",
    "CARD_RADIUS",
    "CARD_RADIUS_INSET",
    "BRAND_PINK",
    "BRAND_VIOLET",
    "GRADIENT_STOPS",
    "INK",
    "INK_SOFT",
    "draw_mark",
    "gradient",
    "logo_image",
    "logo_pixmap",
    "n_path",
    "spark_path",
    "splash_gradient",
    "tile_path",
    "wordmark_image",
]

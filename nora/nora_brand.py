"""Nora's brand mark: the white **N** monogram.

The mark is drawn, never loaded from a file, so it is sharp at every size and
identical on every platform.  It is built from a single idea:

* a **modern N monogram** — two vertical strokes and one diagonal, with the
  corners cut at 45° so the letter reads as a brand glyph rather than text;
* **white only** — the mark is meant to sit on glass, on a dark splash card or
  on a white installer background without ever changing colour;
* a **hairline ring** and a small **spark** (her one playful accent) that can be
  switched off when the mark has to be a plain app icon.

Everything is expressed in fractions of the canvas, so the same code produces
the 16 px tray icon and the 512 px installer icon.  Pixel characters keep their
own pixel-art faces; this module is the *brand*, not the character.
"""

from __future__ import annotations


from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

#: The brand white.  Pure white so the mark never tints with the UI theme.
BRAND_WHITE = QColor("#ffffff")

#: Everything the mark is made of, in canvas fractions (0..1).
STROKE = 0.115  # thickness of one letter stroke
TOP = 0.248  # top of the letters
BOTTOM = 0.752  # bottom of the letters
LEFT = 0.272  # left edge of the left stem
RIGHT = 0.728  # right edge of the right stem
CUT = 0.5  # 1.0 = square corners, 0.0 = fully cut

#: The ring around the mark, as fractions of the canvas.
RING_INSET = 0.055
RING_WIDTH = 0.011


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def draw_n(painter: QPainter, rect: QRectF, color: QColor = BRAND_WHITE) -> None:
    """Draw just the letter, centred in ``rect`` — for use inside other marks."""
    size = min(rect.width(), rect.height())
    x0 = rect.center().x() - size / 2.0
    y0 = rect.center().y() - size / 2.0
    s = STROKE * size
    left = x0 + LEFT * size
    right = x0 + RIGHT * size
    top = y0 + TOP * size
    bottom = y0 + BOTTOM * size

    path = QPainterPath()
    path.setFillRule(Qt.WindingFill)
    # left stem
    stem = QPainterPath()
    stem.moveTo(left, top)
    stem.lineTo(left + s, top)
    stem.lineTo(left + s, bottom)
    stem.lineTo(left, bottom)
    stem.closeSubpath()
    path.addPath(stem)
    # right stem
    stem2 = QPainterPath()
    stem2.moveTo(right - s, top)
    stem2.lineTo(right, top)
    stem2.lineTo(right, bottom)
    stem2.lineTo(right - s, bottom)
    stem2.closeSubpath()
    path.addPath(stem2)
    # diagonal: from the top of the left stem to the bottom of the upper-right,
    # stopping one stroke short of the floor so the wedge under it reads as a
    # counter.  A diagonal that lands exactly in the corner closes the gap and
    # the glyph turns into a solid white slab at small sizes.
    diagonal = QPainterPath()
    diagonal.moveTo(left, top)
    diagonal.lineTo(left + s, top)
    diagonal.lineTo(right, bottom - s)
    diagonal.lineTo(right - s, bottom - s)
    diagonal.closeSubpath()
    path.addPath(diagonal)

    painter.save()
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPath(path)
    painter.restore()


def n_quadrants(rect: QRectF) -> list[QPainterPath]:
    """The N split into four bands, for the splash "assemble" animation.

    Each band is a horizontal slice of the finished letter.  Combining them in
    order yields the whole glyph, so an animation can slide them in from the
    sides without ever drawing a different letter.
    """
    bands: list[QPainterPath] = []
    rows = 4
    step = (BOTTOM - TOP) / rows
    for index in range(rows):
        band_top = TOP + step * index
        band_bottom = TOP + step * (index + 1)
        clip = QRectF(
            rect.center().x() - rect.width() / 2.0 + rect.width() * 0.0,
            rect.center().y() - rect.height() / 2.0 + rect.height() * band_top,
            rect.width(),
            rect.height() * (band_bottom - band_top),
        )
        band = QPainterPath()
        band.addRect(clip)
        bands.append(band)
    return bands


def spark_path(rect: QRectF) -> QPainterPath:
    """Her one accent: a four-point sparkle, drawn from exact line segments."""
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


def draw_mark(
    painter: QPainter,
    size: int,
    *,
    ring: bool = True,
    spark: bool = True,
    color: QColor = BRAND_WHITE,
    ring_color: QColor | None = None,
) -> None:
    """Paint the complete logo mark in a ``size`` × ``size`` square.

    ``ring`` and ``spark`` are separate switches: the app icon drops the ring at
    very small sizes where a hairline would turn into grey mush.
    """
    box = QRectF(0, 0, size, size)
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    if ring and size >= 24:
        inset = size * RING_INSET
        ring_rect = box.adjusted(inset, inset, -inset, -inset)
        pen = QPen(ring_color or QColor(255, 255, 255, 150))
        pen.setWidthF(max(1.0, size * RING_WIDTH))
        painter.setBrush(Qt.NoBrush)
        painter.setPen(pen)
        painter.drawEllipse(ring_rect)

    draw_n(painter, box, color)

    if spark and size >= 56:
        # Inside the ring, tucked into the N's top-right counter: on top of the
        # hairline it would read as a smudge instead of an accent.
        # It lives in the N's open counter, tucked under the top bar, so the
        # glyph stays perfectly legible and the hairline ring stays clean.
        spark_size = size * 0.145
        spark_rect = QRectF(
            box.left() + size * 0.528 - spark_size / 2.0,
            box.top() + size * 0.315 - spark_size / 2.0,
            spark_size,
            spark_size,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPath(spark_path(spark_rect))

    painter.restore()


def logo_pixmap(size: int, **kwargs) -> QPixmap:
    """The mark as a transparent pixmap (device-pixel-ratio aware)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    draw_mark(painter, size, **kwargs)
    painter.end()
    return pixmap


def logo_image(size: int, **kwargs) -> QImage:
    """The mark as an ARGB image — used by the icon exporter and tests."""
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    draw_mark(painter, size, **kwargs)
    painter.end()
    return image


def splash_gradient(painter: QPainter, rect: QRectF) -> None:
    """The splash card's dark violet wash, shared by the splash and the chat."""
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    gradient.setColorAt(0.0, QColor(38, 28, 54))
    gradient.setColorAt(0.55, QColor(28, 22, 42))
    gradient.setColorAt(1.0, QColor(20, 16, 32))
    painter.fillRect(rect, gradient)


__all__ = [
    "BRAND_WHITE",
    "draw_mark",
    "draw_n",
    "logo_image",
    "logo_pixmap",
    "spark_path",
    "splash_gradient",
]

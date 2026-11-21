"""Semi-realistic VTuber-style Nora portrait, painted with QPainter at runtime.

The desktop pet draws a softly shaded portrait bust instead of an 8-bit chibi.
Everything is generated from code — no sprite sheets, no downloaded art — so the
app stays offline-installable and license-clean while looking like a modern
VTuber model.

Design brief (user request):
    * realistic girl rather than a cartoon chibi
    * hazel / green-leaning eyes
    * ash-brown "kumral" hair
    * smooth "realistic animation" feel like a VTuber rig

Rendering strategy: the figure is composed from a small number of parametric
shapes (head, hair masses, curtains, fringe) painted at 3× supersampling and
downscaled with smooth transformation.  Frames are memoised, so the 30 FPS pet
loop just blits a cached image.

Geometry map (in portrait units, 260 × 360):
    crown  y= 22     brow  y=112     chin  y=214
    eye line y=136   mouth y=182     shoulders y=250
"""

from __future__ import annotations

from typing import Any, Mapping

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

AVATAR_WIDTH = 260
AVATAR_HEIGHT = 360
SUPERSAMPLE = 3

CX = 130.0  # vertical centre line
CROWN = 22.0
BROW_Y = 112.0
EYE_Y = 136.0
NOSE_Y = 160.0
MOUTH_Y = 182.0
CHIN_Y = 214.0
FACE_HALF = 62.0

DEFAULT_SKIN = "#efc7b1"
DEFAULT_HAIR = "#7d5a44"
DEFAULT_EYE = "#7c9a52"

SUPPORTED_EYE_COLORS = {
    "yesil": "#7c9a52",
    "yeşil": "#7c9a52",
    "hazel": "#8d7a45",
    "ela": "#8d7a45",
    "kahve": "#6f4a34",
    "mavi": "#5b8299",
    "gri": "#7d848a",
}

_LASH = QColor("#3b2822")
_LIP = QColor("#bc8189")
_LIP_DARK = QColor("#9c5a66")


def _color(value: Any, fallback: QColor) -> QColor:
    color = QColor(str(value or ""))
    return color if color.isValid() else QColor(fallback)


def _mix(first: QColor, second: QColor, weight: float) -> QColor:
    weight = max(0.0, min(1.0, weight))
    return QColor(
        round(first.red() + (second.red() - first.red()) * weight),
        round(first.green() + (second.green() - first.green()) * weight),
        round(first.blue() + (second.blue() - first.blue()) * weight),
    )


def _alpha(color: QColor, alpha: int) -> QColor:
    out = QColor(color)
    out.setAlpha(max(0, min(255, alpha)))
    return out


class RealisticCharacter:
    """Stateless portrait renderer shared by the pet widget and tray icon."""

    def __init__(self) -> None:
        self.width = AVATAR_WIDTH
        self.height = AVATAR_HEIGHT
        self._cache: dict[tuple[Any, ...], QImage] = {}

    # -------------------------------------------------------------- public API
    def draw(
        self,
        painter: QPainter,
        *,
        state: str = "idle",
        emotion: str = "happy",
        frame: int = 0,
        appearance: Mapping[str, Any] | None = None,
        talking: bool = False,
        listening: bool = False,
        blinking: bool = False,
        affection: bool = False,
        grounded: bool = True,
        animations: bool = True,
    ) -> None:
        """Mirror of ``PixelCharacter.draw`` so the pet can swap renderers."""
        painter.drawImage(
            QRectF(0, 0, self.width, self.height),
            self.portrait(
                state=state,
                emotion=emotion,
                frame=frame,
                appearance=appearance,
                talking=talking,
                listening=listening,
                blinking=blinking,
                affection=affection,
                grounded=grounded,
                animations=animations,
            ),
        )

    def portrait(
        self,
        *,
        state: str = "idle",
        emotion: str = "happy",
        frame: int = 0,
        appearance: Mapping[str, Any] | None = None,
        talking: bool = False,
        listening: bool = False,
        blinking: bool = False,
        affection: bool = False,
        grounded: bool = True,
        animations: bool = True,
    ) -> QImage:
        state = str(state or "idle").lower()
        emotion = str(emotion or "happy").lower()
        appearance = appearance or {}
        phase = max(0, int(frame)) if animations else 0
        key = (
            state,
            emotion,
            phase % 120,
            bool(talking),
            bool(listening),
            bool(blinking),
            bool(affection),
            bool(grounded),
            bool(animations),
            tuple(
                str(appearance.get(name, ""))
                for name in (
                    "hair_color",
                    "outfit",
                    "accessory",
                    "eye_color",
                    "skin_tone",
                )
            ),
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if len(self._cache) > 300:
            self._cache.clear()
        image = QImage(
            self.width * SUPERSAMPLE,
            self.height * SUPERSAMPLE,
            QImage.Format_ARGB32_Premultiplied,
        )
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHints(
            QPainter.Antialiasing
            | QPainter.SmoothPixmapTransform
            | QPainter.TextAntialiasing,
            True,
        )
        painter.scale(SUPERSAMPLE, SUPERSAMPLE)
        try:
            self._paint(
                painter,
                state=state,
                emotion=emotion,
                phase=phase,
                appearance=appearance,
                talking=talking,
                listening=listening,
                blinking=blinking,
                affection=affection,
                grounded=grounded,
            )
        finally:
            painter.end()
        result = image.scaled(
            self.width,
            self.height,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
        self._cache[key] = result
        return result

    def draw_icon(
        self,
        painter: QPainter,
        size: int = 64,
        appearance: Mapping[str, Any] | None = None,
    ) -> None:
        image = self.portrait(state="idle", appearance=appearance)
        crop = image.copy(28, 18, 204, 204)
        painter.drawImage(QRectF(0, 0, size, size), crop)

    # ------------------------------------------------------------------ paint
    def _paint(
        self,
        painter: QPainter,
        *,
        state: str,
        emotion: str,
        phase: int,
        appearance: Mapping[str, Any],
        talking: bool,
        listening: bool,
        blinking: bool,
        affection: bool,
        grounded: bool,
    ) -> None:
        skin = _color(appearance.get("skin_tone"), QColor(DEFAULT_SKIN))
        hair = _color(appearance.get("hair_color"), QColor(DEFAULT_HAIR))
        eye_value = str(appearance.get("eye_color", "yesil")).lower().strip()
        eye = QColor(
            SUPPORTED_EYE_COLORS.get(
                eye_value,
                eye_value if QColor(eye_value).isValid() else DEFAULT_EYE,
            )
        )
        if not eye.isValid():
            eye = QColor(DEFAULT_EYE)

        breathing = 0.0
        if state not in {"drag", "fall", "jump"}:
            breathing = (-0.7, 0.0, 0.7, 0.0)[(phase // 34) % 4]
        lean = 0.0
        if state == "dance":
            lean = (-2.2, 0.0, 2.2, 0.0)[(phase // 7) % 4]
        elif state in {"walk_left", "walk_right"}:
            lean = -1.2 if state == "walk_left" else 1.2
        elif state == "sleep":
            lean = 2.4
        tilt = -1.4 if emotion == "thinking" else 0.0

        talking_now = bool(talking or state == "talk")
        listening_now = bool(listening or state == "listening")

        painter.save()
        painter.translate(CX, 200 + breathing)
        painter.rotate(lean * 0.5 + tilt)
        painter.translate(-CX, -(200 + breathing))
        try:
            self._body(painter, skin, hair, appearance)
            self._neck(painter, skin)
            self._hair_back(painter, hair)
            self._face(painter, skin)
            self._ears(painter, skin)
            self._lid_wash(painter)
            self._eyes(painter, eye, blinking, listening_now)
            self._brows(painter, hair, emotion)
            self._nose(painter, skin)
            self._lips(painter, phase, talking_now, listening_now, emotion)
            self._hair_front(painter, hair)
            self._accessory(painter, appearance)
            self._mood(painter, emotion, affection)
            self._state_marks(painter, state, phase, listening_now)
        finally:
            painter.restore()

    # ---- body -------------------------------------------------------------
    def _body(self, painter, skin, hair, appearance) -> None:
        outfit = str(appearance.get("outfit", "classic"))
        base = {
            "classic": QColor("#3a3442"),
            "casual": QColor("#d99cab"),
            "night": QColor("#414e6b"),
        }.get(outfit, QColor("#3a3442"))

        # The torso stays inside the canvas with rounded shoulders; letting it
        # bleed to the edges would paint a hard rectangle on the desktop.
        torso = QPainterPath()
        torso.moveTo(50, 372)
        torso.cubicTo(54, 314, 66, 276, 94, 262)
        torso.cubicTo(110, 272, 150, 272, 166, 262)
        torso.cubicTo(194, 276, 206, 314, 210, 372)
        torso.closeSubpath()
        grad = QLinearGradient(QPointF(CX, 252), QPointF(CX, 372))
        grad.setColorAt(0.0, _mix(base, QColor("#ffffff"), 0.40))
        grad.setColorAt(0.40, base)
        grad.setColorAt(0.86, base.darker(120))
        grad.setColorAt(1.0, QColor(base.red(), base.green(), base.blue(), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(torso)

        # neckline: rounded scoop
        scoop = QPainterPath()
        scoop.moveTo(94, 262)
        scoop.cubicTo(106, 296, 154, 296, 166, 262)
        scoop.cubicTo(148, 276, 112, 276, 94, 262)
        scoop.closeSubpath()
        painter.setBrush(_alpha(base.lighter(168), 130))
        painter.drawPath(scoop)

        # collarbones: two soft arcs plus a highlight on each shoulder
        painter.setPen(
            QPen(_alpha(QColor("#2b2030"), 46), 2.4, Qt.SolidLine, Qt.RoundCap)
        )
        painter.setBrush(Qt.NoBrush)
        for sign in (-1, 1):
            arc = QPainterPath(QPointF(CX, 284))
            arc.quadTo(QPointF(CX + sign * 20, 280), QPointF(CX + sign * 36, 290))
            painter.drawPath(arc)
        painter.setPen(
            QPen(_alpha(QColor("#ffffff"), 34), 6.0, Qt.SolidLine, Qt.RoundCap)
        )
        painter.drawArc(QRectF(48, 292, 84, 80), 36 * 16, 58 * 16)
        painter.drawArc(QRectF(128, 292, 84, 80), 86 * 16, 58 * 16)

        # A slim under-layer of hair, so the curtains in front still have a
        # believable mass behind them where they meet the shoulders.
        for sign in (-1, 1):
            under = QPainterPath()
            under.moveTo(CX + sign * 58, 240)
            under.cubicTo(
                CX + sign * 74,
                276,
                CX + sign * 78,
                314,
                CX + sign * 68,
                348,
            )
            under.cubicTo(
                CX + sign * 62,
                356,
                CX + sign * 52,
                352,
                CX + sign * 52,
                340,
            )
            under.cubicTo(
                CX + sign * 60,
                302,
                CX + sign * 56,
                272,
                CX + sign * 46,
                252,
            )
            under.closeSubpath()
            grad_lock = QLinearGradient(
                QPointF(CX + sign * 60, 234), QPointF(CX + sign * 74, 362)
            )
            grad_lock.setColorAt(0.0, hair.darker(150))
            grad_lock.setColorAt(1.0, hair.darker(186))
            painter.setBrush(QBrush(grad_lock))
            painter.setPen(Qt.NoPen)
            painter.drawPath(under)

    def _neck(self, painter, skin) -> None:
        neck = QPainterPath()
        neck.moveTo(111, 186)
        neck.cubicTo(112, 222, 105, 240, 98, 260)
        neck.cubicTo(118, 276, 142, 276, 162, 260)
        neck.cubicTo(155, 240, 148, 222, 149, 186)
        neck.closeSubpath()
        grad = QLinearGradient(QPointF(CX, 188), QPointF(CX, 268))
        grad.setColorAt(0.0, skin.darker(132))
        grad.setColorAt(0.40, skin.darker(112))
        grad.setColorAt(1.0, skin.lighter(102))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(neck)

        # the jaw casts a soft shadow on the throat
        shadow = QRadialGradient(QPointF(CX, 196), 54)
        shadow.setColorAt(0.0, _alpha(QColor("#8d5c50"), 130))
        shadow.setColorAt(1.0, _alpha(QColor("#8d5c50"), 0))
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QRectF(CX - 40, 184, 80, 66))

    # ---- head -------------------------------------------------------------
    def _face_path(self) -> QPainterPath:
        path = QPainterPath(QPointF(CX, CROWN + 26))
        # left temple → cheekbone → jaw → chin
        path.cubicTo(
            CX - FACE_HALF + 6,
            CROWN + 26,
            CX - FACE_HALF,
            BROW_Y - 6,
            CX - FACE_HALF,
            EYE_Y,
        )
        path.cubicTo(
            CX - FACE_HALF,
            EYE_Y + 26,
            CX - FACE_HALF + 8,
            NOSE_Y + 20,
            CX - 34,
            CHIN_Y - 12,
        )
        path.cubicTo(CX - 20, CHIN_Y + 2, CX - 8, CHIN_Y + 6, CX, CHIN_Y + 6)
        path.cubicTo(CX + 8, CHIN_Y + 6, CX + 20, CHIN_Y + 2, CX + 34, CHIN_Y - 12)
        path.cubicTo(
            CX + FACE_HALF - 8,
            NOSE_Y + 20,
            CX + FACE_HALF,
            EYE_Y + 26,
            CX + FACE_HALF,
            EYE_Y,
        )
        path.cubicTo(
            CX + FACE_HALF,
            BROW_Y - 6,
            CX + FACE_HALF - 6,
            CROWN + 26,
            CX,
            CROWN + 26,
        )
        path.closeSubpath()
        return path

    def _face(self, painter, skin) -> None:
        face = self._face_path()
        grad = QRadialGradient(QPointF(CX - 18, 108), 116)
        grad.setColorAt(0.0, _mix(skin, QColor("#ffffff"), 0.18))
        grad.setColorAt(0.60, skin)
        grad.setColorAt(1.0, _mix(skin, QColor("#bd8268"), 0.42))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(face)

        # cheekbone light
        for cx in (CX - 36, CX + 36):
            light = QRadialGradient(QPointF(cx, 150), 32)
            light.setColorAt(0.0, _alpha(QColor("#ffffff"), 50))
            light.setColorAt(1.0, _alpha(QColor("#ffffff"), 0))
            painter.setBrush(QBrush(light))
            painter.drawEllipse(QRectF(cx - 30, 126, 60, 52))

        # warm blush
        for cx in (CX - 40, CX + 40):
            blush = QRadialGradient(QPointF(cx, 164), 26)
            blush.setColorAt(0.0, _alpha(QColor("#d47a7a"), 34))
            blush.setColorAt(1.0, _alpha(QColor("#d47a7a"), 0))
            painter.setBrush(QBrush(blush))
            painter.drawEllipse(QRectF(cx - 30, 142, 60, 44))

        # faint forehead/undereye shading keeps the skin from looking flat
        shade = QLinearGradient(QPointF(CX, BROW_Y - 8), QPointF(CX, 150))
        shade.setColorAt(0.0, _alpha(QColor("#a8705c"), 0))
        shade.setColorAt(1.0, _alpha(QColor("#a8705c"), 0))
        painter.setBrush(QBrush(shade))

    def _ears(self, painter, skin) -> None:
        for sign in (-1, 1):
            x = CX + sign * (FACE_HALF - 2)
            rect = QRectF(x - 6, EYE_Y - 2, 12, 22)
            painter.setPen(Qt.NoPen)
            painter.setBrush(skin.darker(108))
            painter.drawEllipse(rect)
            painter.setPen(QPen(_alpha(QColor("#a9715c"), 80), 1.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(QRectF(x - 3, EYE_Y + 3, 6, 11), 40 * 16, 200 * 16)

    # ---- features ---------------------------------------------------------
    def _lid_wash(self, painter) -> None:
        """Very light warm lid colour; adds depth without eyeshadow glam."""
        painter.setPen(Qt.NoPen)
        for sign in (-1, 1):
            cx = CX + sign * 26
            wash = QRadialGradient(QPointF(cx, EYE_Y - 9), 22)
            wash.setColorAt(0.0, _alpha(QColor("#c79a86"), 42))
            wash.setColorAt(1.0, _alpha(QColor("#c79a86"), 0))
            painter.setBrush(QBrush(wash))
            painter.drawEllipse(QRectF(cx - 24, EYE_Y - 26, 48, 34))

    def _eyes(self, painter, eye, blink, listening) -> None:
        half = 17.0
        open_h = 11.0 * (1.14 if listening else 1.0)
        for sign in (-1, 1):
            cx = CX + sign * 26
            mid = EYE_Y
            upper = QPainterPath(QPointF(cx - half, mid + 1.5))
            upper.cubicTo(
                QPointF(cx - half * 0.42, mid - open_h - 0.6),
                QPointF(cx + half * 0.52, mid - open_h - 0.6),
                QPointF(cx + half, mid),
            )
            lower = QPainterPath(QPointF(cx + half, mid))
            lower.cubicTo(
                QPointF(cx + half * 0.42, mid + open_h * 0.92),
                QPointF(cx - half * 0.48, mid + open_h * 0.98),
                QPointF(cx - half, mid + 1.5),
            )
            almond = QPainterPath(upper)
            almond.connectPath(lower)
            almond.closeSubpath()

            if blink:
                painter.setPen(QPen(_LASH, 2.6, Qt.SolidLine, Qt.RoundCap))
                painter.setBrush(Qt.NoBrush)
                closed = QPainterPath(QPointF(cx - half, mid))
                closed.quadTo(QPointF(cx, mid + 5.4), QPointF(cx + half, mid))
                painter.drawPath(closed)
                painter.setPen(QPen(_LASH, 1.3, Qt.SolidLine, Qt.RoundCap))
                for index, offset in enumerate((-9.0, -1.0, 7.0)):
                    painter.drawLine(
                        QPointF(cx + offset, mid + 1.6),
                        QPointF(cx + offset + 3.2, mid + 4.2 + index * 0.1),
                    )
                continue

            # sclera
            sclera = QLinearGradient(
                QPointF(cx, mid - open_h), QPointF(cx, mid + open_h)
            )
            sclera.setColorAt(0.0, QColor("#d9cfc9"))
            sclera.setColorAt(0.30, QColor("#fdfaf7"))
            sclera.setColorAt(1.0, QColor("#f6ece7"))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(sclera))
            painter.drawPath(almond)

            painter.save()
            painter.setClipPath(almond)
            iris = QRadialGradient(QPointF(cx, mid + 1.0), 12.0)
            iris.setColorAt(0.00, _mix(eye, QColor("#eef4cf"), 0.52))
            iris.setColorAt(0.45, eye)
            iris.setColorAt(0.86, eye.darker(170))
            iris.setColorAt(1.00, eye.darker(215))
            painter.setBrush(QBrush(iris))
            painter.drawEllipse(QRectF(cx - 10.2, mid - 10.4, 20.4, 21.0))
            # limbal ring + pupil
            painter.setPen(QPen(_alpha(eye.darker(215), 190), 1.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(cx - 10.2, mid - 10.4, 20.4, 21.0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#241a14"))
            painter.drawEllipse(QRectF(cx - 4.0, mid - 4.0, 8.0, 8.6))
            # catchlights
            painter.setBrush(QColor(255, 255, 255, 240))
            painter.drawEllipse(QRectF(cx - 7.2, mid - 8.8, 6.0, 5.6))
            painter.setBrush(QColor(255, 255, 255, 150))
            painter.drawEllipse(QRectF(cx + 2.4, mid + 2.6, 3.4, 3.0))
            # lid shadow inside the eye
            lid_shade = QLinearGradient(QPointF(cx, mid - open_h - 1), QPointF(cx, mid))
            lid_shade.setColorAt(0.0, QColor(52, 30, 26, 120))
            lid_shade.setColorAt(1.0, QColor(52, 30, 26, 0))
            painter.setBrush(QBrush(lid_shade))
            painter.drawPath(almond)
            painter.restore()

            # waterline
            painter.setPen(
                QPen(_alpha(QColor("#9c6659"), 170), 1.3, Qt.SolidLine, Qt.RoundCap)
            )
            painter.setBrush(Qt.NoBrush)
            water = QPainterPath(QPointF(cx - half * 0.82, mid + open_h * 0.42))
            water.quadTo(
                QPointF(cx, mid + open_h * 0.86),
                QPointF(cx + half * 0.82, mid + open_h * 0.36),
            )
            painter.drawPath(water)

            # upper lid line and lashes
            painter.setPen(QPen(_LASH, 2.5, Qt.SolidLine, Qt.RoundCap))
            painter.drawPath(upper)
            painter.setPen(QPen(_LASH, 1.4, Qt.SolidLine, Qt.RoundCap))
            outer = 1 if sign > 0 else -1
            for index in range(3):
                base = QPointF(
                    cx + outer * (half - 1.0 - index * 2.4), mid - 1.4 + index * 1.4
                )
                painter.drawLine(
                    base,
                    QPointF(
                        base.x() + outer * (4.6 - index * 0.6),
                        base.y() - 3.4 + index * 0.5,
                    ),
                )
            # inner corner
            painter.setPen(
                QPen(_alpha(QColor("#c08b78"), 150), 1.1, Qt.SolidLine, Qt.RoundCap)
            )
            painter.drawLine(
                QPointF(cx - outer * (half - 1), mid + 1.2),
                QPointF(cx - outer * (half - 4), mid + 2.4),
            )

            # crease above the lash line
            painter.setPen(
                QPen(_alpha(QColor("#b07865"), 105), 1.1, Qt.SolidLine, Qt.RoundCap)
            )
            crease = QPainterPath(QPointF(cx - half * 0.86, mid - open_h * 0.60))
            crease.quadTo(
                QPointF(cx + sign * 1.5, mid - open_h - 4.4),
                QPointF(cx + half * 0.90, mid - open_h * 0.44),
            )
            painter.drawPath(crease)

    def _brows(self, painter, hair, emotion) -> None:
        colour = _mix(hair.darker(150), QColor("#3a2a22"), 0.50)
        lift = -2.4 if emotion in {"surprised", "love"} else 0.0
        pinch = 2.2 if emotion == "angry" else 0.0
        for sign in (-1, 1):
            cx = CX + sign * 26
            inner = QPointF(cx - sign * 17, BROW_Y - 4 + lift + pinch)
            outer = QPointF(cx + sign * 17, BROW_Y - 1 + lift - pinch * 0.4)
            brow = QPainterPath(inner)
            brow.quadTo(QPointF(cx, BROW_Y - 9 + lift), outer)
            painter.setPen(QPen(colour, 3.2, Qt.SolidLine, Qt.RoundCap))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(brow)
            # sparse inner hairs instead of a solid block
            painter.setPen(QPen(_alpha(colour, 105), 1.3, Qt.SolidLine, Qt.RoundCap))
            soft = QPainterPath(QPointF(inner.x() + sign * 2, inner.y() + 2.4))
            soft.quadTo(
                QPointF(cx, BROW_Y - 7 + lift), QPointF(outer.x(), outer.y() + 1.6)
            )
            painter.drawPath(soft)

    def _nose(self, painter, skin) -> None:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(
            QPen(_alpha(QColor("#b97f68"), 150), 1.5, Qt.SolidLine, Qt.RoundCap)
        )
        bridge = QPainterPath(QPointF(CX + 3.4, NOSE_Y - 16))
        bridge.quadTo(QPointF(CX + 1.0, NOSE_Y - 4), QPointF(CX + 5.0, NOSE_Y - 1))
        painter.drawPath(bridge)
        painter.setPen(
            QPen(_alpha(QColor("#9d6251"), 135), 1.3, Qt.SolidLine, Qt.RoundCap)
        )
        for sign in (-1, 1):
            nostril = QPainterPath(QPointF(CX + sign * 5.6, NOSE_Y - 1))
            nostril.quadTo(
                QPointF(CX + sign * 3.2, NOSE_Y + 2.4), QPointF(CX, NOSE_Y + 1.6)
            )
            painter.drawPath(nostril)
        painter.setPen(
            QPen(_alpha(QColor("#ffffff"), 110), 1.1, Qt.SolidLine, Qt.RoundCap)
        )
        painter.drawLine(QPointF(CX + 3.8, NOSE_Y - 15), QPointF(CX + 2.4, NOSE_Y - 7))

    def _lips(self, painter, phase, talking, listening, emotion) -> None:
        if listening:
            mouth = QPainterPath(QPointF(CX - 9, MOUTH_Y - 3))
            mouth.cubicTo(
                QPointF(CX - 4, MOUTH_Y - 8),
                QPointF(CX + 4, MOUTH_Y - 8),
                QPointF(CX + 9, MOUTH_Y - 3),
            )
            mouth.cubicTo(
                QPointF(CX + 4, MOUTH_Y + 8),
                QPointF(CX - 4, MOUTH_Y + 8),
                QPointF(CX - 9, MOUTH_Y - 3),
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(_LIP_DARK)
            painter.drawPath(mouth)
            painter.setBrush(QColor("#c9808b"))
            painter.drawEllipse(QRectF(CX - 4.6, MOUTH_Y + 1.2, 9.2, 4.6))
            return

        if talking and phase % 8 < 4:
            mouth = QPainterPath(QPointF(CX - 8, MOUTH_Y - 4))
            mouth.cubicTo(
                QPointF(CX - 3, MOUTH_Y - 8),
                QPointF(CX + 3, MOUTH_Y - 8),
                QPointF(CX + 8, MOUTH_Y - 4),
            )
            mouth.cubicTo(
                QPointF(CX + 3, MOUTH_Y + 8),
                QPointF(CX - 3, MOUTH_Y + 8),
                QPointF(CX - 8, MOUTH_Y - 4),
            )
            painter.setPen(Qt.NoPen)
            painter.setBrush(_LIP_DARK)
            painter.drawPath(mouth)
            painter.setBrush(QColor("#c9808b"))
            painter.drawEllipse(QRectF(CX - 4.2, MOUTH_Y + 1.0, 8.4, 4.2))
            return

        curve = (
            -1.4 if emotion == "sad" else (1.2 if emotion in {"happy", "love"} else 0.0)
        )

        upper = QPainterPath(QPointF(CX - 9.4, MOUTH_Y - 0.6))
        upper.cubicTo(
            QPointF(CX - 8.2, MOUTH_Y - 4.4),
            QPointF(CX - 3.8, MOUTH_Y - 5.4),
            QPointF(CX - 2.0, MOUTH_Y - 3.6),
        )
        upper.cubicTo(
            QPointF(CX - 1.0, MOUTH_Y - 2.9),
            QPointF(CX + 1.0, MOUTH_Y - 2.9),
            QPointF(CX + 2.0, MOUTH_Y - 3.6),
        )
        upper.cubicTo(
            QPointF(CX + 3.8, MOUTH_Y - 5.4),
            QPointF(CX + 8.2, MOUTH_Y - 4.4),
            QPointF(CX + 9.4, MOUTH_Y - 0.6),
        )
        upper.quadTo(
            QPointF(CX, MOUTH_Y + 1.0 + curve * 0.2), QPointF(CX - 9.4, MOUTH_Y - 0.6)
        )
        grad = QLinearGradient(QPointF(CX, MOUTH_Y - 6), QPointF(CX, MOUTH_Y + 1))
        grad.setColorAt(0.0, _LIP_DARK)
        grad.setColorAt(1.0, _LIP)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(upper)

        lower = QPainterPath(QPointF(CX - 8.8, MOUTH_Y + 0.4))
        lower.cubicTo(
            QPointF(CX - 5.6, MOUTH_Y + 6.2 + curve),
            QPointF(CX + 5.6, MOUTH_Y + 6.2 + curve),
            QPointF(CX + 8.8, MOUTH_Y + 0.4),
        )
        lower.quadTo(
            QPointF(CX, MOUTH_Y + 2.6 + curve), QPointF(CX - 8.8, MOUTH_Y + 0.4)
        )
        grad2 = QLinearGradient(QPointF(CX, MOUTH_Y + 1), QPointF(CX, MOUTH_Y + 8))
        grad2.setColorAt(0.0, QColor("#c2808a"))
        grad2.setColorAt(1.0, QColor("#b06b78"))
        painter.setBrush(QBrush(grad2))
        painter.drawPath(lower)

        painter.setPen(QPen(_alpha(_LIP_DARK, 200), 1.0, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        seam = QPainterPath(QPointF(CX - 9.0, MOUTH_Y - 0.4))
        seam.quadTo(
            QPointF(CX, MOUTH_Y + 1.6 + curve), QPointF(CX + 9.0, MOUTH_Y - 0.4)
        )
        painter.drawPath(seam)
        # lower-lip highlight
        painter.setPen(
            QPen(_alpha(QColor("#ffffff"), 120), 1.5, Qt.SolidLine, Qt.RoundCap)
        )
        painter.drawLine(
            QPointF(CX - 3.4, MOUTH_Y + 4.0 + curve * 0.6),
            QPointF(CX + 2.2, MOUTH_Y + 4.4 + curve * 0.6),
        )
        # upper-lip shadow under the nose
        painter.setPen(QPen(_alpha(QColor("#a8705c"), 60), 1.0))
        painter.drawLine(QPointF(CX - 7, MOUTH_Y - 7.4), QPointF(CX + 7, MOUTH_Y - 7.4))

    # ---- hair -------------------------------------------------------------
    def _hair_back(self, painter, hair) -> None:
        back = QPainterPath()
        back.moveTo(CX, 12)
        back.cubicTo(72, 10, 46, 58, 46, 122)
        back.cubicTo(46, 176, 40, 226, 38, 272)
        back.cubicTo(36, 306, 48, 334, 66, 344)
        back.cubicTo(80, 352, 98, 344, 104, 328)
        back.cubicTo(110, 306, 100, 268, 102, 228)
        back.cubicTo(104, 176, 114, 108, CX, 86)
        back.cubicTo(146, 108, 156, 176, 158, 228)
        back.cubicTo(160, 268, 150, 306, 156, 328)
        back.cubicTo(162, 344, 180, 352, 194, 344)
        back.cubicTo(212, 334, 224, 306, 222, 272)
        back.cubicTo(220, 226, 214, 176, 214, 122)
        back.cubicTo(214, 58, 188, 10, CX, 12)
        back.closeSubpath()
        grad = QLinearGradient(QPointF(CX, 8), QPointF(CX, 348))
        grad.setColorAt(0.0, _mix(hair, QColor("#f4e0c6"), 0.24))
        grad.setColorAt(0.30, hair)
        grad.setColorAt(0.68, hair.darker(120))
        grad.setColorAt(1.0, hair.darker(158))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(back)

        # painterly wave bands for depth
        painter.save()
        painter.setClipPath(back)
        painter.setBrush(Qt.NoBrush)
        for offset in (0.0, 22.0):
            for sign in (-1, 1):
                band = QPainterPath(
                    QPointF(CX + sign * (58 + offset), 150 + offset * 0.4)
                )
                band.cubicTo(
                    QPointF(CX + sign * (44 + offset), 196 + offset * 0.6),
                    QPointF(CX + sign * (52 + offset), 262 + offset * 0.4),
                    QPointF(CX + sign * (62 + offset), 316),
                )
                painter.setPen(
                    QPen(_alpha(hair.darker(178), 62), 7.0, Qt.SolidLine, Qt.RoundCap)
                )
                painter.drawPath(band)
        for sign in (-1, 1):
            hi = QPainterPath(QPointF(CX + sign * 40, 74))
            hi.cubicTo(
                QPointF(CX + sign * 62, 118),
                QPointF(CX + sign * 66, 178),
                QPointF(CX + sign * 70, 236),
            )
            painter.setPen(
                QPen(
                    _alpha(_mix(hair, QColor("#ffe9cf"), 0.42), 120),
                    3.4,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            painter.drawPath(hi)

        # head shadow, clipped so no halo appears on the transparent window
        shadow = QRadialGradient(QPointF(CX, 54), 122)
        shadow.setColorAt(0.0, _alpha(QColor("#1a1114"), 130))
        shadow.setColorAt(1.0, _alpha(QColor("#1a1114"), 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QRectF(2, 8, 256, 200))
        painter.restore()

    def _hair_front(self, painter, hair) -> None:
        """Side-swept fringe plus the face-framing curtains.

        The curtains overlap the outer edge of the face deliberately: without
        them the head reads as a floating oval and the portrait stops looking
        like hair actually grows from a scalp.
        """
        light = _mix(hair, QColor("#f6e3c8"), 0.26)

        # ---- curtains ----------------------------------------------------
        # One continuous mass per side: hugs the temple, skims the cheekbone,
        # then flows over the shoulder and ends in a soft point.  Drawing it in
        # a single path avoids the "floating slab" look of stacked locks.
        for sign in (-1, 1):
            outer = CX + sign * (FACE_HALF + 16)
            inner = CX + sign * (FACE_HALF - 6)
            curtain = QPainterPath(QPointF(CX + sign * 24, 26))
            curtain.cubicTo(
                QPointF(CX + sign * 58, 30),
                QPointF(outer, 62),
                QPointF(outer, 104),
            )
            curtain.cubicTo(
                QPointF(outer, 148),
                QPointF(outer - sign * 4, 196),
                QPointF(outer - sign * 2, 244),
            )
            curtain.cubicTo(
                QPointF(outer + sign * 2, 292),
                QPointF(outer + sign * 6, 322),
                QPointF(outer + sign * 2, 344),
            )
            curtain.cubicTo(
                QPointF(outer - sign * 8, 356),
                QPointF(outer - sign * 24, 352),
                QPointF(outer - sign * 28, 338),
            )
            curtain.cubicTo(
                QPointF(outer - sign * 34, 304),
                QPointF(inner + sign * 4, 268),
                QPointF(inner, 232),
            )
            curtain.cubicTo(
                QPointF(inner - sign * 4, 188),
                QPointF(inner - sign * 2, 140),
                QPointF(CX + sign * 40, 88),
            )
            curtain.cubicTo(
                QPointF(CX + sign * 34, 58),
                QPointF(CX + sign * 28, 38),
                QPointF(CX + sign * 24, 26),
            )
            curtain.closeSubpath()
            grad = QLinearGradient(QPointF(CX, 24), QPointF(CX + sign * 66, 340))
            grad.setColorAt(0.0, _mix(light, QColor("#ffffff"), 0.10))
            grad.setColorAt(0.34, hair)
            grad.setColorAt(0.74, hair.darker(126))
            grad.setColorAt(1.0, hair.darker(168))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawPath(curtain)

            painter.save()
            painter.setClipPath(curtain)
            painter.setBrush(Qt.NoBrush)
            # shadow where the curtain tucks behind the cheek
            painter.setPen(
                QPen(_alpha(hair.darker(195), 95), 2.0, Qt.SolidLine, Qt.RoundCap)
            )
            inner_shadow = QPainterPath(QPointF(inner + sign * 3, 104))
            inner_shadow.cubicTo(
                QPointF(inner + sign * 5, 152),
                QPointF(inner - sign * 2, 200),
                QPointF(inner - sign * 12, 246),
            )
            painter.drawPath(inner_shadow)
            # painterly strand bands
            painter.setPen(
                QPen(_alpha(hair.darker(180), 78), 3.0, Qt.SolidLine, Qt.RoundCap)
            )
            for shift in (0.0, 14.0):
                band = QPainterPath(QPointF(outer - sign * (18 + shift), 120))
                band.cubicTo(
                    QPointF(outer - sign * (26 + shift), 172),
                    QPointF(outer - sign * (14 + shift), 238),
                    QPointF(outer - sign * (22 + shift), 300),
                )
                painter.drawPath(band)
            # specular highlight running down the outer curve
            painter.setPen(
                QPen(_alpha(light.lighter(112), 150), 2.2, Qt.SolidLine, Qt.RoundCap)
            )
            glow = QPainterPath(QPointF(outer - sign * 4, 96))
            glow.cubicTo(
                QPointF(outer - sign * 1, 150),
                QPointF(outer - sign * 4, 208),
                QPointF(outer - sign * 12, 262),
            )
            painter.drawPath(glow)
            painter.restore()

        # ---- fringe ------------------------------------------------------
        # Skull-following "cap" whose inner edge slides diagonally across the
        # forehead: full coverage over the left brow, a triangular sliver of
        # forehead left visible on the right.  That single diagonal is what
        # makes a side part read as a real haircut instead of a wig.
        fringe = QPainterPath(QPointF(46, 146))
        fringe.cubicTo(QPointF(42, 74), QPointF(76, 12), QPointF(CX, 10))
        fringe.cubicTo(QPointF(186, 12), QPointF(216, 68), QPointF(214, 120))
        fringe.cubicTo(QPointF(210, 104), QPointF(204, 92), QPointF(196, 84))
        fringe.cubicTo(QPointF(186, 74), QPointF(172, 68), QPointF(158, 68))
        fringe.cubicTo(QPointF(140, 68), QPointF(124, 78), QPointF(112, 94))
        fringe.cubicTo(QPointF(102, 106), QPointF(92, 118), QPointF(84, 132))
        fringe.cubicTo(QPointF(80, 140), QPointF(76, 148), QPointF(72, 158))
        fringe.closeSubpath()
        grad = QLinearGradient(QPointF(80, 18), QPointF(170, 160))
        grad.setColorAt(0.0, _mix(light, QColor("#ffffff"), 0.12))
        grad.setColorAt(0.46, hair)
        grad.setColorAt(1.0, hair.darker(150))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(fringe)

        # a soft shadow cast by the fringe onto the forehead
        painter.save()
        shade = QLinearGradient(QPointF(CX, 84), QPointF(CX, 124))
        shade.setColorAt(0.0, _alpha(QColor("#8a6349"), 74))
        shade.setColorAt(1.0, _alpha(QColor("#8a6349"), 0))
        painter.setBrush(QBrush(shade))
        painter.drawPath(fringe)
        painter.restore()

        # parting shadow + strand sweep, following the same diagonal
        painter.save()
        painter.setClipPath(fringe)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(
            QPen(_alpha(hair.darker(200), 105), 2.2, Qt.SolidLine, Qt.RoundCap)
        )
        part = QPainterPath(QPointF(CX - 30, 20))
        part.cubicTo(QPointF(CX - 22, 44), QPointF(CX - 16, 54), QPointF(CX - 18, 64))
        painter.drawPath(part)
        painter.setPen(
            QPen(_alpha(hair.darker(172), 110), 1.3, Qt.SolidLine, Qt.RoundCap)
        )
        for start_pt, control, end_pt in (
            ((104, 26), (84, 46), (72, 92)),
            ((114, 28), (96, 56), (88, 100)),
            ((92, 40), (78, 74), (76, 118)),
            ((160, 40), (176, 56), (188, 88)),
            ((176, 52), (194, 72), (204, 104)),
        ):
            path = QPainterPath(QPointF(*start_pt))
            path.quadTo(QPointF(*control), QPointF(*end_pt))
            painter.drawPath(path)
        painter.setPen(
            QPen(_alpha(light.lighter(114), 170), 1.8, Qt.SolidLine, Qt.RoundCap)
        )
        for start_pt, control, end_pt in (
            ((100, 28), (82, 50), (70, 92)),
            ((110, 30), (94, 58), (86, 100)),
            ((186, 60), (196, 84), (200, 112)),
        ):
            path = QPainterPath(QPointF(*start_pt))
            path.quadTo(QPointF(*control), QPointF(*end_pt))
            painter.drawPath(path)
        painter.restore()

    def _accessory(self, painter, appearance) -> None:
        accessory = str(appearance.get("accessory", "none"))
        if accessory == "glasses":
            painter.setPen(QPen(QColor("#3f3830"), 1.9))
            painter.setBrush(_alpha(QColor("#dfe9ee"), 34))
            painter.drawRoundedRect(QRectF(CX - 46, 122, 38, 28), 12, 12)
            painter.drawRoundedRect(QRectF(CX + 8, 122, 38, 28), 12, 12)
            painter.drawLine(QPointF(CX - 8, 132), QPointF(CX + 8, 132))
            painter.drawLine(QPointF(CX - 46, 134), QPointF(CX - 62, 130))
            painter.drawLine(QPointF(CX + 46, 134), QPointF(CX + 62, 130))
            painter.setPen(QPen(_alpha(QColor("#ffffff"), 110), 1.3))
            painter.drawLine(QPointF(CX - 40, 127), QPointF(CX - 26, 124))
            painter.drawLine(QPointF(CX + 14, 127), QPointF(CX + 28, 124))
        elif accessory == "headphones":
            painter.setPen(QPen(QColor("#37344a"), 4.6, Qt.SolidLine, Qt.RoundCap))
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(QRectF(CX - 78, 16, 156, 176), 18 * 16, 144 * 16)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#443f57"))
            painter.drawRoundedRect(QRectF(CX - 86, 112, 20, 54), 9, 9)
            painter.drawRoundedRect(QRectF(CX + 66, 112, 20, 54), 9, 9)
            painter.setBrush(QColor("#8b7ea6"))
            painter.drawRoundedRect(QRectF(CX - 82, 119, 8, 40), 4, 4)
            painter.drawRoundedRect(QRectF(CX + 74, 119, 8, 40), 4, 4)
        elif accessory == "ribbon":
            ribbon = QColor("#bf647f")
            painter.setPen(Qt.NoPen)
            painter.setBrush(ribbon)
            painter.drawEllipse(QRectF(CX + 34, 40, 26, 17))
            painter.drawEllipse(QRectF(CX + 58, 34, 22, 17))
            painter.setBrush(ribbon.darker(128))
            painter.drawEllipse(QRectF(CX + 52, 45, 8, 8))

    # ---- mood / state marks ----------------------------------------------
    def _mood(self, painter, emotion, affection) -> None:
        if emotion == "love" or affection:
            self._sparkle(painter, CX - 82, 62, QColor("#e8879c"), 7)
            self._sparkle(painter, CX + 84, 84, QColor("#e8879c"), 5)
            self._sparkle(painter, CX + 70, 40, QColor("#f0b6c3"), 3.4)
        elif emotion == "angry":
            painter.setPen(QPen(QColor("#c4453f"), 2.8, Qt.SolidLine, Qt.RoundCap))
            for x in (CX + 76, CX + 88):
                painter.drawLine(QPointF(x, 52), QPointF(x + 7, 42))
                painter.drawLine(QPointF(x, 42), QPointF(x + 7, 52))
        elif emotion == "surprised":
            painter.setPen(QPen(QColor("#8f7fa8"), 2.4, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(CX + 80, 40), QPointF(CX + 80, 56))
            painter.drawPoint(QPointF(CX + 80, 63))
        elif emotion == "thinking":
            painter.setPen(Qt.NoPen)
            for radius, y in ((7, 46), (5, 60), (3.4, 71)):
                painter.setBrush(QColor(255, 250, 252, 180))
                painter.drawEllipse(
                    QRectF(CX + 80 - radius, y - radius, radius * 2, radius * 2)
                )
        elif emotion == "sleepy":
            painter.setFont(QFont("Segoe UI", 14, QFont.DemiBold))
            painter.setPen(QColor(196, 180, 214, 205))
            painter.drawText(QRectF(CX + 62, 30, 44, 32), Qt.AlignCenter, "z")
        elif emotion == "smug":
            self._sparkle(painter, CX + 78, 56, QColor("#e0b060"), 5.4)

    def _state_marks(self, painter, state, phase, listening) -> None:
        if listening:
            painter.setPen(
                QPen(QColor(150, 122, 196, 165), 1.9, Qt.SolidLine, Qt.RoundCap)
            )
            painter.setBrush(Qt.NoBrush)
            for index, radius in enumerate((11, 18, 25)):
                if (phase // 8) % 3 >= index:
                    painter.drawArc(
                        QRectF(CX + 78 - radius, 150 - radius, radius * 2, radius * 2),
                        -52 * 16,
                        104 * 16,
                    )
        if state == "sleep":
            painter.setFont(QFont("Segoe UI", 13, QFont.DemiBold))
            painter.setPen(QColor(196, 180, 214, 205))
            painter.drawText(QRectF(CX + 64, 32, 46, 28), Qt.AlignCenter, "z z")

    @staticmethod
    def _sparkle(painter, x, y, color, size) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        path = QPainterPath(QPointF(x, y - size))
        path.quadTo(QPointF(x + size * 0.25, y - size * 0.25), QPointF(x + size, y))
        path.quadTo(QPointF(x + size * 0.25, y + size * 0.25), QPointF(x, y + size))
        path.quadTo(QPointF(x - size * 0.25, y + size * 0.25), QPointF(x - size, y))
        path.quadTo(QPointF(x - size * 0.25, y - size * 0.25), QPointF(x, y - size))
        painter.drawPath(path)

"""Crisp 8-bit-style Nora artwork drawn entirely with QPainter rectangles.

The pet is rendered on a 40×50 logical pixel grid and scaled by an integer
factor of three.  There are no sprite sheets, image files, gradients, rotated
paths or smoothed edges: every mark snaps to the same 3×3 device-pixel grid.
The small tray icon uses the same palette and a 16×16 logical grid.
"""

from __future__ import annotations

from typing import Any, Mapping

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter

PIXEL_SIZE = 3
GRID_WIDTH = 40
GRID_HEIGHT = 50

_OUTLINE = "#2c203a"
_SKIN = "#ffe1cb"
_SKIN_SHADE = "#f2b9a8"
_CREAM = "#fff3e6"
_GOLD = "#ffd166"
_GOLD_SHADE = "#c99135"
_PINK = "#ff8fb3"

DEFAULT_HAIR_COLOR = "#f5f3f0"

_OUTFITS = {
    # Requested black dress; casual/night remain optional user choices.
    "classic": ("#4a4a58", "#1c1c24", "#0c0c12"),
    "casual": ("#ffd1df", "#ef83ad", "#b95783"),
    "night": ("#a2baff", "#647fc7", "#3c559b"),
}

_HEART = (".X.X.", "XXXXX", "XXXXX", ".XXX.", "..X..")
_SPARKLE = (".X.", "XXX", ".X.")
_CROSS = ("X.X", ".X.", "X.X")
_NOTE = ("..XX", "..X.", "..X.", "XXX.", "XXX.")
_Z = ("XXX", "..X", ".X.", "XXX")


def _mix(first: QColor, second: QColor, weight: float) -> QColor:
    weight = max(0.0, min(1.0, weight))
    return QColor(
        round(first.red() + (second.red() - first.red()) * weight),
        round(first.green() + (second.green() - first.green()) * weight),
        round(first.blue() + (second.blue() - first.blue()) * weight),
    )


def _palette(appearance: Mapping[str, Any] | None) -> dict[str, QColor]:
    appearance = appearance or {}
    hair = QColor(str(appearance.get("hair_color", DEFAULT_HAIR_COLOR)))
    if not hair.isValid():
        hair = QColor(DEFAULT_HAIR_COLOR)
    outline = QColor(_OUTLINE)
    light, base, shade = _OUTFITS.get(
        str(appearance.get("outfit", "classic")), _OUTFITS["classic"]
    )
    return {
        "outline": outline,
        "hair": hair,
        "hair_light": _mix(hair, QColor("#ffffff"), 0.55),
        "hair_glint": _mix(hair, QColor("#ffffff"), 0.8),
        "hair_shade": _mix(hair, QColor("#8f8a9c"), 0.5),
        "skin": QColor(_SKIN),
        "skin_shade": QColor(_SKIN_SHADE),
        "cream": QColor(_CREAM),
        "gold": QColor(_GOLD),
        "gold_shade": QColor(_GOLD_SHADE),
        "pink": QColor(_PINK),
        "blush": QColor("#f49ab0"),
        "mouth": QColor("#a45172"),
        "dress_light": QColor(light),
        "dress": QColor(base),
        "dress_shade": QColor(shade),
        "white": QColor("#ffffff"),
        "iris": QColor("#e6384c"),
        "iris_light": QColor("#ff8a95"),
        "pink_iris": QColor("#ff4d6d"),
        "shoe": QColor("#d92b3d"),
        "shoe_light": QColor("#ff6b70"),
        "shoe_shade": QColor("#8f1526"),
        "blue": QColor("#8ed9ff"),
        "red": QColor("#ff7085"),
    }


class _PixelCanvas:
    """Integer-only drawing helper; one logical pixel is ``scale`` device px."""

    def __init__(
        self, painter: QPainter, scale: int, offset_x: int = 0, offset_y: int = 0
    ) -> None:
        self.painter = painter
        self.scale = int(scale)
        self.offset_x = int(offset_x)
        self.offset_y = int(offset_y)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setRenderHint(QPainter.TextAntialiasing, False)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.NoBrush)

    def rect(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: QColor,
        *,
        mirror: bool = False,
    ) -> None:
        if width <= 0 or height <= 0:
            return
        if mirror:
            x = GRID_WIDTH - x - width
        self.painter.fillRect(
            self.offset_x + int(x) * self.scale,
            self.offset_y + int(y) * self.scale,
            int(width) * self.scale,
            int(height) * self.scale,
            color,
        )

    def stamp(
        self,
        pattern: tuple[str, ...],
        x: int,
        y: int,
        color: QColor,
        *,
        mirror: bool = False,
    ) -> None:
        for dy, row in enumerate(pattern):
            for dx, cell in enumerate(row):
                if cell != ".":
                    self.rect(x + dx, y + dy, 1, 1, color, mirror=mirror)

    def frame(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        color: QColor,
        *,
        mirror: bool = False,
    ) -> None:
        self.rect(x, y, width, 1, color, mirror=mirror)
        self.rect(x, y + height - 1, width, 1, color, mirror=mirror)
        self.rect(x, y + 1, 1, height - 2, color, mirror=mirror)
        self.rect(x + width - 1, y + 1, 1, height - 2, color, mirror=mirror)


class PixelCharacter:
    """Stateless retro renderer shared by the desktop pet and tray icon."""

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
        canvas = _PixelCanvas(painter, PIXEL_SIZE)
        colors = _palette(appearance)
        state = str(state).lower()
        emotion = str(emotion).lower()
        phase = max(0, int(frame)) if animations else 0
        talking = bool(talking or state == "talk")
        listening = bool(listening or state == "listening")
        sleeping = state == "sleep"
        sitting = state == "sit"

        # A stepped, solid-alpha shadow stays on the floor while Nora bobs.
        shadow = QColor(44, 32, 58, 38 if grounded else 24)
        if grounded:
            canvas.rect(14, 47, 12, 1, shadow)
            canvas.rect(11, 48, 18, 1, shadow)
        else:
            canvas.rect(16, 48, 8, 1, shadow)

        if sleeping:
            bob = 2 + (1 if (phase // 20) % 2 else 0)
        elif sitting:
            bob = 2 + (-1 if (phase // 30) % 2 else 0)
        elif state == "love":
            bob = -1 if (phase // 12) % 2 else 0
        elif state == "angry":
            bob = -1 if (phase // 8) % 2 else 0
        elif state == "surprised":
            bob = -1 if (phase // 10) % 2 else 0
        elif state in {"walk_left", "walk_right"}:
            bob = -1 if (phase // 6) % 2 else 0
        else:
            bob = -1 if grounded and (phase // 24) % 2 else 0
        sway = 0
        if state == "dance":
            sway = (-1, 0, 1, 0)[(phase // 6) % 4]
            bob += -1 if (phase // 6) % 2 else 0
        painter.save()
        painter.translate(sway * PIXEL_SIZE, bob * PIXEL_SIZE)
        try:
            self._tail(canvas, colors, phase, affection)
            self._back_hair(canvas, colors, phase)
            self._legs(canvas, colors, state, phase)
            self._body(canvas, colors)
            self._arms(canvas, colors, state, emotion, phase, listening)
            self._ears(canvas, colors, phase, listening)
            self._head(canvas, colors)
            self._face(
                canvas, colors, state, emotion, phase, talking, listening, blinking
            )
            self._front_hair(canvas, colors)
            self._star_clip(canvas, colors)
            self._accessory(
                canvas, colors, str((appearance or {}).get("accessory", "none"))
            )
            if listening:
                self._listening_hand(canvas, colors)
        finally:
            painter.restore()
        self._effects(canvas, colors, state, emotion, phase, listening, affection)

    def _tail(
        self, c: _PixelCanvas, p: dict[str, QColor], phase: int, affection: bool
    ) -> None:
        speed = 10 if affection else 22
        sway = (0, 1, 0, -1)[(phase // speed) % 4]
        o, h, glint = p["outline"], p["hair"], p["hair_light"]
        c.rect(28, 38, 6, 4, o)
        c.rect(32, 35, 4, 6, o)
        c.rect(35, 31 + sway, 4, 6, o)
        c.rect(33, 28 + sway, 5, 5, o)
        c.rect(31, 28 + sway, 4, 3, o)
        c.rect(29, 39, 4, 2, h)
        c.rect(33, 35, 2, 5, h)
        c.rect(36, 31 + sway, 2, 6, h)
        c.rect(34, 29 + sway, 3, 3, h)
        c.rect(32, 29 + sway, 2, 1, h)
        c.rect(32, 28 + sway, 3, 1, glint)
        c.rect(36, 31 + sway, 1, 3, glint)

    def _back_hair(self, c: _PixelCanvas, p: dict[str, QColor], phase: int) -> None:
        # Wolfcut: choppy, jaw-length layers with outward flicks, not twin tails.
        sway = (0, 1, 0, -1)[(phase // 16) % 4]
        o, h, glint, shade = p["outline"], p["hair"], p["hair_light"], p["hair_shade"]
        c.rect(9, 27, 22, 5, o)
        c.rect(10, 28, 20, 3, h)
        for x, width, height in ((11, 3, 1), (16, 3, 2), (21, 3, 1), (26, 2, 2)):
            c.rect(x, 31, width, height + 1, o)
            c.rect(x + 1, 31, max(1, width - 1), height, h)
        for mirror in (False, True):
            c.rect(5, 15, 5, 13, o, mirror=mirror)
            c.rect(4, 21, 6, 8, o, mirror=mirror)
            c.rect(3 + sway, 27, 6, 4, o, mirror=mirror)
            c.rect(5 + sway, 31, 3, 2, o, mirror=mirror)
            c.rect(6, 16, 3, 11, h, mirror=mirror)
            c.rect(5, 22, 4, 6, h, mirror=mirror)
            c.rect(4 + sway, 28, 4, 2, h, mirror=mirror)
            c.rect(6 + sway, 30, 1, 2, h, mirror=mirror)
            c.rect(6, 17, 1, 8, glint, mirror=mirror)
            c.rect(5 + sway, 28, 1, 2, glint, mirror=mirror)
            c.rect(8, 18, 1, 10, shade, mirror=mirror)

    def _legs(
        self, c: _PixelCanvas, p: dict[str, QColor], state: str, phase: int
    ) -> None:
        o, skin, cream = p["outline"], p["skin"], p["cream"]
        boot, trim = p["shoe"], p["shoe_light"]
        if state in {"sit", "sleep"}:
            c.rect(13, 41, 4, 3, o)
            c.rect(23, 41, 4, 3, o)
            c.rect(14, 41, 2, 2, skin)
            c.rect(24, 41, 2, 2, skin)
            c.rect(9, 43, 8, 3, o)
            c.rect(23, 43, 8, 3, o)
            c.rect(10, 44, 6, 1, boot)
            c.rect(24, 44, 6, 1, boot)
            c.rect(10, 45, 6, 1, p["shoe_shade"])
            c.rect(24, 45, 6, 1, p["shoe_shade"])
            c.rect(10, 43, 3, 1, cream)
            c.rect(27, 43, 3, 1, cream)
            return
        moving = state in {"walk_left", "walk_right", "dance"}
        stride = (0, 1, 0, -1)[(phase // 6) % 4] if moving else 0
        if state == "walk_left":
            stride = -stride
        tucked = state in {"jump", "fall", "drag"}
        top = 40 if tucked else 41
        for x, lift in ((15, -1 if stride > 0 else 0), (22, -1 if stride < 0 else 0)):
            c.rect(x, top + lift, 3, 4, o)
            c.rect(x + 1, top + lift, 1, 2, skin)
            c.rect(x, top + 2 + lift, 3, 2, cream)
            c.rect(x - 2, top + 4 + lift, 6, 2, o)
            c.rect(x - 1, top + 4 + lift, 4, 1, boot)
            c.rect(x - 1, top + 4 + lift, 2, 1, trim)
            c.rect(x - 1, top + 5 + lift, 4, 1, p["shoe_shade"])

    def _body(self, c: _PixelCanvas, p: dict[str, QColor]) -> None:
        o, skin = p["outline"], p["skin"]
        light, base, shade = p["dress_light"], p["dress"], p["dress_shade"]
        c.rect(18, 29, 4, 3, o)
        c.rect(19, 29, 2, 3, skin)
        c.rect(14, 30, 12, 2, o)
        c.rect(13, 32, 14, 3, o)
        c.rect(12, 35, 16, 3, o)
        c.rect(11, 38, 18, 3, o)
        c.rect(12, 41, 16, 1, o)
        c.rect(15, 31, 10, 2, base)
        c.rect(14, 33, 12, 3, base)
        c.rect(13, 36, 14, 2, base)
        c.rect(12, 38, 16, 2, base)
        c.rect(13, 40, 14, 1, light)
        for x in (14, 18, 22, 26):
            c.rect(x, 40, 1, 1, p["cream"])  # little lace dots on the black hem
        c.rect(15, 33, 2, 3, light)
        for x in (16, 20, 24):
            c.rect(x, 37, 1, 3, shade)
        c.rect(15, 30, 4, 2, p["cream"])
        c.rect(21, 30, 4, 2, p["cream"])
        c.rect(17, 32, 6, 1, p["cream"])
        c.rect(17, 32, 2, 2, p["shoe"])
        c.rect(21, 32, 2, 2, p["shoe"])
        c.rect(19, 33, 2, 2, p["gold_shade"])
        c.rect(19, 33, 2, 1, p["gold"])
        c.rect(19, 34, 1, 1, o)

    def _arms(
        self,
        c: _PixelCanvas,
        p: dict[str, QColor],
        state: str,
        emotion: str,
        phase: int,
        listening: bool,
    ) -> None:
        o, skin, cream = p["outline"], p["skin"], p["cream"]
        sleeve = p["dress"]
        swing = (0, 1, 0, -1)[(phase // 6) % 4] if state.startswith("walk_") else 0
        dancing = state == "dance"
        jumping = state in {"jump", "drag"}
        falling = state == "fall"
        waving = state == "wave" or (
            emotion == "happy" and state == "idle" and (phase // 48) % 4 == 0
        )
        angry = state == "angry" or emotion == "angry"
        surprised = state == "surprised" or emotion == "surprised"
        wave = (0, -1, 0, 1)[(phase // 8) % 4]

        def relaxed_left(dy: int = 0) -> None:
            c.rect(10, 34 + dy, 4, 5, o)
            c.rect(11, 35 + dy, 2, 3, skin)
            c.rect(10, 34 + dy, 4, 1, cream)
            c.rect(11, 31, 3, 4, sleeve)

        def relaxed_right(dy: int = 0) -> None:
            c.rect(26, 34 + dy, 4, 5, o)
            c.rect(27, 35 + dy, 2, 3, skin)
            c.rect(26, 34 + dy, 4, 1, cream)
            c.rect(26, 31, 3, 4, sleeve)

        def raised_left() -> None:
            c.rect(8, 28, 3, 5, o)
            c.rect(9, 29, 1, 3, skin)
            c.rect(7, 25, 4, 4, o)
            c.rect(8, 26, 2, 2, skin)
            c.rect(11, 31, 3, 3, sleeve)

        def raised_right() -> None:
            c.rect(29, 28, 3, 5, o)
            c.rect(30, 29, 1, 3, skin)
            c.rect(29, 25, 4, 4, o)
            c.rect(30, 26, 2, 2, skin)
            c.rect(26, 31, 3, 3, sleeve)

        if dancing or jumping:
            raised_left()
        elif falling:
            c.rect(7, 32, 5, 3, o)
            c.rect(8, 33, 3, 1, skin)
            c.rect(11, 31, 3, 3, sleeve)
        elif angry:
            c.rect(10, 33, 3, 4, o)
            c.rect(11, 34, 1, 2, skin)
            c.rect(12, 36, 3, 2, skin)
            c.rect(11, 31, 3, 3, sleeve)
        elif surprised:
            c.rect(9, 30, 3, 5, o)
            c.rect(10, 31, 1, 3, skin)
            c.rect(11, 31, 3, 3, sleeve)
        else:
            relaxed_left(swing)

        if listening:
            c.rect(27, 31, 3, 4, sleeve)
        elif dancing or jumping:
            raised_right()
        elif falling:
            c.rect(28, 32, 5, 3, o)
            c.rect(29, 33, 3, 1, skin)
            c.rect(26, 31, 3, 3, sleeve)
        elif waving:
            c.rect(27, 31, 3, 3, sleeve)
            c.rect(30, 28 + wave, 3, 4, o)
            c.rect(31, 29 + wave, 1, 2, skin)
            c.rect(33, 24 + wave, 4, 5, o)
            c.rect(34, 25 + wave, 2, 3, skin)
            c.rect(33, 28 + wave, 3, 1, cream)
        elif state == "yawn":
            c.rect(27, 26, 3, 6, o)
            c.rect(28, 27, 1, 4, skin)
            c.rect(26, 24, 4, 3, o)
            c.rect(27, 25, 2, 1, skin)
            c.rect(26, 31, 3, 3, sleeve)
        elif emotion == "thinking":
            c.rect(27, 28, 3, 5, o)
            c.rect(28, 29, 1, 3, skin)
            c.rect(26, 27, 3, 2, skin)
            c.rect(26, 31, 3, 3, sleeve)
        elif angry:
            c.rect(27, 33, 3, 4, o)
            c.rect(28, 34, 1, 2, skin)
            c.rect(25, 36, 3, 2, skin)
            c.rect(26, 31, 3, 3, sleeve)
        elif surprised:
            c.rect(28, 30, 3, 5, o)
            c.rect(29, 31, 1, 3, skin)
            c.rect(26, 31, 3, 3, sleeve)
        else:
            relaxed_right(-swing)

    def _ears(
        self, c: _PixelCanvas, p: dict[str, QColor], phase: int, listening: bool
    ) -> None:
        o, h, pink, cream = p["outline"], p["hair"], p["pink"], p["cream"]
        twitch = -1 if listening and (phase // 8) % 2 else 0
        for mirror, dy in ((False, 0), (True, twitch)):
            rows = (
                (2, 10, 2),
                (3, 9, 4),
                (4, 9, 5),
                (5, 8, 7),
                (6, 8, 8),
                (7, 7, 10),
                (8, 7, 11),
            )
            for y, x, width in rows:
                c.rect(x, y + dy, width, 1, o, mirror=mirror)
            c.rect(10, 4 + dy, 1, 1, pink, mirror=mirror)
            c.rect(10, 5 + dy, 2, 1, pink, mirror=mirror)
            c.rect(9, 6 + dy, 4, 1, pink, mirror=mirror)
            c.rect(9, 7 + dy, 5, 1, pink, mirror=mirror)
            c.rect(8, 8 + dy, 7, 1, h, mirror=mirror)
            c.rect(10, 6 + dy, 2, 1, cream, mirror=mirror)

    def _head(self, c: _PixelCanvas, p: dict[str, QColor]) -> None:
        o, hair, skin = p["outline"], p["hair"], p["skin"]
        rows = [(9, 12, 16), (10, 10, 20), (11, 9, 22), (12, 8, 24)]
        rows.extend((y, 7, 26) for y in range(13, 25))
        rows.extend(
            ((25, 8, 24), (26, 9, 22), (27, 10, 20), (28, 12, 16), (29, 14, 12))
        )
        for y, x, width in rows:
            c.rect(x, y, width, 1, o)
        c.rect(17, 8, 6, 1, o)
        c.rect(18, 8, 4, 1, hair)
        c.rect(19, 7, 2, 1, hair)
        c.rect(8, 16, 24, 9, skin)
        c.rect(9, 25, 22, 1, skin)
        c.rect(10, 26, 20, 1, skin)
        c.rect(11, 27, 18, 1, skin)
        c.rect(13, 28, 14, 1, p["skin_shade"])
        for y, x, width in (
            (10, 12, 16),
            (11, 10, 20),
            (12, 9, 22),
            (13, 8, 24),
            (14, 8, 24),
            (15, 8, 24),
        ):
            c.rect(x, y, width, 1, hair)
        c.rect(13, 11, 7, 1, p["hair_light"])
        c.rect(11, 12, 3, 1, p["hair_light"])
        c.rect(22, 12, 5, 1, p["hair_glint"])

    def _face(
        self,
        c: _PixelCanvas,
        p: dict[str, QColor],
        state: str,
        emotion: str,
        phase: int,
        talking: bool,
        listening: bool,
        blinking: bool,
    ) -> None:
        o, mouth = p["outline"], p["mouth"]
        closed = blinking or state in {"sleep", "yawn"}
        surprised = emotion == "surprised" or state == "surprised"
        love = emotion == "love" or state == "love"
        angry = emotion == "angry" or state == "angry"
        sad = emotion == "sad"
        smug = emotion == "smug" or state == "sit"
        sleepy = emotion == "sleepy" and state != "sleep"
        iris = p["pink_iris"] if love else p["iris"]
        # Larger, rounded sparkly eyes read as sweeter at 120×150 while keeping
        # the requested red iris palette. Corners are omitted, not anti-aliased.
        for x in (10, 23):
            if closed:
                c.stamp((".XXXX.", "X....X"), x, 22, o)
                continue
            c.rect(x + 1, 19, 5, 1, o)
            c.rect(x, 20, 7, 4, o)
            c.rect(x + 1, 24, 5, 1, o)
            c.rect(x + 1, 20, 5, 4, p["white"])
            if surprised:
                c.rect(x + 1, 21, 5, 2, iris)
                c.rect(x + 2, 21, 2, 2, o)
                c.rect(x + 1, 20, 2, 2, p["white"])
            else:
                c.rect(x + 1, 20, 5, 4, iris)
                c.rect(x + 3, 21, 2, 3, o)
                c.rect(x + 1, 20, 2, 2, p["white"])
                c.rect(x + 5, 23, 1, 1, p["white"])
                c.rect(x + 2, 23, 3, 1, p["iris_light"])
            c.rect(x - 1, 19, 1, 1, o)
            c.rect(x + 7, 19, 1, 1, o)
            if smug or sleepy:
                c.rect(x, 19, 7, 2, o)
        if angry:
            c.rect(11, 17, 2, 1, o)
            c.rect(13, 18, 3, 1, o)
            c.rect(27, 17, 2, 1, o)
            c.rect(24, 18, 3, 1, o)
        elif sad:
            c.rect(12, 18, 3, 1, o)
            c.rect(11, 17, 1, 1, o)
            c.rect(25, 18, 3, 1, o)
            c.rect(28, 17, 1, 1, o)
            c.rect(28, 25, 1, 2, p["blue"])
        elif listening or emotion == "thinking":
            c.rect(12, 16, 4, 1, p["hair_shade"])
            c.rect(24, 17, 4, 1, p["hair_shade"])
        c.rect(9, 25, 3, 2, p["blush"])
        c.rect(28, 25, 3, 2, p["blush"])
        c.rect(10, 25, 1, 1, p["pink"])
        c.rect(29, 25, 1, 1, p["pink"])
        c.rect(20, 25, 1, 1, p["skin_shade"])
        if state == "sleep":
            c.rect(20, 27, 1, 1, mouth)
        elif state == "yawn":
            height = 3 if (phase // 10) % 2 == 0 else 2
            c.rect(19, 26, 3, height, o)
            c.rect(20, 27, 1, 1, p["pink"])
        elif talking:
            height = 2 if (phase // 6) % 2 == 0 else 1
            c.rect(19, 26, 3, height, o)
            if height == 2:
                c.rect(20, 27, 1, 1, p["pink"])
        elif surprised:
            c.rect(19, 26, 3, 2, o)
            c.rect(20, 27, 1, 1, p["pink"])
        elif angry or sad:
            c.rect(19, 27, 1, 1, mouth)
            c.rect(20, 26, 1, 1, mouth)
            c.rect(21, 27, 1, 1, mouth)
        else:
            c.stamp(("X.X.X", ".X.X."), 18, 26, mouth)

    def _front_hair(self, c: _PixelCanvas, p: dict[str, QColor]) -> None:
        # Choppy wolfcut fringe and face-framing layers.
        h, glint, shade = p["hair"], p["hair_light"], p["hair_shade"]
        c.rect(8, 15, 24, 2, h)
        c.rect(9, 16, 4, 3, h)
        c.rect(10, 19, 2, 1, h)
        c.rect(14, 16, 3, 2, h)
        c.rect(16, 18, 2, 2, h)
        c.rect(20, 16, 4, 3, h)
        c.rect(22, 19, 2, 1, h)
        c.rect(25, 16, 3, 2, h)
        c.rect(26, 18, 2, 1, h)
        c.rect(8, 16, 2, 11, h)
        c.rect(30, 16, 2, 11, h)
        c.rect(7, 25, 2, 3, h)
        c.rect(31, 25, 2, 3, h)
        c.rect(6, 27, 2, 1, h)
        c.rect(32, 27, 2, 1, h)
        c.rect(8, 20, 1, 6, glint)
        c.rect(31, 20, 1, 6, shade)
        c.rect(10, 16, 2, 1, glint)
        c.rect(21, 16, 2, 1, p["hair_glint"])
        c.rect(18, 9, 3, 1, glint)

    def _star_clip(self, c: _PixelCanvas, p: dict[str, QColor]) -> None:
        # Tiny red heart pin echoing the eyes and shoes.
        c.stamp(("X.X", "XXX", ".X."), 9, 13, p["shoe"])
        c.rect(10, 13, 1, 1, p["shoe_light"])

    def _accessory(self, c: _PixelCanvas, p: dict[str, QColor], accessory: str) -> None:
        o = p["outline"]
        if accessory == "headphones":
            accent, light = p["dress_light"], p["iris_light"]
            c.rect(12, 8, 16, 1, o)
            c.rect(9, 9, 3, 2, o)
            c.rect(28, 9, 3, 2, o)
            c.rect(7, 11, 2, 8, o)
            c.rect(31, 11, 2, 8, o)
            c.rect(13, 8, 14, 1, accent)
            for mirror in (False, True):
                c.rect(5, 18, 4, 7, o, mirror=mirror)
                c.rect(6, 19, 2, 5, accent, mirror=mirror)
                c.rect(6, 20, 1, 2, light, mirror=mirror)
        elif accessory == "glasses":
            frame = QColor("#4a315c")
            c.frame(10, 19, 8, 7, frame)
            c.frame(22, 19, 8, 7, frame)
            c.rect(18, 21, 4, 1, frame)
            c.rect(11, 20, 1, 1, p["white"])
            c.rect(23, 20, 1, 1, p["white"])
        elif accessory == "ribbon":
            c.rect(28, 11, 3, 3, o)
            c.rect(34, 11, 3, 3, o)
            c.rect(31, 12, 3, 2, o)
            c.rect(29, 14, 2, 2, o)
            c.rect(34, 14, 2, 2, o)
            c.rect(29, 12, 2, 1, p["pink"])
            c.rect(34, 12, 2, 1, p["pink"])
            c.rect(31, 12, 3, 2, p["gold"])
            c.rect(30, 14, 1, 1, p["pink"])
            c.rect(34, 14, 1, 1, p["pink"])

    def _listening_hand(self, c: _PixelCanvas, p: dict[str, QColor]) -> None:
        o, skin = p["outline"], p["skin"]
        c.rect(28, 30, 3, 3, p["dress"])
        c.rect(30, 24, 3, 7, o)
        c.rect(31, 25, 1, 5, skin)
        c.rect(31, 18, 4, 6, o)
        c.rect(32, 19, 2, 4, skin)
        c.rect(32, 20, 1, 2, p["skin_shade"])
        c.rect(31, 23, 3, 1, p["cream"])

    def _effects(
        self,
        c: _PixelCanvas,
        p: dict[str, QColor],
        state: str,
        emotion: str,
        phase: int,
        listening: bool,
        affection: bool,
    ) -> None:
        if listening:
            c.stamp((".X", "X.", "X.", ".X"), 35, 17, p["pink"])
            if (phase // 8) % 2:
                c.stamp(("..X", ".X.", "X..", ".X.", "..X"), 36, 16, p["iris_light"])
            else:
                c.stamp((".X", "X.", ".X"), 37, 18, p["iris_light"])
        if state == "idle" and emotion == "happy" and (phase // 24) % 4 == 1:
            c.stamp(_SPARKLE, 4, 10, p["gold"])
        if state == "dance":
            drift = (0, -1, 0, 1)[(phase // 10) % 4]
            c.stamp(_NOTE, 2, 20 + drift, p["hair_light"])
            c.stamp(_NOTE, 34, 12 - drift, p["shoe_light"])
        if emotion == "love" or state == "love" or affection:
            drift = (0, -1, 0, 1)[(phase // 12) % 4]
            c.stamp(_HEART, 2, 10 + drift, p["pink_iris"])
            c.stamp(_HEART, 33, 4 - drift, p["pink"])
            c.stamp(_HEART, 3, 32 - drift, p["iris_light"])
        elif emotion == "angry" or state == "angry":
            c.stamp(_CROSS, 3, 12, p["red"])
            c.stamp(_CROSS, 34, 8, p["red"])
        elif emotion == "surprised" or state == "surprised":
            c.stamp(_SPARKLE, 3, 14, p["gold"])
            c.stamp(_SPARKLE, 35, 10, p["gold"])
        if state == "sleep" or emotion == "sleepy":
            rise = (phase // 12) % 3
            c.stamp(_Z, 32, 12 - rise, p["hair_shade"])
            c.stamp(_Z, 35, 6 - rise, p["iris_light"])
        if state == "drag":
            c.rect(34, 16, 1, 2, p["blue"])
            c.rect(34, 18, 2, 1, p["blue"])

    @staticmethod
    def draw_icon(
        painter: QPainter, size: int = 64, appearance: Mapping[str, Any] | None = None
    ) -> None:
        """A matching 16×16 cat-face icon, scaled only by whole pixels."""
        scale = max(1, int(size) // 16)
        offset = (int(size) - 16 * scale) // 2
        c = _PixelCanvas(painter, scale, offset, offset)
        p = _palette(appearance)
        o, h, skin = p["outline"], p["hair"], p["skin"]
        for mirror in (False, True):
            c.rect(3, 1, 2, 1, o, mirror=mirror)
            c.rect(2, 2, 4, 1, o, mirror=mirror)
            c.rect(2, 3, 5, 2, o, mirror=mirror)
            c.rect(3, 3, 2, 1, p["pink"], mirror=mirror)
        rows = (
            (4, 3, 10),
            (5, 2, 12),
            (6, 1, 14),
            (7, 1, 14),
            (8, 1, 14),
            (9, 1, 14),
            (10, 1, 14),
            (11, 1, 14),
            (12, 2, 12),
            (13, 3, 10),
            (14, 5, 6),
        )
        for y, x, width in rows:
            c.rect(x, y, width, 1, o)
        c.rect(3, 5, 10, 3, h)
        c.rect(2, 7, 12, 1, h)
        c.rect(3, 8, 10, 4, skin)
        c.rect(4, 12, 8, 1, skin)
        c.rect(5, 13, 6, 1, p["skin_shade"])
        c.rect(3, 8, 2, 3, h)
        c.rect(11, 8, 2, 3, h)
        c.rect(4, 6, 3, 2, h)
        c.rect(8, 6, 3, 2, h)
        c.rect(5, 5, 3, 1, p["hair_light"])
        for x in (4, 10):
            c.rect(x, 9, 2, 3, o)
            c.rect(x, 9, 1, 1, p["white"])
            c.rect(x, 11, 2, 1, p["iris"])
        c.rect(3, 11, 1, 1, p["blush"])
        c.rect(12, 11, 1, 1, p["blush"])
        c.stamp(("X.X", ".X."), 7, 12, p["mouth"])
        c.rect(4, 5, 1, 1, p["shoe"])

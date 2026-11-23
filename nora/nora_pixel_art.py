"""8-bit Nora: a pixel-art girl in a cream turtleneck, drawn with rectangles.

This replaces the old cat-girl.  The artwork follows the reference sticker:
**caramel-brown bob hair, big green eyes, ribbed cream turtleneck, white
pleated skirt, brown loafers** — but everything is snapped to a 40×50 logical
grid and scaled by an integer factor, so edges stay perfectly square.

Design rules that keep the look crisp:

* only ``fillRect`` on whole device pixels — no lines, no gradients, no
  antialiasing, no rotated paths;
* one global outline colour, one shade colour per material, never a blur;
* the same palette feeds the 16×16 tray icon.

Nothing here reads a file or the network: the character is drawn from code.
"""

from __future__ import annotations

from typing import Any, Mapping

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter

#: Logical grid the character is composed on (before integer scaling).
GRID_WIDTH = 40
GRID_HEIGHT = 54
#: How many device pixels one logical pixel becomes.
PIXEL_SIZE = 3

# ---------------------------------------------------------------- palette
_OUTLINE = "#2b2233"

_SKIN = "#ffdbc4"
_SKIN_SHADE = "#f0b49c"
_SKIN_DEEP = "#d9947f"

_HAIR = "#a9743f"
_HAIR_LIGHT = "#c9955c"
_HAIR_DARK = "#7a4f2a"

#: The cream ribbed turtleneck from the reference.
_CREAM = "#fff5e4"
_CREAM_SHADE = "#e8d7bd"
_CREAM_DEEP = "#cdb896"

#: The white pleated skirt.
_SKIRT = "#fbfbfd"
_SKIRT_SHADE = "#dfe0e8"
_SKIRT_DEEP = "#bcbdc9"

#: Brown loafers.
_SHOE = "#6b4229"
_SHOE_DARK = "#452a19"

_EYE_WHITE = "#fdfdff"
_EYE_GREEN = "#46ab45"
_EYE_GREEN_DARK = "#2b7d34"
_EYE_PUPIL = "#1d2126"
_LASH = "#241a2b"

_MOUTH = "#b8536a"
_BLUSH = "#ff9fa8"

DEFAULT_HAIR_COLOR = _HAIR

#: Outfit variants keep the silhouette and only swap fabric colours.
_OUTFITS: dict[str, tuple[str, str, str]] = {
    "cream": (_CREAM, _CREAM_SHADE, _CREAM_DEEP),
    "classic": ("#3f3f4d", "#26262f", "#14141a"),
    "casual": ("#ffd1df", "#ef83ad", "#b95783"),
    "night": ("#a2baff", "#647fc7", "#3c559b"),
}

# ------------------------------------------------------------- little icons
_HEART = (".X.X.", "XXXXX", "XXXXX", ".XXX.", "..X..")
_SPARKLE = (".X.", "XXX", ".X.")
_NOTE = ("..XX", "..X.", "..X.", "XXX.", "XXX.")
_Z = ("XXX", "..X", ".X.", "XXX")
_QUESTION = ("XXX", "..X", ".X.", "...", ".X.")
_ANGER = ("X.X", ".X.", "X.X")
_SWEAT = (".X.", "XXX", ".X.")


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
    fabric, fabric_shade, fabric_deep = _OUTFITS.get(
        str(appearance.get("outfit", "cream")), _OUTFITS["cream"]
    )
    return {
        "outline": QColor(_OUTLINE),
        "skin": QColor(_SKIN),
        "skin_shade": QColor(_SKIN_SHADE),
        "skin_deep": QColor(_SKIN_DEEP),
        "hair": hair,
        "hair_light": _mix(hair, QColor("#ffffff"), 0.28),
        "hair_dark": _mix(hair, QColor("#000000"), 0.30),
        "cloth": QColor(fabric),
        "cloth_shade": QColor(fabric_shade),
        "cloth_deep": QColor(fabric_deep),
        "skirt": QColor(_SKIRT),
        "skirt_shade": QColor(_SKIRT_SHADE),
        "skirt_deep": QColor(_SKIRT_DEEP),
        "shoe": QColor(_SHOE),
        "shoe_dark": QColor(_SHOE_DARK),
        "eye_white": QColor(_EYE_WHITE),
        "eye_green": QColor(_EYE_GREEN),
        "eye_green_dark": QColor(_EYE_GREEN_DARK),
        "eye_pupil": QColor(_EYE_PUPIL),
        "lash": QColor(_LASH),
        "mouth": QColor(_MOUTH),
        "blush": QColor(_BLUSH),
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
    """Stateless 8-bit renderer shared by the desktop pet and the tray icon."""

    #: Logical bounding box of the figure (used by callers for hit testing).
    WIDTH = GRID_WIDTH
    HEIGHT = GRID_HEIGHT

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
        sleeping = state == "sleep"
        sitting = state in {"sit", "watch"}

        # --- vertical bob: a couple of logical pixels, never smooth ---------
        if sleeping:
            bob = 1 + (1 if (phase // 20) % 2 else 0)
        elif sitting:
            bob = 1 + (1 if (phase // 30) % 2 else 0)
        elif state == "land":
            bob = 3 if (phase // 6) % 2 else 2
        elif state in {"walk_left", "walk_right", "dance"}:
            bob = -1 if (phase // 6) % 2 else 0
        elif state in {"love", "angry", "surprised"}:
            bob = -1 if (phase // 12) % 2 else 0
        elif state == "giggle":
            bob = -1 if (phase // 4) % 2 else 0
        else:
            bob = -1 if grounded and (phase // 24) % 2 else 0

        sway = 0
        if state == "dance":
            sway = (-1, 0, 1, 0)[(phase // 6) % 4]
        if state == "giggle":
            sway = (-1, 1)[(phase // 4) % 2]

        # --- floor shadow, drawn first so it never covers the shoes ---------
        shadow = QColor(44, 32, 58, 46 if grounded else 22)
        if grounded:
            canvas.rect(11, 49, 18, 1, shadow)
            canvas.rect(8, 50, 24, 1, shadow)
        else:
            canvas.rect(13, 50, 14, 1, shadow)

        # Snap the offset to whole logical pixels so the 3×3 grid stays intact.
        sway = int(sway)
        bob = int(bob)
        painter.save()
        painter.translate(sway * canvas.scale, bob * canvas.scale)
        try:
            self._hair_back(canvas, colors, phase)
            self._legs(canvas, colors, state, phase)
            self._skirt(canvas, colors, state, phase)
            self._torso(canvas, colors, state)
            self._arms(canvas, colors, state, emotion, phase, talking, listening)
            self._head(canvas, colors, state, emotion, phase, sleeping, sitting)
            self._face(
                canvas, colors, state, emotion, phase, talking, listening, blinking
            )
            self._hair_front(canvas, colors, phase)
            self._accessory(
                canvas, colors, str((appearance or {}).get("accessory", "none"))
            )
        finally:
            painter.restore()
        self._effects(canvas, colors, state, emotion, phase, affection)

    # ------------------------------------------------------------- hairdo
    def _hair_back(
        self, canvas: _PixelCanvas, c: dict[str, QColor], phase: int
    ) -> None:
        """The bob's volume behind the head and the two side locks."""
        # back mass, one shade darker so the silhouette reads
        canvas.rect(9, 4, 22, 4, c["hair_dark"])
        canvas.rect(8, 7, 24, 10, c["hair_dark"])
        # the bob flares at the jaw line and stops at the collarbone
        canvas.rect(7, 13, 26, 8, c["hair_dark"])
        canvas.rect(8, 20, 24, 2, c["hair"])
        # side locks framing the face
        canvas.rect(7, 15, 3, 9, c["hair"])
        canvas.rect(30, 15, 3, 9, c["hair"])
        canvas.rect(7, 24, 3, 2, c["hair_dark"])
        canvas.rect(30, 24, 3, 2, c["hair_dark"])

    def _hair_front(
        self, canvas: _PixelCanvas, c: dict[str, QColor], phase: int
    ) -> None:
        """Fringe with the side-swept parting, plus a highlight strand."""
        # cap over the skull, leaving the face *below* y=8 uncovered
        canvas.rect(10, 2, 20, 2, c["hair"])
        canvas.rect(9, 4, 22, 4, c["hair"])
        # side-swept fringe: heavy on her right (image left), thin on the other
        canvas.rect(10, 8, 6, 3, c["hair"])
        canvas.rect(16, 8, 3, 2, c["hair"])
        canvas.rect(10, 11, 4, 2, c["hair"])
        canvas.rect(28, 8, 3, 4, c["hair"])
        # a lighter strand so the bob is not a flat mass
        canvas.rect(12, 5, 6, 1, c["hair_light"])
        canvas.rect(24, 5, 3, 2, c["hair_light"])
        canvas.rect(11, 9, 3, 1, c["hair_light"])
        # crown outline
        canvas.rect(10, 1, 20, 1, c["hair_dark"])
        canvas.rect(9, 2, 1, 3, c["hair_dark"])
        canvas.rect(30, 2, 1, 3, c["hair_dark"])

    # --------------------------------------------------------------- body
    def _legs(
        self, canvas: _PixelCanvas, c: dict[str, QColor], state: str, phase: int
    ) -> None:
        left, right = 12, 21
        lift_l = lift_r = 0
        if state in {"walk_left", "walk_right"}:
            step = (phase // 6) % 2
            if step:
                lift_l, lift_r = 0, 1
            else:
                lift_l, lift_r = 1, 0
        for x, lift in ((left, lift_l), (right, lift_r)):
            top = 36 - lift
            # thigh, knee, calf — twelve pixels of leg, in proportion
            canvas.rect(x, top, 5, 12, c["skin"])
            canvas.rect(x, top, 1, 12, c["skin_shade"])
            canvas.rect(x, top + 7, 5, 1, c["skin_deep"])
            # the loafer, with a dark sole and a rounded toe
            canvas.rect(x - 1, top + 12, 7, 2, c["shoe"])
            canvas.rect(x - 1, top + 14, 7, 1, c["shoe_dark"])
            canvas.rect(x - 1, top + 12, 2, 1, c["shoe_dark"])
        # the small gap between the legs stays transparent

    def _skirt(
        self, canvas: _PixelCanvas, c: dict[str, QColor], state: str, phase: int
    ) -> None:
        """Pleated skirt: flat bands read as pleats at this resolution."""
        sway = 1 if state == "dance" and (phase // 6) % 2 else 0
        canvas.rect(11 - sway, 30, 18 + sway * 2, 2, c["skirt_shade"])
        canvas.rect(10 - sway, 32, 20 + sway * 2, 4, c["skirt"])
        # pleats: alternating shade columns read as folds at this size
        for x in range(11 - sway, 29 + sway, 3):
            canvas.rect(x, 32, 1, 4, c["skirt_shade"])
        canvas.rect(10 - sway, 35, 20 + sway * 2, 1, c["skirt_deep"])

    def _torso(self, canvas: _PixelCanvas, c: dict[str, QColor], state: str) -> None:
        """Ribbed cream sweater with the rolled turtleneck collar."""
        # sweater body: narrow enough that the arms read as separate
        canvas.rect(11, 21, 18, 9, c["cloth"])
        # ribbing: vertical shade lines every third column
        for x in range(12, 29, 3):
            canvas.rect(x, 22, 1, 7, c["cloth_shade"])
        # the rolled turtleneck collar
        canvas.rect(15, 18, 10, 3, c["cloth"])
        canvas.rect(15, 18, 10, 1, c["cloth_shade"])
        canvas.rect(16, 20, 8, 1, c["cloth_shade"])
        # hem
        canvas.rect(11, 29, 18, 1, c["cloth_shade"])
        canvas.rect(11, 30, 18, 1, c["cloth_deep"])

    def _arms(
        self,
        canvas: _PixelCanvas,
        c: dict[str, QColor],
        state: str,
        emotion: str,
        phase: int,
        talking: bool,
        listening: bool,
    ) -> None:
        """Sleeves hang from the shoulders and end in bare hands.

        Every arm is drawn as one continuous run of pixels from the shoulder to
        the hand, so no pose can leave a hand floating beside the head.
        """
        swing = 0
        if state in {"walk_left", "walk_right"}:
            swing = 1 if (phase // 6) % 2 else -1

        if listening:
            # right hand cupped at her ear, left arm relaxed
            canvas.rect(10, 22, 3, 8, c["cloth"])
            canvas.rect(10, 30, 3, 2, c["skin"])
            canvas.rect(28, 22, 3, 6, c["cloth"])
            canvas.rect(28, 28, 3, 2, c["skin"])
            canvas.rect(30, 13, 3, 3, c["skin"])
            return

        if state == "dance":
            # left arm up and out, right arm down and out
            canvas.rect(9, 18, 3, 5, c["cloth"])
            canvas.rect(7, 14, 3, 4, c["cloth"])
            canvas.rect(6, 12, 3, 2, c["skin"])
            canvas.rect(28, 22, 3, 7, c["cloth"])
            canvas.rect(29, 29, 3, 2, c["skin"])
            return

        if emotion in {"love", "shy"} or state in {"giggle", "cheer", "jump"}:
            # both hands lifted, but still joined to the shoulders by sleeve
            canvas.rect(10, 22, 3, 4, c["cloth"])
            canvas.rect(9, 18, 3, 4, c["cloth"])
            canvas.rect(8, 15, 3, 3, c["skin"])
            canvas.rect(27, 22, 3, 4, c["cloth"])
            canvas.rect(28, 18, 3, 4, c["cloth"])
            canvas.rect(29, 15, 3, 3, c["skin"])
            return

        if emotion == "happy" and state in {"idle", "happy", "talk"}:
            # A cheerful wave with the right hand.  The sleeve steps outward so
            # the hand lands *beside* the hair locks (x>=33), never on top of
            # them, and stays visually attached to the shoulder.
            canvas.rect(10, 22, 3, 8, c["cloth"])
            canvas.rect(10, 30, 3, 2, c["skin"])
            canvas.rect(27, 22, 3, 5, c["cloth"])
            canvas.rect(29, 19, 3, 4, c["cloth"])
            canvas.rect(31, 16, 3, 4, c["cloth"])
            canvas.rect(32, 13, 4, 3, c["skin"])
            canvas.rect(32, 13, 1, 1, c["skin_shade"])
            return

        # default: both arms hang at her sides, swinging while walking
        canvas.rect(10, 22 + swing, 3, 8, c["cloth"])
        canvas.rect(10, 30 + swing, 3, 2, c["skin"])
        canvas.rect(27, 22 - swing, 3, 8, c["cloth"])
        canvas.rect(27, 30 - swing, 3, 2, c["skin"])

        if talking:
            # a small gesture with the right hand while speaking
            canvas.rect(27, 22, 3, 4, c["cloth"])
            canvas.rect(28, 18, 3, 4, c["cloth"])
            canvas.rect(29, 16, 3, 2, c["skin"])

    def _head(
        self,
        canvas: _PixelCanvas,
        c: dict[str, QColor],
        state: str,
        emotion: str,
        phase: int,
        sleeping: bool,
        sitting: bool,
    ) -> None:
        # neck
        canvas.rect(17, 16, 6, 2, c["skin_shade"])
        # face block: 16 wide, y=8..18 so the fringe sits above the eyes
        canvas.rect(12, 8, 16, 11, c["skin"])
        # rounded jaw
        canvas.rect(13, 19, 14, 1, c["skin"])
        canvas.rect(15, 20, 10, 1, c["skin_shade"])
        # ears just outside the face
        canvas.rect(11, 12, 1, 3, c["skin_shade"])
        canvas.rect(28, 12, 1, 3, c["skin_shade"])

    def _face(
        self,
        canvas: _PixelCanvas,
        c: dict[str, QColor],
        state: str,
        emotion: str,
        phase: int,
        talking: bool,
        listening: bool,
        blinking: bool,
    ) -> None:
        """Big green eyes, then the mouth and blush for the current mood."""
        eyes_closed = blinking or state == "sleep" or emotion == "sleepy"
        happy_eyes = state in {"giggle", "laugh"}
        surprised = emotion == "surprised" or state == "surprised"
        angry = emotion == "angry"
        sad = emotion in {"sad", "grief"}
        loving = emotion == "love"

        for eye_x in (13, 21):
            if eyes_closed:
                canvas.rect(eye_x, 13, 6, 1, c["lash"])
                continue
            if happy_eyes:
                # ^ ^ happy arcs
                canvas.rect(eye_x, 13, 1, 1, c["lash"])
                canvas.rect(eye_x + 1, 12, 4, 1, c["lash"])
                canvas.rect(eye_x + 5, 13, 1, 1, c["lash"])
                continue
            # sclera
            canvas.rect(eye_x, 11, 6, 5, c["eye_white"])
            # iris fills the eye: 5 of 6 columns, 5 rows
            canvas.rect(eye_x, 11, 6, 5, c["eye_green"])
            canvas.rect(eye_x, 14, 6, 2, c["eye_green_dark"])
            # a small pupil, so the green still reads at this size
            canvas.rect(eye_x + 2, 12, 2, 2, c["eye_pupil"])
            # highlight, upper-left as in the reference art
            canvas.rect(eye_x + 1, 11, 2, 1, c["eye_white"])
            # heavy upper lash
            canvas.rect(eye_x, 10, 6, 1, c["lash"])
            canvas.rect(eye_x, 11, 1, 1, c["lash"])
            canvas.rect(eye_x + 5, 11, 1, 1, c["lash"])
            # lower lid
            canvas.rect(eye_x, 16, 6, 1, c["skin_shade"])
            if loving:
                # half-lidded: a lid line across the top third
                canvas.rect(eye_x, 11, 6, 2, c["skin"])

        # eyebrows, angled per mood, one pixel above the lashes
        brow_y = 8
        if angry:
            canvas.rect(13, brow_y + 1, 5, 1, c["hair_dark"])
            canvas.rect(21, brow_y, 5, 1, c["hair_dark"])
        elif sad:
            canvas.rect(13, brow_y, 5, 1, c["hair_dark"])
            canvas.rect(21, brow_y + 1, 5, 1, c["hair_dark"])
        elif surprised:
            canvas.rect(13, brow_y - 1, 5, 1, c["hair_dark"])
            canvas.rect(21, brow_y - 1, 5, 1, c["hair_dark"])
        else:
            canvas.rect(13, brow_y, 5, 1, c["hair_dark"])
            canvas.rect(21, brow_y, 5, 1, c["hair_dark"])

        # mouth, two pixels under the eye band
        mouth_y = 18
        if state == "sleep":
            canvas.rect(18, mouth_y, 3, 1, c["mouth"])
        elif talking or state == "talk":
            open_px = 2 if (phase // 4) % 2 else 1
            canvas.rect(17, mouth_y, 5, open_px, c["mouth"])
        elif surprised:
            canvas.rect(18, mouth_y, 3, 2, c["mouth"])
        elif emotion in {"happy", "love"} or state in {"giggle", "laugh", "dance"}:
            canvas.rect(16, mouth_y, 1, 1, c["mouth"])
            canvas.rect(17, mouth_y + 1, 5, 1, c["mouth"])
            canvas.rect(22, mouth_y, 1, 1, c["mouth"])
        elif angry:
            canvas.rect(17, mouth_y + 1, 5, 1, c["mouth"])
        elif sad:
            canvas.rect(17, mouth_y + 1, 1, 1, c["mouth"])
            canvas.rect(18, mouth_y, 3, 1, c["mouth"])
            canvas.rect(21, mouth_y + 1, 1, 1, c["mouth"])
        else:
            canvas.rect(18, mouth_y, 4, 1, c["mouth"])

        # blush low on the cheeks, clear of the eyes
        if emotion in {"love", "shy", "happy"} or state in {"giggle", "love"}:
            canvas.rect(12, 16, 3, 1, c["blush"])
            canvas.rect(25, 16, 3, 1, c["blush"])

    # ---------------------------------------------------------- accessories
    def _accessory(
        self, canvas: _PixelCanvas, c: dict[str, QColor], accessory: str
    ) -> None:
        accessory = accessory.lower()
        if accessory == "ribbon":
            canvas.rect(24, 5, 3, 2, QColor("#ff6f91"))
            canvas.rect(27, 4, 2, 2, QColor("#ff92ad"))
            canvas.rect(27, 6, 2, 2, QColor("#ff92ad"))
        elif accessory == "glasses":
            frame = QColor("#3a3550")
            canvas.frame(12, 9, 7, 6, frame)
            canvas.frame(21, 9, 7, 6, frame)
            canvas.rect(19, 11, 2, 1, frame)
        elif accessory == "headphones":
            canvas.rect(10, 6, 20, 2, QColor("#4b4a63"))
            canvas.rect(8, 9, 3, 6, QColor("#4b4a63"))
            canvas.rect(29, 9, 3, 6, QColor("#4b4a63"))
            canvas.rect(9, 11, 1, 2, QColor("#8f8fb0"))
            canvas.rect(30, 11, 1, 2, QColor("#8f8fb0"))

    # -------------------------------------------------------------- effects
    def _effects(
        self,
        canvas: _PixelCanvas,
        c: dict[str, QColor],
        state: str,
        emotion: str,
        phase: int,
        affection: bool,
    ) -> None:
        """Floating pixel icons: hearts, notes, Zzz, questions, sparks."""
        bob = (phase // 8) % 2
        if state == "sleep":
            canvas.stamp(_Z, 31, 8 - bob, c["hair_light"])
            canvas.stamp(_Z, 34, 3, c["hair_light"])
        elif state == "dance":
            canvas.stamp(_NOTE, 33, 10 - bob, QColor("#ff8fb3"))
        elif emotion == "love" or affection:
            canvas.stamp(_HEART, 30, 9 - bob, QColor("#ff6f91"))
            canvas.stamp(_SPARKLE, 33, 16, QColor("#ffd166"))
        elif emotion == "angry":
            canvas.stamp(_ANGER, 32, 8, QColor("#e8536b"))
        elif emotion == "surprised":
            canvas.stamp(_QUESTION, 32, 8 - bob, QColor("#7fc7ff"))
        elif state in {"giggle", "laugh"}:
            canvas.stamp(_SPARKLE, 32, 8 - bob, QColor("#ffd166"))
            canvas.stamp(_SPARKLE, 6, 11, QColor("#ffd166"))
        elif state == "cheer" or state == "jump":
            canvas.stamp(_SPARKLE, 33, 7 - bob, QColor("#ffd166"))
            canvas.stamp(_SPARKLE, 4, 9, QColor("#ff8fb3"))

    def draw_scaled(
        self,
        painter: QPainter,
        *,
        scale: int = 1,
        x: int = 0,
        y: int = 0,
        **kwargs: Any,
    ) -> None:
        """Draw the whole figure with an explicit integer pixel scale.

        Small badges (mood chips, the panel portrait) cannot use ``PIXEL_SIZE``
        or the character would overflow the card, so the caller picks the scale.
        """
        painter.save()
        painter.translate(int(x), int(y))
        original = globals()["PIXEL_SIZE"]
        try:
            globals()["PIXEL_SIZE"] = int(scale)
            self.draw(painter, **kwargs)
        finally:
            globals()["PIXEL_SIZE"] = original
        painter.restore()

    # ---------------------------------------------------------------- icons
    #: The tray icon art lives inside this logical box (x0, y0, w, h).
    ICON_BOX = (4, 2, 14, 13)

    @classmethod
    def draw_icon(
        cls,
        painter: QPainter,
        size: int,
        appearance: Mapping[str, Any] | None = None,
    ) -> None:
        """The tray icon: her head, on exact integer blocks, never clipped."""
        colors = _palette(appearance)
        icon = int(size)
        x0, y0, width, height = cls.ICON_BOX
        largest = max(width, height)
        # Pick the biggest integer scale that still leaves a one-block margin
        # and divides the canvas, so no block is ever partially drawn.
        scale = 1
        for candidate in range(1, max(2, icon // largest) + 1):
            if candidate * largest + 2 <= icon and icon % candidate == 0:
                scale = candidate
        # The offset must be a whole number of logical pixels, otherwise the
        # art lands half a block off the canvas grid and the icon blurs.
        offset_x = ((icon - width * scale) // 2 // scale - x0) * scale
        offset_y = ((icon - height * scale) // 2 // scale - y0) * scale
        canvas = _PixelCanvas(painter, scale, offset_x=offset_x, offset_y=offset_y)

        canvas.rect(6, 2, 10, 1, colors["hair"])
        canvas.rect(5, 3, 12, 2, colors["hair"])
        canvas.rect(4, 5, 14, 5, colors["hair"])
        canvas.rect(6, 6, 10, 7, colors["skin"])
        canvas.rect(7, 9, 3, 3, colors["eye_green"])
        canvas.rect(12, 9, 3, 3, colors["eye_green"])
        canvas.rect(8, 10, 1, 1, colors["eye_pupil"])
        canvas.rect(13, 10, 1, 1, colors["eye_pupil"])
        canvas.rect(7, 9, 1, 1, colors["eye_white"])
        canvas.rect(12, 9, 1, 1, colors["eye_white"])
        canvas.rect(9, 13, 4, 1, colors["mouth"])
        canvas.rect(6, 3, 4, 1, colors["hair_light"])
        canvas.rect(4, 10, 2, 4, colors["hair"])
        canvas.rect(14, 10, 2, 4, colors["hair"])


__all__ = [
    "DEFAULT_HAIR_COLOR",
    "GRID_HEIGHT",
    "GRID_WIDTH",
    "PIXEL_SIZE",
    "PixelCharacter",
]

"""Sprite based character renderer.

The character art is *illustrated* rather than drawn with QPainter: a set of
PNG files in ``docs/character/ai`` holds one full-body pose per mood and per
movement phase.  This module turns those files into a small state machine that
behaves like an animation engine:

* **moods**       — happy, sad, angry, thinking… (chosen by the AI per reply)
* **locomotion**  — walk / run cycles built from 2–3 phases plus mirroring
* **airborne**    — picked up, dangling, dropped, falling, landing

Design rules:

* Missing files never crash the app — ``available()`` reports what exists and
  the caller falls back to the procedural renderer.
* White backgrounds are keyed out to transparent at load time, so a flat white
  poster prints cleanly on the desktop.
* Crossfades use ``QPainter`` opacity, so a mood change never pops.

No network access, no bundled binary blobs, no hidden downloads.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QColor, QImage, QPainter, QPixmap, QTransform

# Where the illustrated sprites live.  Relative to the repository root so the
# module also works when the app is installed as a plain folder.
ASSET_DIR = Path(__file__).resolve().parent.parent / "docs" / "character" / "ai"

#: Mood -> sprite file stem.  The AI's ``emotion`` lands on one of these.
MOOD_SPRITES: dict[str, str] = {
    "happy": "happy",
    "love": "love",
    "thinking": "thinking",
    "surprised": "surprised",
    "angry": "angry",
    "sad": "sad",
    "sleepy": "sleepy",
    "shy": "shy",
    "laugh": "laugh",
    "dance": "dance",
    "shrug": "shrug",
    "idle": "base_idle",
    "neutral": "base_idle",
}

#: Gesture (from the AI's ``[MOVE]`` tag) -> sprite stem.  The illustrated set
#: cannot interpolate limbs, so a gesture becomes a short *hold* on the sheet
#: that reads as that gesture.  Gestures without a dedicated drawing fall back
#: to the closest readable mood, never to nothing.
GESTURE_SPRITES: dict[str, str] = {
    "wave": "happy",
    "jump": "cheer",
    "dance": "dance",
    "talk": "base_idle",
    "listen": "thinking",
    "think": "thinking",
    "laugh": "laugh",
    "smile_only": "happy",
    "surprised": "surprised",
    "shy": "shy",
    "angry": "angry",
    "sad": "sad",
    "sleep": "sleepy",
    "sit": "base_idle",
    "walk_left": "base_idle",
    "walk_right": "base_idle",
    "shrug": "shrug",
    "stretch": "cheer",
    "nod": "happy",
    "shake_head": "surprised",
    "cheer": "cheer",
    "point": "happy",
    "clap": "cheer",
    "bow": "shy",
    "tilt_head": "thinking",
    "idle": "base_idle",
    "breathe": "base_idle",
}

#: Walk cycle: the frames are played in order, then the sequence is mirrored to
#: get the second half of the stride.  Three phases is the classic minimum for a
#: readable walk (contact → passing → contact).
WALK_FRAMES = ("side_walk_1", "side_walk_3_pass", "side_walk_1")
RUN_FRAMES = ("side_run", "side_jump")

#: Airborne set, in the order the interaction happens.
AIR_FRAMES = {
    "picked_up": "picked_up_1",
    "held": "picked_up_2",
    "dangle": "dangle_kick",
    "falling": "fall_1",
    "bracing": "fall_2",
    "landing": "land_squat",
    "recovering": "land_recover",
}


def _key_out_white(image: QImage, tolerance: int = 12) -> QImage:
    """Turn the flat white poster background into transparency.

    The illustrations are delivered on pure white.  A flood fill from the
    borders is used instead of a global colour test so that white highlights
    *inside* the character (the sweater, the skirt) are preserved.
    """
    image = image.convertToFormat(QImage.Format_ARGB32)
    width, height = image.width(), image.height()
    if width == 0 or height == 0:
        return image

    def is_white(x: int, y: int) -> bool:
        colour = image.pixelColor(x, y)
        return (
            colour.alpha() > 0
            and colour.red() >= 255 - tolerance
            and colour.green() >= 255 - tolerance
            and colour.blue() >= 255 - tolerance
        )

    seen = bytearray(width * height)
    stack: list[tuple[int, int]] = []
    for x in range(width):
        stack.append((x, 0))
        stack.append((x, height - 1))
    for y in range(height):
        stack.append((0, y))
        stack.append((width - 1, y))

    transparent = QColor(0, 0, 0, 0)
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        index = y * width + x
        if seen[index]:
            continue
        seen[index] = 1
        if not is_white(x, y):
            continue
        image.setPixelColor(x, y, transparent)
        stack.append((x + 1, y))
        stack.append((x - 1, y))
        stack.append((x, y + 1))
        stack.append((x, y - 1))
    return image


@dataclass
class _Frame:
    """One loaded sprite plus the trimmed bounds of the artwork."""

    pixmap: QPixmap
    bounds: QRectF


class SpriteLibrary:
    """Loads, trims and caches the illustrated character sprites."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else ASSET_DIR
        self._cache: dict[str, _Frame | None] = {}

    # ------------------------------------------------------------------ loading
    def path_for(self, name: str) -> Path:
        return self.root / f"{name}.png"

    def frame(self, name: str) -> _Frame | None:
        """Return a trimmed frame, or ``None`` when the file is missing."""
        if name in self._cache:
            return self._cache[name]
        path = self.path_for(name)
        if not path.is_file():
            self._cache[name] = None
            return None
        image = QImage(str(path))
        if image.isNull():
            self._cache[name] = None
            return None
        image = _key_out_white(image)
        pixmap = QPixmap.fromImage(image)
        bounds = self._opaque_bounds(image)
        self._cache[name] = _Frame(pixmap, bounds)
        return self._cache[name]

    @staticmethod
    def _opaque_bounds(image: QImage) -> QRectF:
        """Bounding box of the non-transparent pixels, in source coordinates."""
        left, top = image.width(), image.height()
        right = bottom = -1
        # Sample every second pixel: four times faster, plenty accurate.
        for y in range(0, image.height(), 2):
            for x in range(0, image.width(), 2):
                if image.pixelColor(x, y).alpha() > 8:
                    if x < left:
                        left = x
                    if x > right:
                        right = x
                    if y < top:
                        top = y
                    if y > bottom:
                        bottom = y
        if right < left or bottom < top:
            return QRectF(0, 0, image.width(), image.height())
        return QRectF(left, top, right - left + 1, bottom - top + 1)

    # ------------------------------------------------------------------ queries
    def available(self) -> set[str]:
        """Names of the sprites that are actually present on disk."""
        names = set(MOOD_SPRITES.values())
        names.update(WALK_FRAMES)
        names.update(RUN_FRAMES)
        names.update(AIR_FRAMES.values())
        return {name for name in names if self.path_for(name).is_file()}

    def has_all(self, names: Iterable[str]) -> bool:
        present = self.available()
        return all(name in present for name in names)

    def mood_for(self, emotion: str) -> str | None:
        """Resolve an emotion to a sprite name that exists (or ``None``)."""
        key = (emotion or "").strip().lower()
        for candidate in (MOOD_SPRITES.get(key), "base_idle"):
            if candidate and self.path_for(candidate).is_file():
                return candidate
        return None


class SpriteCharacter:
    """Paints the illustrated character into an arbitrary target rectangle.

    The renderer is deliberately stateless about time: the caller advances it
    with ``tick(dt)`` and then asks it to paint.  That keeps the pet's 30 fps
    timer, the chat panel's preview and the tests all driving the same code.
    """

    #: How long one walk/run phase is displayed.
    WALK_PHASE = 0.22
    RUN_PHASE = 0.14
    #: Crossfade duration between two different moods.
    BLEND = 0.18

    def __init__(self, library: SpriteLibrary | None = None) -> None:
        self.library = library or SpriteLibrary()
        self._current: str | None = None
        self._previous: str | None = None
        self._blend = 1.0  # 1.0 = fully on the current sprite
        self._elapsed = 0.0
        self._mirrored = False
        self._locomotion: str | None = None
        self._airborne: str | None = None
        self._bob = 0.0
        self._expression: str | None = None
        self._expression_left = 0.0
        # First paint must never be blank: adopt the idle sheet immediately.
        initial = self.library.mood_for("idle")
        if initial is not None:
            self._current = initial

    # ------------------------------------------------------------------ state
    @property
    def sprite(self) -> str | None:
        return self._current

    def set_mood(self, emotion: str) -> bool:
        """Switch to the sprite for ``emotion``. Returns ``True`` if it changed.

        An unrecognised emotion is *ignored*: falling back to the idle sheet here
        would silently override a valid pose just because a model typo'd, and the
        caller already has its own "no emotion" path.
        """
        key = (emotion or "").strip().lower()
        name = MOOD_SPRITES.get(key)
        if name is None or not self.library.path_for(name).is_file():
            return False
        if name == self._current:
            return False
        self._transition(name)
        return True

    def express(self, gesture: str, duration: float = 1.6) -> bool:
        """Hold the sheet that reads as ``gesture`` for ``duration`` seconds.

        This is how an AI-chosen ``[MOVE]`` gesture is shown with a sprite set:
        the illustrated character cannot interpolate limbs, so the move becomes
        a timed pose instead of a canned loop.
        """
        key = (gesture or "").strip().lower()
        name = GESTURE_SPRITES.get(key)
        if name is None or not self.library.path_for(name).is_file():
            return False
        self._expression = name
        self._expression_left = max(0.2, float(duration))
        self._transition(name)
        return True

    def set_locomotion(self, mode: str | None, *, mirrored: bool = False) -> None:
        """``"walk"``, ``"run"`` or ``None``; the cycle is time driven."""
        mode = mode if mode in {"walk", "run"} else None
        if mode != self._locomotion:
            self._locomotion = mode
            self._elapsed = 0.0
        self._mirrored = bool(mirrored)

    def set_airborne(self, stage: str | None) -> None:
        """``picked_up``/``held``/``dangle``/``falling``/``bracing``/``landing``/
        ``recovering`` — or ``None`` to return to the mood sprite."""
        stage = stage if stage in AIR_FRAMES else None
        if stage == self._airborne:
            return
        self._airborne = stage
        if stage is not None:
            name = AIR_FRAMES[stage]
            if self.library.path_for(name).is_file():
                self._transition(name)

    def _transition(self, name: str) -> None:
        if name == self._current:
            return
        if self._current is not None:
            self._previous = self._current
            self._blend = 0.0
        else:
            self._previous = None
            self._blend = 1.0
        self._current = name

    # ------------------------------------------------------------------- clock
    def tick(self, dt: float) -> None:
        dt = max(0.0, min(float(dt), 0.35))  # clamp after a hidden window
        self._elapsed += dt
        if self._blend < 1.0:
            self._blend = min(1.0, self._blend + dt / self.BLEND)
        if self._expression_left > 0.0:
            self._expression_left -= dt
            if self._expression_left <= 0.0:
                self._expression = None
        # A gentle vertical bob makes even a static sprite feel alive.
        self._bob = math.sin(self._elapsed * (7.0 if self._locomotion else 2.2)) * 2.0

    def _cycle_frame(self) -> str | None:
        if self._locomotion is None:
            return None
        frames = RUN_FRAMES if self._locomotion == "run" else WALK_FRAMES
        phase = self.RUN_PHASE if self._locomotion == "run" else self.WALK_PHASE
        index = int(self._elapsed / max(phase, 1e-3)) % len(frames)
        return frames[index]

    def active_sprite(self) -> str | None:
        if self._airborne is not None:
            return AIR_FRAMES[self._airborne]
        cycle = self._cycle_frame()
        if cycle is not None:
            return cycle
        if self._expression is not None and self._expression_left > 0.0:
            return self._expression
        return self._current

    # ------------------------------------------------------------------ drawing
    def paint(self, painter: QPainter, target: QRectF) -> bool:
        """Draw the sprite fitted into ``target``. ``False`` = nothing to draw."""
        name = self.active_sprite()
        if name is None:
            return False
        frame = self.library.frame(name)
        if frame is None:
            return False

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # Crossfade: draw the outgoing sprite underneath while fading in.
        if self._previous is not None and self._blend < 1.0:
            old = self.library.frame(self._previous)
            if old is not None:
                painter.setOpacity(1.0 - self._blend)
                self._draw_frame(painter, old, target, mirrored=self._mirrored)
        painter.setOpacity(1.0)
        self._draw_frame(painter, frame, target, mirrored=self._mirrored)
        painter.restore()
        return True

    @staticmethod
    def _draw_frame(
        painter: QPainter, frame: _Frame, target: QRectF, *, mirrored: bool
    ) -> None:
        bounds = frame.bounds
        if bounds.width() <= 0 or bounds.height() <= 0:
            return
        scale = min(target.width() / bounds.width(), target.height() / bounds.height())
        width = bounds.width() * scale
        height = bounds.height() * scale
        x = target.center().x() - width / 2.0
        # Anchor at the bottom: the shoes must stay on the floor line.
        y = target.bottom() - height

        source = QRectF(bounds)
        if mirrored:
            transform = QTransform()
            transform.translate(x + width, y)
            transform.scale(-1.0, 1.0)
            painter.setTransform(transform, True)
            painter.drawPixmap(QRectF(0, 0, width, height), frame.pixmap, source)
            painter.resetTransform()
        else:
            painter.drawPixmap(QRectF(x, y, width, height), frame.pixmap, source)

    # ---------------------------------------------------------------- portraits
    def portrait(
        self, size: int, emotion: str = "idle", *, crop: str = "face"
    ) -> QImage:
        """Square portrait for the tray icon and the chat header avatar."""
        name = self.library.mood_for(emotion) or self.library.mood_for("idle")
        if name is None:
            blank = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
            blank.fill(QColor(0, 0, 0, 0))
            return blank
        frame = self.library.frame(name)
        if frame is None:
            blank = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
            blank.fill(QColor(0, 0, 0, 0))
            return blank

        bounds = frame.bounds
        if crop == "face":
            # The head occupies roughly the top third of a full-body sheet.
            side = min(bounds.width(), bounds.height() * 0.30)
            source = QRectF(
                bounds.center().x() - side / 2.0,
                bounds.top(),
                side,
                side,
            )
        else:
            source = QRectF(bounds)

        canvas = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
        canvas.fill(QColor(0, 0, 0, 0))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(QRectF(0, 0, size, size), frame.pixmap, source)
        painter.end()
        return canvas


def iter_missing(root: Path | None = None) -> Iterator[str]:
    """Names of the sprites the app would like to have but cannot find."""
    library = SpriteLibrary(root)
    wanted = set(MOOD_SPRITES.values()) | set(WALK_FRAMES) | set(RUN_FRAMES)
    wanted |= set(AIR_FRAMES.values())
    present = library.available()
    for name in sorted(wanted - present):
        yield name


@dataclass
class SpriteAssets:
    """Small helper so callers can ask "can I use sprites?" in one call."""

    library: SpriteLibrary = field(default_factory=SpriteLibrary)

    @property
    def usable(self) -> bool:
        """Sprites are usable when at least the idle sheet is present."""
        return self.library.path_for("base_idle").is_file()

    def missing(self) -> list[str]:
        return list(iter_missing(self.library.root))


__all__ = [
    "AIR_FRAMES",
    "GESTURE_SPRITES",
    "ASSET_DIR",
    "MOOD_SPRITES",
    "RUN_FRAMES",
    "SpriteAssets",
    "SpriteCharacter",
    "SpriteLibrary",
    "WALK_FRAMES",
    "iter_missing",
]

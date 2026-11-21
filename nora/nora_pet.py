"""A transparent semi-realistic VTuber-style desktop companion.

The character has a small physics/behaviour loop, weighted idle choices,
multi-monitor awareness, sticky screen edges and a separate speech bubble so
the bubble does not shrink the character.

Two renderers ship with the app: the default smoothed portrait
(:mod:`nora.nora_avatar`, 260×360) and the legacy 8-bit chibi
(:mod:`nora.nora_pixel_art`) that can be selected with ``NORA_CHARACTER=pixel``.
No sprite or image files are used by either one.
"""

from __future__ import annotations

import os
import random
from collections import deque
from enum import Enum, auto
from typing import Any, Mapping

from PyQt5.QtCore import QPoint, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication, QWidget

from .nora_avatar import (
    AVATAR_HEIGHT,
    AVATAR_WIDTH,
    DEFAULT_HAIR,
    RealisticCharacter,
)
from .nora_body import FullBodyCharacter
from .nora_motion import MotionController, fallback_move, normalize_move
from .nora_physics import AirStages
from .nora_pixel_art import DEFAULT_HAIR_COLOR, PixelCharacter
from .nora_sprite import SpriteAssets, SpriteCharacter


class PetState(Enum):
    IDLE = auto()
    WALK_LEFT = auto()
    WALK_RIGHT = auto()
    SIT = auto()
    SLEEP = auto()
    JUMP = auto()
    FALL = auto()
    WAVE = auto()
    TALK = auto()
    LISTENING = auto()
    SURPRISED = auto()
    LOVE = auto()
    ANGRY = auto()
    DRAG = auto()
    DANCE = auto()
    YAWN = auto()
    WATCH = auto()
    LAND = auto()


def _character_style(settings: Mapping[str, Any] | None = None) -> str:
    """Preference > environment > default; unknown values fall back safely."""
    settings = settings or {}
    candidates = (
        settings.get("character_style"),
        os.getenv("NORA_CHARACTER"),
    )
    for value in candidates:
        text = str(value or "").strip().lower()
        if text in {"sprite", "body", "realistic", "pixel"}:
            return text
    return "sprite"


def _tooltip_for(style: str) -> str:
    if style == "sprite":
        return "Nora 💕 · çizim · Sol tık: sohbet · Sağ tık: menü · Sürükle: kaldır & bırak"
    if style == "pixel":
        return "Nora 💕 · 8-bit mod · Sol tık: sohbet · Sağ tık: menü · Sürükle: taşı"
    if style == "realistic":
        return "Nora 💕 · portre · Sol tık: sohbet · Sağ tık: menü · Sürükle: taşı"
    return "Nora 💕 · tam vücut · Sol tık: sohbet · Sağ tık: menü · Sürükle: taşı"


class SpeechBubble(QWidget):
    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self._text = ""
        self._speaker = "nora"
        self.setFixedSize(240, 76)

    def set_text(self, text: str, speaker: str = "nora") -> None:
        self._speaker = "user" if speaker == "user" else "nora"
        text = str(text).replace("\n", " ").strip()
        if self._speaker == "user":
            text = "Sen: " + text
        self._text = text[:60] + "..." if len(text) > 60 else text
        metrics = self.fontMetrics()
        rect = metrics.boundingRect(
            QRectF(0, 0, 214, 200).toRect(),
            Qt.TextWordWrap | Qt.AlignCenter,
            self._text,
        )
        self.setFixedHeight(max(54, min(96, rect.height() + 26)))
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        body = QRectF(1, 1, self.width() - 2, self.height() - 11)
        path = QPainterPath()
        path.addRoundedRect(body, 12, 12)
        tail = QPainterPath()
        cx = self.width() / 2
        tail.moveTo(cx - 8, body.bottom() - 1)
        tail.lineTo(cx, body.bottom() + 9)
        tail.lineTo(cx + 8, body.bottom() - 1)
        tail.closeSubpath()
        path.addPath(tail)
        if self._speaker == "user":
            painter.setPen(QPen(QColor("#7c4dff"), 1.6))
            painter.setBrush(QColor("#f3ecff"))
        else:
            painter.setPen(QPen(QColor("#ff6b9d"), 1.5))
            painter.setBrush(QColor("#fffafc"))
        painter.drawPath(path.simplified())
        painter.setPen(QColor("#3a204c"))
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        painter.drawText(
            QRectF(12, 7, self.width() - 24, self.height() - 22),
            Qt.TextWordWrap | Qt.AlignCenter,
            self._text,
        )


class NoraPet(QWidget):
    clicked = pyqtSignal()
    right_clicked = pyqtSignal(QPoint)
    double_clicked = pyqtSignal()
    position_changed = pyqtSignal(QPoint)

    PIXEL_WIDTH = 120
    PIXEL_HEIGHT = 150
    #: Full-body character (default): small on screen, but with real legs and
    #: arms that the motion engine can move.
    BODY_WIDTH = 132
    BODY_HEIGHT = 312
    # The illustrated sheets are portrait shaped; the window is sized to give
    # the figure roughly the same on-screen height as the drawn body.
    SPRITE_WIDTH = 168
    SPRITE_HEIGHT = 330
    WIDTH = BODY_WIDTH
    HEIGHT = BODY_HEIGHT
    GRAVITY = 0.4
    WALK_SPEED = 1.2
    FPS_INTERVAL = 33

    def __init__(
        self, parent: QWidget | None = None, *, rng: random.Random | None = None
    ) -> None:
        super().__init__(parent)
        self.rng = rng or random.Random()
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.character_style = _character_style()
        # The sprite library must exist before the style is applied: the style
        # switch checks whether the illustrated sheets are actually present.
        self._sprite_assets = SpriteAssets()
        self._sprite_artist = SpriteCharacter(self._sprite_assets.library)
        self._air = AirStages()
        self._apply_character_style(self.character_style, update=False)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setWindowTitle("Nora")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Nora 💕 · Sol tık: sohbet · Sağ tık: menü · Sürükle: taşı")

        self.state = PetState.IDLE
        self.emotion = "happy"
        self._frame = 0
        self._state_frames = 0
        self._state_duration = 100
        self._vx = 0.0
        self._vy = 0.0
        self._grounded = True
        self._on_taskbar = False
        self._talking = False
        self._listening = False
        self._state_before_talk = PetState.IDLE
        self._state_before_listening = PetState.IDLE
        self._pinned_state: PetState | None = None
        self._manual = False
        self._autonomous = True
        self._animations = True
        self._affection_frames = 0
        self._appearance = {
            # the reference art wears a cream turtleneck
            "outfit": "cream",
            "hair_color": (
                DEFAULT_HAIR_COLOR if self.character_style == "pixel" else DEFAULT_HAIR
            ),
            "accessory": "none",
            "eye_color": "yesil",
        }
        self._pixel_artist = PixelCharacter()
        self._realistic_artist = RealisticCharacter()
        self._body_artist = FullBodyCharacter()
        self._motion = MotionController(self.rng)
        self._pose_clock = 0.0
        self._last_pose = None
        self._blink_left = 0
        self._next_blink = self.rng.randint(100, 200)
        self._drag_offset = QPoint()
        self._press_pos = QPoint()
        self._dragging = False
        self._drag_complained = False
        self._bubble: SpeechBubble | None = None
        self._speech_queue: deque[tuple[str, int, str]] = deque(maxlen=5)
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._hide_bubble)
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(240)
        self._click_timer.timeout.connect(self.clicked.emit)

        screen = QApplication.primaryScreen()
        geometry = (
            screen.availableGeometry() if screen else QRectF(0, 0, 1280, 720).toRect()
        )
        self._x = float(geometry.right() - self.WIDTH - 20)
        self._y = float(geometry.bottom() - self.HEIGHT + 1)
        self._floor_y = self._y
        self.move(int(self._x), int(self._y))
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(self.FPS_INTERVAL)

    # ------------------------------------------------------------------ helpers
    def _screen_rects(self):
        app = QApplication.instance()
        screen = (
            app.screenAt(
                QPoint(int(self._x + self.WIDTH / 2), int(self._y + self.HEIGHT / 2))
            )
            if app
            else None
        )
        if screen is None:
            screen = self.screen() or (app.primaryScreen() if app else None)
        if screen is None:
            return QRectF(0, 0, 1280, 720).toRect(), QRectF(0, 0, 1280, 720).toRect()
        return screen.availableGeometry(), screen.geometry()

    def _current_floor(self) -> float:
        available, full = self._screen_rects()
        bottom = (
            full.bottom()
            if self._on_taskbar and full.bottom() > available.bottom()
            else available.bottom()
        )
        return float(bottom - self.HEIGHT + 1)

    def _set_state(self, state: PetState, duration: int | None = None) -> None:
        self.state = state
        self._state_frames = 0
        if state != PetState.DRAG:
            self._drag_complained = False
        self._state_duration = duration or self.rng.randint(70, 170)
        self._vx = {
            PetState.WALK_LEFT: -self.WALK_SPEED,
            PetState.WALK_RIGHT: self.WALK_SPEED,
        }.get(state, 0.0)
        if state != PetState.SIT:
            self._on_taskbar = False
        if state == PetState.JUMP and self._grounded:
            self._vy = -8.0
            self._grounded = False
        if state == PetState.SLEEP and not self._grounded:
            self.state = PetState.IDLE
        self.update()

    def _choose_state(self) -> None:
        if self.state == PetState.LAND:
            if self._listening:
                self._set_state(PetState.LISTENING, 100000)
            elif self._pinned_state is not None:
                self._set_state(self._pinned_state, 100000)
            else:
                self._set_state(PetState.IDLE, 80)
            return
        if (
            self._talking
            or self._listening
            or self.state == PetState.DRAG
            or self._manual
        ):
            return
        if not self._autonomous:
            if self.state != PetState.IDLE:
                self._set_state(PetState.IDLE, 100000)
            return
        from .nora_personality import is_quiet_hours

        choices = [
            (PetState.IDLE, 25),
            (PetState.WALK_LEFT, 20),
            (PetState.WALK_RIGHT, 20),
            (PetState.SIT, 10),
            (PetState.JUMP, 8),
            (PetState.WAVE, 5),
            (PetState.SLEEP, 5),
        ]
        if is_quiet_hours():
            choices = [
                (
                    s,
                    35
                    if s == PetState.SLEEP
                    else max(1, w // 2 if s != PetState.IDLE else w),
                )
                for s, w in choices
            ]
        if not self._grounded:
            choices = [(s, w) for s, w in choices if s != PetState.SLEEP]
        total = sum(w for _, w in choices)
        pick = self.rng.uniform(0, total)
        for state, weight in choices:
            pick -= weight
            if pick <= 0:
                if state == PetState.SIT:
                    available, full = self._screen_rects()
                    self._on_taskbar = (
                        full.bottom() > available.bottom() and self.rng.random() < 0.15
                    )
                    self._floor_y = self._current_floor()
                    self._set_state(state, self.rng.randint(120, 260))
                elif state == PetState.SLEEP:
                    self._set_state(state, self.rng.randint(180, 360))
                else:
                    self._set_state(state, self.rng.randint(80, 200))
                return

    def _tick(self) -> None:
        if self._animations:
            self._frame += 1
        self._affection_frames = max(0, self._affection_frames - 1)
        self._state_frames += 1
        if (
            self.state == PetState.DRAG
            and self._state_frames > 110
            and not self._drag_complained
        ):
            self._drag_complained = True
            self.emotion = "angry"
            self.show_speech("Beni biraz bırak senpai! 😾", 3000)
        if self._blink_left > 0:
            self._blink_left -= 1
        else:
            self._next_blink -= 1
            if self._next_blink <= 0:
                self._blink_left = 6
                self._next_blink = self.rng.randint(100, 200)
        self._tick_body()
        if self.character_style == "sprite":
            self._tick_sprite()
        self._floor_y = self._current_floor()

        if self.state != PetState.DRAG:
            available, _ = self._screen_rects()
            if self.state in (PetState.WALK_LEFT, PetState.WALK_RIGHT):
                self._x += self._vx
                # Sticky edges: pause at the edge, then turn back into screen.
                if self._x <= available.left() + 2:
                    self._x = float(available.left() + 2)
                    self._set_state(PetState.WALK_RIGHT)
                elif self._x + self.WIDTH >= available.right() - 1:
                    self._x = float(available.right() - self.WIDTH + 1)
                    self._set_state(PetState.WALK_LEFT)
            if not self._grounded or self.state in (PetState.JUMP, PetState.FALL):
                self._vy += self.GRAVITY
                self._y += self._vy
                if self._y >= self._floor_y:
                    self._y = self._floor_y
                    self._vy = 0.0
                    self._grounded = True
                    if self.state in (PetState.JUMP, PetState.FALL):
                        if self.state == PetState.FALL:
                            if self.character_style == "sprite":
                                self._air.landed(speed=abs(self._vy))
                            self._set_state(PetState.LAND, 18)
                        elif self._listening:
                            self._set_state(PetState.LISTENING, 100000)
                        elif self._pinned_state is not None:
                            self._set_state(self._pinned_state, 100000)
                        else:
                            self._set_state(PetState.IDLE, 60)
            elif self._y < self._floor_y:
                self._grounded = False
                self._vy = 0.0
            else:
                self._y = self._floor_y
                self._vy = 0.0
            if (
                self.state
                not in (PetState.JUMP, PetState.FALL, PetState.TALK, PetState.LISTENING)
                and self._state_frames >= self._state_duration
            ):
                self._choose_state()
            self.move(int(round(self._x)), int(round(self._y)))
        self._update_bubble_position()
        self.update()

    # ----------------------------------------------------------------- external
    def set_emotion(self, emotion: str) -> None:
        from .nora_personality import EMOTIONS

        self.emotion = emotion if emotion in EMOTIONS else "happy"
        if (
            self.state != PetState.DRAG
            and not self._talking
            and not self._listening
            and not self._manual
        ):
            mapping = {
                "happy": PetState.WAVE,
                "thinking": PetState.IDLE,
                "surprised": PetState.SURPRISED,
                "love": PetState.LOVE,
                "angry": PetState.ANGRY,
                "sad": PetState.IDLE,
                "sleepy": PetState.SLEEP if self._grounded else PetState.IDLE,
                "smug": PetState.SIT,
            }
            self._set_state(mapping[self.emotion], 100)
        self.update()

    def set_listening(self, listening: bool) -> None:
        if listening:
            if not self._listening:
                self._state_before_listening = self.state
                self._listening = True
                self._talking = False
                if self.state != PetState.DRAG:
                    self._set_state(PetState.LISTENING, 100000)
                self.setToolTip("Nora dinliyor 🎙️ · konuşabilirsin senpai")
        else:
            if self._listening:
                self._listening = False
                if self.state == PetState.LISTENING:
                    restore = self._state_before_listening
                    self._set_state(
                        restore
                        if restore not in (PetState.LISTENING, PetState.TALK)
                        else PetState.IDLE,
                        80,
                    )
                self.setToolTip(
                    "Nora 💕 · Sol tık: sohbet · Sağ tık: menü · Sürükle: taşı"
                )
        self.update()

    def set_speaking(self, speaking: bool) -> None:
        if speaking:
            self._listening = False
            if not self._talking:
                self._state_before_talk = self.state
                self._talking = True
                if self.state != PetState.DRAG:
                    self._set_state(PetState.TALK, 100000)
        else:
            if self._talking:
                self._talking = False
                if self.state == PetState.TALK:
                    self._set_state(
                        self._state_before_talk
                        if self._state_before_talk
                        not in (PetState.TALK, PetState.LISTENING)
                        else PetState.IDLE,
                        80,
                    )
        self.update()

    def show_speech(
        self, text: str, duration: int = 5000, speaker: str = "nora"
    ) -> None:
        text = str(text).strip()
        if not text:
            return
        duration = max(1000, min(15000, int(duration)))
        if speaker == "user":
            # The user's own utterance takes priority over ambient Nora lines.
            self._speech_queue.clear()
            self._display_speech(text, duration, "user")
        elif self._bubble is not None and self._bubble_timer.isActive():
            self._speech_queue.append((text, duration, "nora"))
        else:
            self._display_speech(text, duration, "nora")

    def show_user_speech(self, text: str, duration: int = 6000) -> None:
        self.show_speech(text, duration, speaker="user")

    def _display_speech(self, text: str, duration: int, speaker: str) -> None:
        if self._bubble is None:
            self._bubble = SpeechBubble()
        self._bubble.set_text(text, speaker)
        self._bubble_timer.start(duration)
        self._update_bubble_position()
        if self.isVisible():
            self._bubble.show()
            self._bubble.raise_()

    def _hide_bubble(self) -> None:
        if self._bubble:
            self._bubble.hide()
        if self._speech_queue:
            text, duration, speaker = self._speech_queue.popleft()
            self._display_speech(text, duration, speaker)

    def _update_bubble_position(self) -> None:
        if not self._bubble or not self._bubble.isVisible():
            return
        available, _ = self._screen_rects()
        x = int(self._x + self.WIDTH / 2 - self._bubble.width() / 2)
        x = max(available.left(), min(x, available.right() - self._bubble.width() + 1))
        y = int(self._y - self._bubble.height() - 4)
        if y < available.top():
            y = min(
                int(self._y + self.HEIGHT + 4),
                available.bottom() - self._bubble.height() + 1,
            )
        self._bubble.move(x, y)

    def jump_to(self, x: int, y: int) -> None:
        self._x, self._y = float(x), float(y)
        self._grounded = False
        self._vy = -8.0
        self._set_state(PetState.JUMP)
        self.move(int(x), int(y))

    def perform_action(self, action: str) -> str:
        """Explicit commands pin a behavior until the user changes it."""
        if action == "sleep":
            self._manual = True
            self._pinned_state = PetState.SLEEP
            self.emotion = "sleepy"
            self._set_state(PetState.SLEEP if self._grounded else PetState.FALL, 100000)
            return "Uyku modundayım senpai. 'Uyan' dersen kalkarım. z Z Z"
        if action in {"wake", "stop"}:
            self._manual = False
            self._pinned_state = None
            self.emotion = "happy"
            self._grounded = True
            self._y = self._current_floor()
            self._vy = 0.0
            self._set_state(PetState.IDLE, 100000)
            return (
                "Uyandım senpai~"
                if action == "wake"
                else "Tamam, burada bekliyorum senpai."
            )
        if action == "walk":
            self._manual = True
            direction = PetState.WALK_LEFT if self._vx < 0 else PetState.WALK_RIGHT
            self._pinned_state = direction
            self._set_state(direction, 100000)
            return "Dolaşıyorum senpai. 'Dur' diyene kadar gezeceğim. 🐾"
        if action == "dance":
            self._manual = True
            self._pinned_state = PetState.DANCE
            self.emotion = "love"
            self._set_state(PetState.DANCE, 100000)
            self.perform_move({"gesture": "dance"}, fallback=False)
            return "Dans modu açık! 'Dur' dersen bitiririm. 🎵"
        if action == "watch":
            self._manual = True
            self._pinned_state = PetState.WATCH
            self.emotion = "happy"
            self._set_state(PetState.WATCH, 100000)
            return "Video izleme modu açık. Mısırlarımı aldım, birlikte izleyelim~ 🍿"
        if action == "jump":
            if not self._grounded:
                return "Zaten havadayım senpai! Bir de yere ineyim. 😼"
            self._set_state(PetState.JUMP, 100000)
            self.perform_move({"gesture": "jump"}, fallback=False)
            return "Hop! Zıpladım senpai~"
        if action == "sit":
            self._manual = True
            self._pinned_state = PetState.SIT
            self._set_state(PetState.SIT, 100000)
            return "Oturdum senpai. Buradan nöbet tutuyorum."
        if action == "pet":
            self._affection_frames = 120
            self.emotion = "love"
            if not self._manual and not self._listening and not self._talking:
                self._set_state(PetState.LOVE, 100)
            self.show_speech("Mırr… Bunu istediğim anlamına gelmez, baka. 💜", 4000)
            return "Başımı okşadın… Şey, teşekkürler senpai. 💜"
        if action == "blink":
            self._blink_left = 10
            return "Göz kırptım senpai~"
        if action == "yawn":
            if not self._manual:
                self._set_state(PetState.YAWN, 75)
            self.show_speech("Eeehh… Uykum geldi sanpai değil, kahvem bitti. ☕", 3000)
            return "Esnedim senpai. Kahve molası?"
        if action == "wave":
            if not self._manual:
                self._set_state(PetState.WAVE, 100)
            self.perform_move({"gesture": "wave"}, fallback=False)
            self.show_speech("Selam senpai~ 👋", 3000)
            return "Selam verdim senpai~"
        return "Bu hareketi bilmiyorum senpai."

    def set_appearance(self, settings: dict) -> None:
        for key in ("outfit", "hair_color", "accessory", "eye_color"):
            if key in settings:
                self._appearance[key] = str(settings[key])
        if "character_style" in settings:
            requested = str(settings["character_style"])
            if requested in {"sprite", "body", "realistic", "pixel"}:
                self._apply_character_style(requested)
        if "animations" in settings:
            self._animations = bool(settings["animations"])
        if "autonomous" in settings:
            self._autonomous = bool(settings["autonomous"])
            if not self._autonomous and not self._manual:
                self._set_state(PetState.IDLE, 100000)
        self.update()

    def _monitor_screens(self) -> list:
        app = QApplication.instance()
        return sorted(
            app.screens() if app else [],
            key=lambda screen: (screen.geometry().x(), screen.geometry().y()),
        )

    def move_to_monitor(self, target: int | str = "next") -> tuple[bool, str]:
        screens = self._monitor_screens()
        if not screens:
            return False, "Monitör bilgisini alamadım senpai."
        app = QApplication.instance()
        current = (
            app.screenAt(self.pos() + QPoint(self.WIDTH // 2, self.HEIGHT // 2))
            if app
            else None
        )
        if current not in screens:
            current = screens[0]
        index = screens.index(current)
        if isinstance(target, int):
            if not 1 <= target <= len(screens):
                return (
                    False,
                    f"{target} numaralı monitör yok senpai. Şu an {len(screens)} monitör bağlı. 🖥️",
                )
            destination = target - 1
        elif target == "primary":
            primary = app.primaryScreen() if app else screens[0]
            destination = screens.index(primary) if primary in screens else 0
        else:
            destination = (index + (1 if target == "next" else -1)) % len(screens)
        screen = screens[destination]
        area = screen.availableGeometry()
        if area.width() < self.WIDTH or area.height() < self.HEIGHT:
            return False, "Hedef ekranın kullanılabilir alanı çok küçük senpai."
        old_area = current.availableGeometry()
        fraction = (self._x - old_area.left()) / max(1, old_area.width() - self.WIDTH)
        self._x = float(
            area.left() + max(0, min(1, fraction)) * (area.width() - self.WIDTH)
        )
        self._y = float(area.bottom() - self.HEIGHT + 1)
        self._floor_y = self._y
        self._grounded = True
        self._vy = 0.0
        self._on_taskbar = False
        self.move(int(round(self._x)), int(round(self._y)))
        self.position_changed.emit(self.pos())
        self._update_bubble_position()
        name = screen.name() or f"Monitör {destination + 1}"
        return True, f"{destination + 1}. monitöre geçtim senpai ({name}). 🖥️"

    def go_to_screen_edge(self) -> None:
        available, _ = self._screen_rects()
        center = self._x + self.WIDTH / 2
        state = (
            PetState.WALK_LEFT
            if center < available.center().x()
            else PetState.WALK_RIGHT
        )
        self._set_state(state, 100000)

    def shutdown(self) -> None:
        self._timer.stop()
        self._click_timer.stop()
        self._bubble_timer.stop()
        self._speech_queue.clear()
        if self._bubble:
            self._bubble.close()
        self.close()

    # -------------------------------------------------------------------- mouse
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._click_timer.stop()
            self._press_pos = event.globalPos()
            self._drag_offset = event.globalPos() - self.pos()
            self._dragging = False
            if self.character_style == "sprite":
                self._air.grab()
            event.accept()
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(event.globalPos())
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton:
            if (
                not self._dragging
                and (event.globalPos() - self._press_pos).manhattanLength() > 5
            ):
                self._dragging = True
                self._hide_bubble()
                self._set_state(PetState.DRAG)
            if self._dragging:
                point = event.globalPos() - self._drag_offset
                self._x, self._y = float(point.x()), float(point.y())
                self.move(point)
                self.position_changed.emit(self.pos())
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self._dragging:
                self._dragging = False
                self._grounded = False
                origin_y = self._y
                self._vy = 0.0
                if self.character_style == "sprite":
                    # Height above the floor decides how hard the landing looks.
                    drop = max(0.0, self._floor_y - origin_y)
                    self._air.release(speed=drop)
                self._set_state(PetState.FALL)
            else:
                self._click_timer.start()
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._click_timer.stop()
            self.double_clicked.emit()
            event.accept()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self.position_changed.emit(self.pos())
        self._update_bubble_position()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._bubble and self._bubble_timer.isActive():
            self._bubble.show()
            self._update_bubble_position()

    def hideEvent(self, event) -> None:
        self._hide_bubble()
        super().hideEvent(event)

    # ------------------------------------------------------------------ drawing
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        # The renderer snaps every rectangle to a 3×3 grid.  Smoothing or
        # fractional transforms here would blur the deliberately retro art.
        if self.character_style == "pixel":
            painter.setRenderHint(QPainter.Antialiasing, False)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
            self._pixel_artist.draw(
                painter,
                state=self.state.name,
                emotion=self.emotion,
                frame=self._frame,
                appearance=self._appearance,
                talking=self._talking,
                listening=self._listening,
                blinking=self._blink_left > 0,
                affection=self._affection_frames > 0,
                grounded=self._grounded,
                animations=self._animations,
            )
            return
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if self.character_style == "sprite":
            self._sprite_artist.paint(painter, QRectF(0, 0, self.WIDTH, self.HEIGHT))
            return
        if self.character_style == "body":
            pose = self._last_pose
            if pose is None:
                pose = self._motion.tick(0.0)
                self._last_pose = pose
            self._body_artist.draw(
                painter,
                pose,
                appearance=self._appearance,
                target=QRectF(0, 0, self.WIDTH, self.HEIGHT),
                talking=self._talking,
            )
            return
        self._realistic_artist.draw(
            painter,
            state=self.state.name,
            emotion=self.emotion,
            frame=self._frame,
            appearance=self._appearance,
            talking=self._talking,
            listening=self._listening,
            blinking=self._blink_left > 0,
            affection=self._affection_frames > 0,
            grounded=self._grounded,
            animations=self._animations,
        )

    # --------------------------------------------------------------- motion
    def _tick_body(self) -> None:
        """Advance the procedural body animation by one frame interval.

        The motion controller is time based, so the animation keeps the same
        speed whether the pet runs at 30 fps or the window is hidden and comes
        back later (the delta is clamped to avoid a jump).
        """
        if self.character_style != "body":
            return
        if not self._animations:
            return
        dt = self.FPS_INTERVAL / 1000.0
        if self._talking and self._motion.sustained != "talk":
            self._motion.play_name("talk", intensity=0.8)
        elif self._listening and self._motion.sustained != "listen":
            self._motion.play_name("listen", intensity=0.8)
        elif self.state == PetState.IDLE and self._motion.sustained in {
            "talk",
            "listen",
        }:
            self._motion.stop_sustained()
        self._last_pose = self._motion.tick(dt)

    def _tick_sprite(self) -> None:
        """Advance the illustrated character: mood sprite + walk cycle + air."""
        dt = self.FPS_INTERVAL / 1000.0
        self._air.tick(dt)
        if self._air.busy:
            # Airborne sprites own the frame; the walk cycle pauses underneath.
            self._sprite_artist.set_locomotion(None)
            self._sprite_artist.set_airborne(self._air.stage())
        else:
            self._sprite_artist.set_airborne(None)
            style_emotion = self.emotion
            if self.state in (PetState.WALK_LEFT, PetState.WALK_RIGHT):
                self._sprite_artist.set_locomotion(
                    "walk", mirrored=self.state == PetState.WALK_LEFT
                )
            elif self.state in (PetState.DRAG, PetState.FALL):
                self._sprite_artist.set_locomotion(None)
            elif self.state is PetState.DANCE:
                self._sprite_artist.set_locomotion(None)
                self._sprite_artist.set_mood("dance")
            else:
                self._sprite_artist.set_locomotion(None)
                self._sprite_artist.set_mood(style_emotion)
        self._sprite_artist.tick(dt)

    def _reset_air(self) -> None:
        """Return to the standing sprite set (also used when the style changes)."""
        self._air.reset()
        self._sprite_artist.set_airborne(None)

    def perform_move(self, move: Any, *, fallback: bool = True) -> bool:
        """Run an AI-chosen move (already parsed JSON) on the body.

        The payload is validated here again, at the trust boundary: a model can
        only pick a known gesture and a bounded intensity/duration.  When the
        payload is unusable and ``fallback`` is set, body language matching the
        current emotion is chosen at random instead — she never freezes.
        """
        if self.character_style == "sprite":
            return self._perform_sprite_move(move, fallback=fallback)
        if self.character_style != "body":
            return False
        normalized = normalize_move(move)
        if normalized is None and fallback:
            normalized = fallback_move(self.emotion, self.rng)
        if normalized is None:
            return False
        return self._motion.play(normalized)

    def _perform_sprite_move(self, move: Any, *, fallback: bool) -> bool:
        """Show an AI-chosen gesture with the illustrated sheets.

        Validation is shared with the drawn body (same ``normalize_move``), so a
        model cannot invent a gesture or an absurd duration in either style.
        """
        normalized = normalize_move(move)
        if normalized is None and fallback:
            normalized = fallback_move(self.emotion, self.rng)
        if normalized is None:
            return False
        steps = normalized.get("steps") or []
        if not steps:
            return False
        played = False
        for step in steps[:3]:
            gesture = str(step.get("gesture", ""))
            duration = float(step.get("duration", 1.6) or 1.6)
            if self._sprite_artist.express(gesture, duration):
                played = True
        return played

    def current_pose(self):
        """Latest pose, for tests and for the chat panel's small avatar."""
        return self._last_pose

    # ------------------------------------------------------------ character
    def _apply_character_style(self, style: str, *, update: bool = True) -> None:
        """Switch renderers and resize the window without teleporting the pet."""
        style = style if style in {"sprite", "body", "realistic", "pixel"} else "sprite"
        if style == "sprite" and not self._sprite_assets.usable:
            # Honest fallback: no illustrated sheets on disk -> drawn body.
            style = "body"
        self.character_style = style
        old_width, old_height = self.WIDTH, self.HEIGHT
        if style == "pixel":
            self.WIDTH, self.HEIGHT = self.PIXEL_WIDTH, self.PIXEL_HEIGHT
        elif style == "realistic":
            self.WIDTH, self.HEIGHT = AVATAR_WIDTH, AVATAR_HEIGHT
        elif style == "sprite":
            self.WIDTH, self.HEIGHT = self.SPRITE_WIDTH, self.SPRITE_HEIGHT
        else:
            self.WIDTH, self.HEIGHT = self.BODY_WIDTH, self.BODY_HEIGHT
        if not update:
            self.setToolTip(_tooltip_for(style))
            return
        self.setToolTip(_tooltip_for(style))
        if old_width == self.WIDTH and old_height == self.HEIGHT:
            self.update()
            return
        # keep the feet on the floor and the window inside the screen
        available, _ = self._screen_rects()
        self._x = min(
            max(float(available.left() + 2), self._x),
            float(available.right() - self.WIDTH + 1),
        )
        self._y = float(available.bottom() - self.HEIGHT + 1)
        self._floor_y = self._y
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.move(int(round(self._x)), int(round(self._y)))
        self._update_bubble_position()
        self.update()

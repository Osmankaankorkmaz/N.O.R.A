"""A 120×150 transparent 8-bit-style desktop pet, drawn with QPainter.

The character has a small physics/behaviour loop, weighted idle choices,
multi-monitor awareness, sticky screen edges and a separate speech bubble so
the bubble does not shrink the character.  Artwork is generated on a crisp
40×50 logical pixel grid; no sprite or image files are used.
"""

from __future__ import annotations

import random
from collections import deque
from enum import Enum, auto

from PyQt5.QtCore import QPoint, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QApplication, QWidget

from .nora_pixel_art import PixelCharacter


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

    WIDTH = 120
    HEIGHT = 150
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
            "outfit": "classic",
            "hair_color": "#f5f3f0",
            "accessory": "none",
        }
        self._pixel_artist = PixelCharacter()
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
            self.show_speech("Selam senpai~ 👋", 3000)
            return "Selam verdim senpai~"
        return "Bu hareketi bilmiyorum senpai."

    def set_appearance(self, settings: dict) -> None:
        for key in ("outfit", "hair_color", "accessory"):
            if key in settings:
                self._appearance[key] = str(settings[key])
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
                self._vy = 0.0
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

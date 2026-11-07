"""A 120×150 transparent desktop pet, drawn entirely with QPainter.

The character has a small physics/behaviour loop, weighted idle choices,
multi-monitor awareness, sticky screen edges and a separate speech bubble so
the bubble does not shrink the character.  No sprite or image files are used.
"""

from __future__ import annotations

import math
import random
from collections import deque
from enum import Enum, auto

from PyQt5.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PyQt5.QtWidgets import QApplication, QWidget


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
        self._mouth = 0.0
        self._blink_left = 0
        self._next_blink = self.rng.randint(100, 200)
        self._drag_offset = QPoint()
        self._press_pos = QPoint()
        self._dragging = False
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
        if self._talking or self._listening or self.state == PetState.DRAG:
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
        self._frame += 1
        self._state_frames += 1
        if self._blink_left > 0:
            self._blink_left -= 1
        else:
            self._next_blink -= 1
            if self._next_blink <= 0:
                self._blink_left = 6
                self._next_blink = self.rng.randint(100, 200)
        self._mouth += ((0.8 if self._talking else 0.0) - self._mouth) * 0.35
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
                        self._set_state(
                            PetState.LISTENING if self._listening else PetState.IDLE, 60
                        )
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
        if self.state != PetState.DRAG and not self._talking and not self._listening:
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
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        breath = math.sin(self._frame * 0.055)
        tail = math.sin(self._frame * 0.12)
        wind = math.sin(self._frame * 0.045) * 2.2
        walk = (
            math.sin(self._frame * 0.32)
            if self.state in (PetState.WALK_LEFT, PetState.WALK_RIGHT)
            else 0.0
        )
        bob = breath * 1.1 if self._grounded else 0.0
        if self.state == PetState.SIT:
            bob += 5

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 42))
        painter.drawEllipse(QRectF(29, 140, 62, 7))
        painter.save()
        painter.translate(0, bob)
        self._draw_tail(painter, tail)
        self._draw_back_hair(painter, wind)
        self._draw_legs(painter, walk)
        self._draw_body(painter)
        self._draw_arms(painter, walk)
        if self._listening or self.state == PetState.LISTENING:
            painter.save()
            painter.translate(60, 55)
            painter.rotate(-6.5)
            painter.translate(-60, -55)
        self._draw_ears(painter)
        self._draw_head(painter)
        self._draw_face(painter)
        self._draw_front_hair(painter, wind)
        self._draw_star_clip(painter)
        if self._listening or self.state == PetState.LISTENING:
            painter.restore()
            self._draw_listening_hand(painter)
        painter.restore()
        self._draw_effects(painter)

    def _draw_tail(self, p: QPainter, tail: float) -> None:
        path = QPainterPath(QPointF(76, 112))
        path.cubicTo(104, 121, 120, 91 + tail * 7, 106, 71 + tail * 9)
        path.cubicTo(99, 60 + tail * 8, 90, 68 + tail * 6, 98, 78 + tail * 6)
        gradient = QLinearGradient(76, 112, 108, 66)
        gradient.setColorAt(0, QColor("#241332"))
        gradient.setColorAt(0.6, QColor("#4a2a66"))
        gradient.setColorAt(1, QColor("#7c4dff"))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QBrush(gradient), 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(QColor(190, 140, 255, 110), 2.2, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#b388ff"))
        p.drawEllipse(QRectF(94, 72 + tail * 6, 8, 8))

    def _draw_back_hair(self, p: QPainter, wind: float) -> None:
        path = QPainterPath(QPointF(31, 30))
        path.cubicTo(11, 47, 17 + wind, 90, 23 + wind, 118)
        path.quadTo(31, 112, 39, 109)
        path.lineTo(60, 120)
        path.lineTo(81, 109)
        path.quadTo(89, 112, 97 - wind, 118)
        path.cubicTo(105 - wind, 82, 109, 43, 88, 28)
        path.cubicTo(70, 11, 45, 13, 31, 30)
        gradient = QLinearGradient(20, 18, 96, 120)
        gradient.setColorAt(0, QColor("#170b22"))
        gradient.setColorAt(0.45, QColor("#33204d"))
        gradient.setColorAt(0.75, QColor("#4a2a66"))
        gradient.setColorAt(1, QColor("#160c20"))
        p.setPen(QPen(QColor("#120818"), 1))
        p.setBrush(QBrush(gradient))
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)
        for x, alpha in ((27, 70), (36, 48), (84, 65), (93, 45)):
            strand = QPainterPath(QPointF(x, 42))
            strand.cubicTo(x - 4 + wind * 0.4, 66, x + 2, 91, x + wind, 111)
            p.setPen(QPen(QColor(162, 108, 224, alpha), 1.1, Qt.SolidLine, Qt.RoundCap))
            p.drawPath(strand)

    def _draw_legs(self, p: QPainter, walk: float) -> None:
        skin = QColor("#f8cfbd")
        p.setPen(QPen(skin, 7, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        if self.state == PetState.SIT:
            left = QPainterPath(QPointF(50, 112))
            left.quadTo(39, 126, 53, 131)
            right = QPainterPath(QPointF(69, 112))
            right.quadTo(81, 126, 67, 131)
            p.drawPath(left)
            p.drawPath(right)
            feet = [(48, 128), (62, 128)]
            socks = []
        else:
            swing = walk * 5
            p.drawLine(QPointF(50, 113), QPointF(48 + swing, 136))
            p.drawLine(QPointF(69, 113), QPointF(71 - swing, 136))
            feet = [(40 + swing, 134), (63 - swing, 134)]
            socks = [(44 + swing, 124, 9, 12), (66 - swing, 124, 9, 12)]
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2a1740"))
        for rect in socks:
            p.drawRoundedRect(QRectF(*rect), 3, 3)
        p.setPen(QPen(QColor("#160c20"), 1))
        p.setBrush(QColor("#3b2055"))
        for x, y in feet:
            p.drawEllipse(QRectF(x, y, 16, 7))
            p.setPen(QPen(QColor("#b388ff"), 0.8))
            p.drawLine(QPointF(x + 3, y + 2), QPointF(x + 12, y + 2))
            p.setPen(QPen(QColor("#160c20"), 1))

    def _draw_body(self, p: QPainter) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f8cfbd"))
        p.drawEllipse(QRectF(54, 72, 12, 15))
        dress = QPainterPath(QPointF(44, 82))
        dress.quadTo(60, 78, 75, 82)
        dress.lineTo(85, 118)
        dress.quadTo(60, 125, 34, 118)
        dress.closeSubpath()
        gradient = QLinearGradient(42, 80, 80, 124)
        gradient.setColorAt(0, QColor("#b58aff"))
        gradient.setColorAt(0.35, QColor("#7c4dff"))
        gradient.setColorAt(0.8, QColor("#4a2a80"))
        gradient.setColorAt(1, QColor("#2c1742"))
        p.setPen(QPen(QColor("#241332"), 1.2))
        p.setBrush(QBrush(gradient))
        p.drawPath(dress)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.setBrush(Qt.NoBrush)
        hem = QPainterPath(QPointF(37, 117))
        hem.quadTo(60, 123, 82, 117)
        p.drawPath(hem)
        p.setPen(QPen(QColor(30, 15, 50, 110), 1))
        for x in (48, 60, 72):
            p.drawLine(QPointF(x, 96), QPointF(x + (x - 60) * 0.14, 118))
        # White collar + golden bow with a tiny cat bell.
        collar = QPainterPath(QPointF(52, 81))
        collar.quadTo(60, 88, 68, 81)
        collar.lineTo(60, 90)
        collar.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#fff4fb"))
        p.drawPath(collar)
        bow = QPainterPath(QPointF(60, 86))
        bow.lineTo(49, 80)
        bow.quadTo(47, 86, 50, 92)
        bow.closeSubpath()
        bow.moveTo(60, 86)
        bow.lineTo(71, 80)
        bow.quadTo(73, 86, 70, 92)
        bow.closeSubpath()
        p.setPen(QPen(QColor("#c99721"), 0.8))
        p.setBrush(QColor("#ffd166"))
        p.drawPath(bow)
        p.drawEllipse(QRectF(57, 83, 6, 6))
        p.setPen(QPen(QColor("#9c6b12"), 0.7))
        p.drawLine(QPointF(58.5, 87), QPointF(61.5, 87))

    def _draw_arms(self, p: QPainter, walk: float) -> None:
        skin = QLinearGradient(0, 80, 0, 112)
        skin.setColorAt(0, QColor("#ffe0d0"))
        skin.setColorAt(1, QColor("#f3bda9"))
        swing = walk * 5
        if self._listening or self.state == PetState.LISTENING:
            p.setPen(QPen(QBrush(skin), 7, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(43, 88), QPointF(30, 106))
            arm = QPainterPath(QPointF(76, 88))
            arm.cubicTo(94, 84, 100, 68, 91, 53)
            p.drawPath(arm)
            return
        p.setPen(QPen(QBrush(skin), 7, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(43, 87), QPointF(33 + swing, 108))
        if (
            self.state == PetState.WAVE
            or self.emotion == "happy"
            and self.state == PetState.IDLE
        ):
            wave = math.sin(self._frame * 0.3) * 4
            path = QPainterPath(QPointF(76, 87))
            path.quadTo(91, 80, 94, 64 + wave)
            p.drawPath(path)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#f8cfbd"))
            p.drawEllipse(QRectF(90, 60 + wave, 9, 9))
        else:
            p.drawLine(QPointF(76, 87), QPointF(86 - swing, 108))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#fff4fb"))
        p.drawEllipse(QRectF(29 + swing, 104, 8, 4))
        if not (
            self.state == PetState.WAVE
            or self.emotion == "happy"
            and self.state == PetState.IDLE
        ):
            p.drawEllipse(QRectF(82 - swing, 104, 8, 4))

    def _draw_listening_hand(self, p: QPainter) -> None:
        skin = QLinearGradient(84, 42, 98, 62)
        skin.setColorAt(0, QColor("#ffe0d0"))
        skin.setColorAt(1, QColor("#f3bda9"))
        p.setPen(QPen(QColor("#d99c89"), 0.8))
        p.setBrush(QBrush(skin))
        cup = QPainterPath(QPointF(87, 60))
        cup.quadTo(82, 49, 89, 42)
        cup.quadTo(98, 41, 99, 51)
        cup.quadTo(98, 61, 87, 60)
        p.drawPath(cup)
        p.setPen(QPen(QColor("#d99c89"), 0.7, Qt.SolidLine, Qt.RoundCap))
        for dx in (0, 3, 6):
            p.drawLine(QPointF(89 + dx, 45), QPointF(90 + dx, 52))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#fff4fb"))
        p.drawEllipse(QRectF(85, 60, 9, 4))

    def _draw_ears(self, p: QPainter) -> None:
        twitch = math.sin(self._frame * 0.35) * 2 if self._listening else 0.0
        for outer, inner, fluff in (
            (
                [(30, 32), (33, 6), (51, 26)],
                [(34, 27), (35, 13), (45, 25)],
                [(36, 24), (38, 18), (41, 24)],
            ),
            (
                [(69, 26), (87, 6 + twitch), (91, 33)],
                [(75, 25), (85, 13 + twitch), (87, 28)],
                [(79, 24), (82, 18 + twitch), (85, 25)],
            ),
        ):
            p.setPen(QPen(QColor("#160c20"), 1.2))
            p.setBrush(QColor("#2c1742"))
            p.drawPolygon(QPolygonF([QPointF(*point) for point in outer]))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#e98ab4"))
            p.drawPolygon(QPolygonF([QPointF(*point) for point in inner]))
            p.setPen(QPen(QColor(255, 235, 245, 170), 0.9, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            tuft = QPainterPath(QPointF(*fluff[0]))
            tuft.lineTo(QPointF(*fluff[1]))
            tuft.lineTo(QPointF(*fluff[2]))
            p.drawPath(tuft)

    def _draw_head(self, p: QPainter) -> None:
        gradient = QRadialGradient(52, 42, 44, 49, 38)
        gradient.setColorAt(0, QColor("#ffe9dd"))
        gradient.setColorAt(0.72, QColor("#f9d0bd"))
        gradient.setColorAt(1, QColor("#eeb59f"))
        head = QPainterPath(QPointF(30, 48))
        head.cubicTo(30, 25, 90, 25, 90, 48)
        head.cubicTo(90, 69, 76, 84, 60, 84)
        head.cubicTo(44, 84, 30, 69, 30, 48)
        p.setPen(QPen(QColor("#d99c89"), 0.8))
        p.setBrush(QBrush(gradient))
        p.drawPath(head)

    def _draw_face(self, p: QPainter) -> None:
        closed = self._blink_left > 0 or self.state == PetState.SLEEP
        surprised = self.emotion == "surprised" or self.state == PetState.SURPRISED
        love = self.emotion == "love"
        angry = self.emotion == "angry"
        listening = self._listening or self.state == PetState.LISTENING
        # Brows give the face a little more expression.
        p.setPen(QPen(QColor("#4a2b58"), 1.1, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        for x, tilt in ((45, -1), (75, 1)):
            brow = QPainterPath(QPointF(x - 6, 40 + (tilt if angry else 0)))
            brow.quadTo(
                x, 37 - (2 if listening else 0), x + 6, 40 - (tilt if angry else 0)
            )
            p.drawPath(brow)
        for x in (45, 75):
            if closed:
                p.setPen(QPen(QColor("#3a204c"), 2, Qt.SolidLine, Qt.RoundCap))
                path = QPainterPath(QPointF(x - 6, 53))
                path.quadTo(x, 57 if self.state == PetState.SLEEP else 51, x + 6, 53)
                p.drawPath(path)
                continue
            h, w = (20, 16) if surprised else (17, 15)
            p.setPen(QPen(QColor("#3a204c"), 0.9))
            p.setBrush(QColor("#fffdfd"))
            p.drawEllipse(QRectF(x - w / 2, 52 - h / 2, w, h))
            iris = QRadialGradient(x, 51, 6.5)
            if love:
                iris.setColorAt(0, QColor("#ffc1da"))
                iris.setColorAt(0.6, QColor("#ff5c99"))
                iris.setColorAt(1, QColor("#c2185b"))
            elif angry:
                iris.setColorAt(0, QColor("#ffbf9a"))
                iris.setColorAt(0.6, QColor("#ff7043"))
                iris.setColorAt(1, QColor("#bf360c"))
            else:
                iris.setColorAt(0, QColor("#f3b6ff"))
                iris.setColorAt(0.55, QColor("#c13b8a"))
                iris.setColorAt(1, QColor("#5b1a78"))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(iris))
            p.drawEllipse(QRectF(x - 5.2, 46, 10.4, 12.5))
            p.setBrush(QColor("#1a0d24"))
            p.drawEllipse(QRectF(x - 1.9, 48, 3.8, 7.2))
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QRectF(x - 3.4, 46.3, 3.4, 3.4))
            p.drawEllipse(QRectF(x + 1.8, 53, 1.7, 1.7))
            p.setPen(QPen(QColor("#241332"), 2.1, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            lash = QPainterPath(QPointF(x - 8, 47))
            lash.quadTo(x, 39.5, x + 8, 47)
            p.drawPath(lash)
            p.setPen(QPen(QColor("#241332"), 1.1, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(
                QPointF(x + (7 if x > 60 else -7), 46),
                QPointF(x + (10 if x > 60 else -10), 43),
            )
            if angry:
                p.setPen(QPen(QColor("#3a204c"), 1.4, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x - 7, 40), QPointF(x + 5, 43 if x < 60 else 40))
        for x in (32, 76):
            blush = QRadialGradient(x + 6, 64, 7)
            blush.setColorAt(0, QColor(255, 105, 150, 120 if love else 62))
            blush.setColorAt(1, QColor(255, 105, 150, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(blush))
            p.drawEllipse(QRectF(x, 60, 13, 8))
        p.setPen(QPen(QColor("#d99c89"), 0.8))
        p.drawPoint(QPointF(60, 62))
        p.setPen(QPen(QColor("#9c4665"), 1.4, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        if self._mouth > 0.15 and self.state != PetState.SLEEP:
            p.setBrush(QColor("#e8799d"))
            p.drawEllipse(QRectF(56, 68, 8, 3 + self._mouth * 6))
        elif surprised:
            p.setBrush(QColor("#d87191"))
            p.drawEllipse(QRectF(57, 67, 6, 8))
        elif listening:
            smile = QPainterPath(QPointF(56, 69))
            smile.quadTo(60, 72, 64, 69)
            p.drawPath(smile)
        elif angry or self.emotion == "sad":
            path = QPainterPath(QPointF(55, 72))
            path.quadTo(60, 67, 65, 72)
            p.drawPath(path)
        else:
            path = QPainterPath(QPointF(54, 68))
            path.quadTo(57, 72, 60, 68)
            path.quadTo(63, 72, 66, 68)
            p.drawPath(path)

    def _draw_front_hair(self, p: QPainter, wind: float) -> None:
        gradient = QLinearGradient(30, 18, 86, 50)
        gradient.setColorAt(0, QColor("#170b22"))
        gradient.setColorAt(0.45, QColor("#3a2256"))
        gradient.setColorAt(0.72, QColor("#563073"))
        gradient.setColorAt(1, QColor("#241332"))
        p.setPen(QPen(QColor("#120818"), 0.8))
        p.setBrush(QBrush(gradient))
        cap = QPainterPath(QPointF(29, 35))
        cap.cubicTo(28, 13, 89, 11, 92, 35)
        cap.lineTo(84, 40)
        cap.quadTo(60, 27, 36, 40)
        cap.closeSubpath()
        p.drawPath(cap)
        for i, x in enumerate((34, 44, 54, 64, 74)):
            sway = wind * (0.6 + i * 0.12)
            bang = QPainterPath(QPointF(x, 25))
            bang.quadTo(x + 5 + sway, 32, x + 2 + sway, 43 - (i % 2) * 3)
            bang.quadTo(x + 11, 35, x + 12, 26)
            bang.closeSubpath()
            p.drawPath(bang)
        left = QPainterPath(QPointF(30, 32))
        left.cubicTo(21, 52, 24 + wind, 77, 30 + wind, 90)
        left.lineTo(38, 82)
        left.cubicTo(34, 61, 38, 43, 39, 30)
        left.closeSubpath()
        right = QPainterPath(QPointF(89, 32))
        right.cubicTo(99, 52, 96 - wind, 77, 90 - wind, 90)
        right.lineTo(82, 82)
        right.cubicTo(86, 61, 82, 43, 81, 30)
        right.closeSubpath()
        p.drawPath(left)
        p.drawPath(right)
        p.setPen(QPen(QColor(200, 155, 255, 105), 1.2, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        highlight = QPainterPath(QPointF(38, 25))
        highlight.quadTo(58, 16, 80, 26)
        p.drawPath(highlight)
        shine = QPainterPath(QPointF(42, 29))
        shine.quadTo(50, 25, 58, 28)
        p.setPen(QPen(QColor(255, 255, 255, 55), 1, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(shine)

    def _draw_star_clip(self, p: QPainter) -> None:
        points = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = 5.5 if i % 2 == 0 else 2.5
            points.append(
                QPointF(34 + math.cos(angle) * radius, 35 + math.sin(angle) * radius)
            )
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 209, 102, 55))
        p.drawEllipse(QRectF(27, 28, 14, 14))
        p.setPen(QPen(QColor("#c99721"), 0.7))
        p.setBrush(QColor("#ffd166"))
        p.drawPolygon(QPolygonF(points))

    def _draw_effects(self, p: QPainter) -> None:
        if self._listening or self.state == PetState.LISTENING:
            pulse = (math.sin(self._frame * 0.18) + 1) / 2
            p.setBrush(Qt.NoBrush)
            for i, radius in enumerate((6, 10, 14)):
                alpha = int(210 - i * 50 - pulse * 35)
                p.setPen(
                    QPen(
                        QColor(255, 107, 157, max(50, alpha)),
                        1.6,
                        Qt.SolidLine,
                        Qt.RoundCap,
                    )
                )
                p.drawArc(
                    QRectF(100 - radius, 49 - radius, radius * 2, radius * 2),
                    -55 * 16,
                    110 * 16,
                )
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ff6b9d"))
            p.drawEllipse(QRectF(98, 47, 4, 4))
        p.setPen(Qt.NoPen)
        if self.emotion == "love" or self.state == PetState.LOVE:
            p.setBrush(QColor("#ff4f8b"))
            p.setFont(QFont("Segoe UI Symbol", 10))
            for i in range(3):
                x = 12 + i * 42 + math.sin(self._frame * 0.08 + i * 2) * 5
                y = 20 + math.cos(self._frame * 0.07 + i) * 7
                p.drawText(QPointF(x, y), "♥")
        elif self.emotion == "angry" or self.state == PetState.ANGRY:
            p.setPen(QPen(QColor("#ff7043"), 2, Qt.SolidLine, Qt.RoundCap))
            for x, y in ((14, 24), (99, 32), (94, 13)):
                p.drawLine(QPointF(x - 3, y - 3), QPointF(x + 3, y + 3))
                p.drawLine(QPointF(x + 3, y - 3), QPointF(x - 3, y + 3))
        if self.state == PetState.SLEEP or self.emotion == "sleepy":
            p.setPen(Qt.NoPen)
            p.setFont(QFont("Segoe UI", 9, QFont.Bold))
            for i in range(3):
                phase = (self._frame + i * 24) % 90
                alpha = int(220 * (1 - phase / 100))
                p.setPen(QColor(179, 136, 255, max(40, alpha)))
                p.drawText(
                    QPointF(91 + i * 5, 34 - phase * 0.28), "z" if i == 0 else "Z"
                )

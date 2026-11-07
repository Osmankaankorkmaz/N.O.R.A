"""A 120×150 transparent desktop pet, drawn entirely with QPainter.

The character has a small physics/behaviour loop, weighted idle choices,
multi-monitor awareness, sticky screen edges and a separate speech bubble so
the bubble does not shrink the character.  No sprite or image files are used.
"""

from __future__ import annotations

import math
import random
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
        self.setFixedSize(240, 76)

    def set_text(self, text: str) -> None:
        text = str(text).replace("\n", " ").strip()
        self._text = text[:60] + "..." if len(text) > 60 else text
        metrics = self.fontMetrics()
        rect = metrics.boundingRect(
            QRectF(0, 0, 214, 200).toRect(),
            Qt.TextWordWrap | Qt.AlignCenter,
            self._text,
        )
        self.setFixedHeight(max(54, min(92, rect.height() + 26)))
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
        self._state_before_talk = PetState.IDLE
        self._mouth = 0.0
        self._blink_left = 0
        self._next_blink = self.rng.randint(100, 200)
        self._drag_offset = QPoint()
        self._press_pos = QPoint()
        self._dragging = False
        self._bubble: SpeechBubble | None = None
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
        if self._talking or self.state == PetState.DRAG:
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
                        self._set_state(PetState.IDLE, 60)
            elif self._y < self._floor_y:
                self._grounded = False
                self._vy = 0.0
            else:
                self._y = self._floor_y
                self._vy = 0.0
            if (
                self.state not in (PetState.JUMP, PetState.FALL, PetState.TALK)
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
        if self.state != PetState.DRAG and not self._talking:
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

    def set_speaking(self, speaking: bool) -> None:
        if speaking:
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
                        if self._state_before_talk != PetState.TALK
                        else PetState.IDLE,
                        80,
                    )
        self.update()

    def show_speech(self, text: str, duration: int = 5000) -> None:
        if self._bubble is None:
            self._bubble = SpeechBubble()
        self._bubble.set_text(text)
        self._bubble_timer.start(max(1000, min(15000, int(duration))))
        self._update_bubble_position()
        if self.isVisible():
            self._bubble.show()
            self._bubble.raise_()

    def _hide_bubble(self) -> None:
        if self._bubble:
            self._bubble.hide()

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
        self._draw_ears(painter)
        self._draw_head(painter)
        self._draw_face(painter)
        self._draw_front_hair(painter, wind)
        self._draw_star_clip(painter)
        painter.restore()
        self._draw_effects(painter)

    def _draw_tail(self, p: QPainter, tail: float) -> None:
        path = QPainterPath(QPointF(76, 112))
        path.cubicTo(104, 120, 119, 91 + tail * 7, 106, 72 + tail * 9)
        path.cubicTo(99, 61 + tail * 8, 91, 68 + tail * 6, 98, 77 + tail * 6)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#35204f"), 9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPath(path)
        p.setPen(QPen(QColor("#6d4392"), 3, Qt.SolidLine, Qt.RoundCap))
        p.drawPath(path)

    def _draw_back_hair(self, p: QPainter, wind: float) -> None:
        path = QPainterPath(QPointF(31, 30))
        path.cubicTo(12, 46, 18 + wind, 88, 24 + wind, 116)
        path.lineTo(40, 108)
        path.lineTo(60, 119)
        path.lineTo(81, 108)
        path.lineTo(96 - wind, 116)
        path.cubicTo(104 - wind, 82, 108, 43, 88, 28)
        path.cubicTo(70, 12, 45, 14, 31, 30)
        gradient = QLinearGradient(20, 20, 95, 118)
        gradient.setColorAt(0, QColor("#241332"))
        gradient.setColorAt(0.55, QColor("#43265e"))
        gradient.setColorAt(1, QColor("#1c1029"))
        p.setPen(QPen(QColor("#160c20"), 1))
        p.setBrush(QBrush(gradient))
        p.drawPath(path)

    def _draw_legs(self, p: QPainter, walk: float) -> None:
        skin = QColor("#f6c8b4")
        p.setPen(QPen(skin, 7, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        if self.state == PetState.SIT:
            left = QPainterPath(QPointF(50, 112))
            left.quadTo(40, 126, 53, 130)
            right = QPainterPath(QPointF(69, 112))
            right.quadTo(80, 126, 67, 130)
            p.drawPath(left)
            p.drawPath(right)
            feet = [(49, 127), (63, 127)]
        else:
            swing = walk * 5
            p.drawLine(QPointF(50, 113), QPointF(48 + swing, 136))
            p.drawLine(QPointF(69, 113), QPointF(71 - swing, 136))
            feet = [(41 + swing, 134), (64 - swing, 134)]
        p.setPen(QPen(QColor("#241332"), 1))
        p.setBrush(QColor("#3b2055"))
        for x, y in feet:
            p.drawEllipse(QRectF(x, y, 15, 7))

    def _draw_body(self, p: QPainter) -> None:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#f6c8b4"))
        p.drawEllipse(QRectF(54, 72, 12, 15))
        dress = QPainterPath(QPointF(44, 82))
        dress.lineTo(75, 82)
        dress.lineTo(84, 119)
        dress.quadTo(60, 124, 35, 119)
        dress.closeSubpath()
        gradient = QLinearGradient(45, 82, 78, 122)
        gradient.setColorAt(0, QColor("#9b6dff"))
        gradient.setColorAt(0.5, QColor("#7c4dff"))
        gradient.setColorAt(1, QColor("#3b205e"))
        p.setPen(QPen(QColor("#2c1742"), 1.2))
        p.setBrush(QBrush(gradient))
        p.drawPath(dress)
        p.setPen(QPen(QColor(40, 20, 65, 100), 1))
        for x in (48, 60, 72):
            p.drawLine(QPointF(x, 96), QPointF(x + (x - 60) * 0.12, 118))
        # Yellow collar bow.
        bow = QPainterPath(QPointF(60, 86))
        bow.lineTo(50, 81)
        bow.lineTo(51, 92)
        bow.closeSubpath()
        bow.moveTo(60, 86)
        bow.lineTo(70, 81)
        bow.lineTo(69, 92)
        bow.closeSubpath()
        p.setPen(QPen(QColor("#c99721"), 0.8))
        p.setBrush(QColor("#ffd166"))
        p.drawPath(bow)
        p.drawEllipse(QRectF(57.5, 83.5, 5, 5))

    def _draw_arms(self, p: QPainter, walk: float) -> None:
        p.setPen(QPen(QColor("#f6c8b4"), 7, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        swing = walk * 5
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
            p.setBrush(QColor("#f6c8b4"))
            p.drawEllipse(QRectF(90, 60 + wave, 9, 9))
        else:
            p.drawLine(QPointF(76, 87), QPointF(86 - swing, 108))

    def _draw_ears(self, p: QPainter) -> None:
        for outer, inner in (
            ([(30, 32), (33, 6), (51, 26)], [(34, 27), (35, 13), (45, 25)]),
            ([(69, 26), (87, 6), (91, 33)], [(75, 25), (85, 13), (87, 28)]),
        ):
            path = QPolygonF([QPointF(*point) for point in outer])
            p.setPen(QPen(QColor("#1c1029"), 1.2))
            p.setBrush(QColor("#35204f"))
            p.drawPolygon(path)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#e98ab4"))
            p.drawPolygon(QPolygonF([QPointF(*point) for point in inner]))

    def _draw_head(self, p: QPainter) -> None:
        gradient = QRadialGradient(52, 42, 42, 49, 38)
        gradient.setColorAt(0, QColor("#ffe5d7"))
        gradient.setColorAt(0.75, QColor("#f8cdb9"))
        gradient.setColorAt(1, QColor("#eeb59f"))
        p.setPen(QPen(QColor("#d99c89"), 0.8))
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QRectF(30, 24, 60, 58))

    def _draw_face(self, p: QPainter) -> None:
        closed = self._blink_left > 0 or self.state == PetState.SLEEP
        surprised = self.emotion == "surprised" or self.state == PetState.SURPRISED
        love = self.emotion == "love"
        angry = self.emotion == "angry"
        for x in (45, 75):
            if closed:
                p.setPen(QPen(QColor("#3a204c"), 2, Qt.SolidLine, Qt.RoundCap))
                p.setBrush(Qt.NoBrush)
                path = QPainterPath(QPointF(x - 6, 53))
                path.quadTo(x, 57 if self.state == PetState.SLEEP else 51, x + 6, 53)
                p.drawPath(path)
                continue
            h, w = (20, 16) if surprised else (16, 14)
            p.setPen(QPen(QColor("#4a2b58"), 0.8))
            p.setBrush(QColor("#fffdfd"))
            p.drawEllipse(QRectF(x - w / 2, 52 - h / 2, w, h))
            iris = QRadialGradient(x, 51, 6)
            if love:
                iris.setColorAt(0, QColor("#ff9ec4"))
                iris.setColorAt(1, QColor("#d81b60"))
            elif angry:
                iris.setColorAt(0, QColor("#ffab75"))
                iris.setColorAt(1, QColor("#d84315"))
            else:
                iris.setColorAt(0, QColor("#c19bff"))
                iris.setColorAt(0.65, QColor("#8e44ad"))
                iris.setColorAt(1, QColor("#5b1a78"))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(iris))
            p.drawEllipse(QRectF(x - 5, 46, 10, 12))
            p.setBrush(QColor("#1a0d24"))
            p.drawEllipse(QRectF(x - 1.8, 48, 3.6, 7))
            p.setBrush(QColor("#ffffff"))
            p.drawEllipse(QRectF(x - 3.2, 46.5, 3.2, 3.2))
            p.drawEllipse(QRectF(x + 1.8, 53, 1.6, 1.6))
            p.setPen(QPen(QColor("#241332"), 2, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            lash = QPainterPath(QPointF(x - 8, 47))
            lash.quadTo(x, 40, x + 8, 47)
            p.drawPath(lash)
            if angry:
                p.drawLine(QPointF(x - 7, 40), QPointF(x + 5, 43 if x < 60 else 40))
        # Soft blush, stronger when loved.
        for x in (32, 76):
            blush = QRadialGradient(x + 6, 64, 7)
            blush.setColorAt(0, QColor(255, 105, 150, 115 if love else 58))
            blush.setColorAt(1, QColor(255, 105, 150, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(blush))
            p.drawEllipse(QRectF(x, 60, 13, 8))
        p.setPen(QPen(QColor("#9c4665"), 1.4, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        if self._mouth > 0.15 and self.state != PetState.SLEEP:
            p.setBrush(QColor("#e8799d"))
            p.drawEllipse(QRectF(56, 68, 8, 3 + self._mouth * 6))
        elif surprised:
            p.setBrush(QColor("#d87191"))
            p.drawEllipse(QRectF(57, 67, 6, 8))
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
        gradient = QLinearGradient(30, 20, 85, 48)
        gradient.setColorAt(0, QColor("#21112e"))
        gradient.setColorAt(0.5, QColor("#4a2a66"))
        gradient.setColorAt(1, QColor("#241332"))
        p.setPen(QPen(QColor("#160c20"), 0.8))
        p.setBrush(QBrush(gradient))
        cap = QPainterPath(QPointF(29, 35))
        cap.cubicTo(28, 14, 89, 12, 92, 35)
        cap.lineTo(84, 39)
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
        left.cubicTo(22, 51, 25 + wind, 76, 31 + wind, 89)
        left.lineTo(38, 81)
        left.cubicTo(34, 61, 38, 43, 39, 30)
        left.closeSubpath()
        right = QPainterPath(QPointF(89, 32))
        right.cubicTo(98, 51, 95 - wind, 76, 89 - wind, 89)
        right.lineTo(82, 81)
        right.cubicTo(86, 61, 82, 43, 81, 30)
        right.closeSubpath()
        p.drawPath(left)
        p.drawPath(right)
        p.setPen(QPen(QColor(155, 105, 205, 90), 1))
        p.setBrush(Qt.NoBrush)
        highlight = QPainterPath(QPointF(38, 25))
        highlight.quadTo(58, 17, 80, 26)
        p.drawPath(highlight)

    def _draw_star_clip(self, p: QPainter) -> None:
        points = []
        for i in range(10):
            angle = -math.pi / 2 + i * math.pi / 5
            radius = 5.5 if i % 2 == 0 else 2.5
            points.append(
                QPointF(34 + math.cos(angle) * radius, 35 + math.sin(angle) * radius)
            )
        p.setPen(QPen(QColor("#c99721"), 0.7))
        p.setBrush(QColor("#ffd166"))
        p.drawPolygon(QPolygonF(points))

    def _draw_effects(self, p: QPainter) -> None:
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

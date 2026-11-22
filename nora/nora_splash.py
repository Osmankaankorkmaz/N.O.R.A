"""The opening screen: a dark glass card with the white **N** being built.

The splash exists for one reason: the model/voice/database warm-up takes long
enough that a bare white window looks broken.  It is deliberately *not* a fake
progress bar — every step it reports is a real step that finished, and if a step
fails the card says so instead of jumping to 100%.

Animation, all of it real (no pre-rendered video):

* the ring draws itself clockwise;
* the four bands of the N slide in from alternating sides and lock together;
* the spark pops in last, then breathes;
* the wordmark letters fade up one by one.
"""

from __future__ import annotations


from PyQt5.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget

from .nora_brand import (
    BRAND_WHITE,
    draw_n,
    splash_gradient,
    spark_path,
    TOP,
    BOTTOM,
)

#: The steps a launch really goes through.  Kept here so the splash and the app
#: cannot drift apart; the app reports progress by index.
STEPS: tuple[str, ...] = (
    "Ayarlar okunuyor",
    "Hafıza hazırlanıyor",
    "Ses ve konuşma yükleniyor",
    "Nora uyanıyor",
)


class SplashScreen(QWidget):
    """Frameless, translucent launch card.  Never accepts input focus."""

    finished = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(520, 400)
        self.setWindowTitle("Nora")

        self._intro_value = 0.0
        self._progress = 0.0
        self._ring = 0.0
        self._bands = 0.0
        self._spark = 0.0
        self._title = 0.0
        self._status = STEPS[0]
        self._detail = ""
        self._pulse = 0.0
        self._failed = False

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(33)
        self._pulse_timer.timeout.connect(self._tick)

        # Three staggered entrances: ring, letter, spark, wordmark.
        self._intro = QPropertyAnimation(self, b"introProgress", self)
        self._intro.setDuration(1150)
        self._intro.setStartValue(0.0)
        self._intro.setEndValue(1.0)
        self._intro.setEasingCurve(QEasingCurve.OutCubic)

    # ------------------------------------------------------------- animation
    def _get_intro(self) -> float:
        return self._intro_value

    def _set_intro(self, value: float) -> None:
        self._intro_value = float(value)
        self._ring = min(1.0, self._intro_value / 0.55)
        self._bands = max(0.0, min(1.0, (self._intro_value - 0.28) / 0.52))
        self._spark = max(0.0, min(1.0, (self._intro_value - 0.72) / 0.28))
        self._title = max(0.0, min(1.0, (self._intro_value - 0.45) / 0.55))
        self.update()

    introProgress = pyqtProperty(float, fget=_get_intro, fset=_set_intro)

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.055) % 1.0
        self.update()

    def start(self) -> None:
        """Show the card and play the entrance."""
        self._intro_value = 0.0
        self._intro.start()
        self._pulse_timer.start()
        self.show()
        self._centre()

    def _centre(self) -> None:
        screen = self.screen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(
            area.center().x() - self.width() // 2,
            area.center().y() - self.height() // 2,
        )

    # ---------------------------------------------------------------- status
    def set_step(self, index: int) -> None:
        """Report the step that **finished**; the next one becomes current."""
        index = max(0, min(len(STEPS) - 1, int(index)))
        self._status = STEPS[index]
        self._progress = min(1.0, max(self._progress, (index + 0.15) / len(STEPS)))
        self.update()

    def set_status(self, text: str) -> None:
        """Free-form status for work that is not one of the fixed steps."""
        self._detail = str(text)
        self.update()

    def set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    def fail(self, reason: str) -> None:
        """Never lie: a failed launch says so instead of reaching 100%."""
        self._failed = True
        self._detail = str(reason)
        self.update()

    def finish(self) -> None:
        """Close the card and tell the app it may show the window."""
        self._pulse_timer.stop()
        self._intro.stop()
        self.hide()
        self.finished.emit()

    # --------------------------------------------------------------- drawing
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        card = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        path = QPainterPath()
        path.addRoundedRect(card, 26.0, 26.0)

        # dark glass: violet wash, then a faint top-light so it reads as glass
        painter.setClipPath(path)
        splash_gradient(painter, card)
        top_light = QLinearGradient(
            card.topLeft(), QPointF(card.left(), card.top() + 120)
        )
        top_light.setColorAt(0.0, QColor(255, 255, 255, 26))
        top_light.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(card, top_light)
        painter.setClipping(False)

        pen = QPen(QColor(255, 255, 255, 46), 1.2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # ---- the mark -------------------------------------------------
        mark_size = 150.0
        mark = QRectF(
            card.center().x() - mark_size / 2.0,
            card.top() + 56.0,
            mark_size,
            mark_size,
        )

        # ring, drawn progressively
        inset = mark_size * 0.055
        ring_rect = mark.adjusted(inset, inset, -inset, -inset)
        ring_pen = QPen(QColor(255, 255, 255, int(70 + 40 * self._spark)), 1.6)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(
            ring_rect,
            90 * 16,
            int(-360 * 16 * max(0.02, self._ring)),
        )

        # the N in four bands, sliding in from alternating sides.  The bands
        # must cover the *letter* (TOP..BOTTOM), not the whole canvas, or the
        # bottom of the stems gets clipped away.
        letters_top = mark.top() + mark.height() * TOP
        band_h = mark.height() * (BOTTOM - TOP) / 4.0
        painter.save()
        painter.setClipRect(mark)
        for index in range(4):
            local = max(0.0, min(1.0, (self._bands - index * 0.13) / 0.62))
            if local <= 0.0:
                continue
            ease = 1.0 - (1.0 - local) ** 3
            offset = (1.0 - ease) * mark.width() * (0.55 if index % 2 == 0 else -0.55)
            painter.save()
            painter.translate(offset, 0.0)
            painter.setOpacity(ease)
            painter.setClipRect(
                QRectF(
                    mark.left(),
                    letters_top + band_h * index,
                    mark.width(),
                    band_h + 0.5,
                ),
                Qt.IntersectClip,
            )
            draw_n(painter, mark, BRAND_WHITE)
            painter.restore()

        painter.restore()

        # spark, last
        if self._spark > 0.0:
            spark_size = mark.width() * 0.145 * (0.6 + 0.4 * self._spark)
            spark_rect = QRectF(
                mark.left() + mark.width() * 0.528 - spark_size / 2.0,
                mark.top() + mark.height() * 0.315 - spark_size / 2.0,
                spark_size,
                spark_size,
            )
            painter.save()
            painter.setOpacity(self._spark)
            painter.setPen(Qt.NoPen)
            painter.setBrush(BRAND_WHITE)
            painter.drawPath(spark_path(spark_rect))
            painter.restore()

        # ---- wordmark --------------------------------------------------
        if self._title > 0.0:
            painter.save()
            painter.setOpacity(self._title)
            font = QFont()
            font.setPointSize(26)
            font.setWeight(QFont.Light)
            font.setLetterSpacing(QFont.AbsoluteSpacing, 7.0)
            painter.setFont(font)
            painter.setPen(BRAND_WHITE)
            title_rect = QRectF(card.left(), mark.bottom() + 22.0, card.width(), 40.0)
            painter.drawText(title_rect, Qt.AlignCenter, "NORA")
            painter.restore()

        # ---- progress --------------------------------------------------
        bar = QRectF(
            card.left() + 84.0, card.bottom() - 74.0, card.width() - 168.0, 3.0
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 28))
        painter.drawRoundedRect(bar, 1.5, 1.5)

        # indeterminate shimmer until the first real step lands
        shown = self._progress
        if shown <= 0.001:
            shimmer = 0.12 * (0.5 + 0.5 * self._pulse)
            painter.setBrush(QColor(255, 255, 255, 90))
            width = bar.width() * shimmer
            painter.drawRoundedRect(
                QRectF(bar.left(), bar.top(), max(6.0, width), bar.height()), 1.5, 1.5
            )
        else:
            fill = QColor("#f2a7d0") if not self._failed else QColor("#ff7a8a")
            painter.setBrush(fill)
            painter.drawRoundedRect(
                QRectF(bar.left(), bar.top(), bar.width() * shown, bar.height()),
                1.5,
                1.5,
            )

        # ---- status text ----------------------------------------------
        painter.setPen(QColor(196, 178, 207) if not self._failed else QColor("#ff9aa6"))
        status_font = QFont()
        status_font.setPointSize(10)
        painter.setFont(status_font)
        caption = self._detail or self._status
        painter.drawText(
            QRectF(card.left(), bar.bottom() + 8.0, card.width(), 20.0),
            Qt.AlignCenter,
            caption,
        )

        painter.end()


class LogoEjectAnimation:
    """Animates the character climbing **out of the logo** onto the desktop.

    The pet window itself is the moving object: it starts as a tiny square
    exactly over the header logo, grows to its real size and slides down to its
    resting spot, while the logo badge shows a "she left" ghost.  Nothing here
    touches the physics state, so the character lands in IDLE and behaves.
    """

    def __init__(
        self,
        pet: QWidget,
        start: QPointF,
        end: QPointF,
        parent: QWidget | None = None,
    ) -> None:
        self.pet = pet
        self._animation = QPropertyAnimation(pet, b"geometry", parent)
        self._animation.setDuration(560)
        self._animation.setEasingCurve(QEasingCurve.OutBack)
        self._start = start
        self._end = end

    def run(self) -> None:
        from PyQt5.QtCore import QRect

        pet = self.pet
        start_w = max(18, pet.width() // 7)
        start_h = max(24, pet.height() // 7)
        begin = QRect(
            int(self._start.x()),
            int(self._start.y()),
            start_w,
            start_h,
        )
        finish = QRect(
            int(self._end.x()),
            int(self._end.y()),
            pet.width(),
            pet.height(),
        )
        self._animation.setStartValue(begin)
        self._animation.setEndValue(finish)
        self._animation.start()


__all__ = ["STEPS", "LogoEjectAnimation", "SplashScreen"]

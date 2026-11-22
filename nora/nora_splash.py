"""The opening screen: a **white** card with the aurora N on it.

The splash exists because the model/voice/database warm-up is not instant.  It
is deliberately *not* a fake progress bar — every step it reports is a real step
that finished, and if a step fails the card says so instead of jumping to 100%.

Design decisions
----------------
* **White.** The card is white glass on the white desktop, with ink type.  The
  only colour is the brand gradient in the mark and the progress fill.
* **Five seconds, honestly.** :data:`HOLD_SECONDS` is the minimum time the card
  stays up so the entrance has room to breathe; the real work usually finishes
  sooner and the card waits for the animation rather than flashing away.
* **A real entrance.** The tile draws itself, the N rises out of it, the
  wordmark tracks out and the progress line lights up. All from the mark's own
  geometry — no pre-rendered video, no image files.
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
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt5.QtWidgets import QWidget

from .nora_brand import (
    BRAND_ORCHID,
    BRAND_PINK,
    BRAND_VIOLET,
    INK,
    INK_SOFT,
    draw_mark,
    splash_gradient,
)

#: The steps a launch really goes through.  The app reports progress by index.
STEPS: tuple[str, ...] = (
    "Ayarlar okunuyor",
    "Hafıza hazırlanıyor",
    "Ses ve konuşma yükleniyor",
    "Nora uyanıyor",
)

#: How long the card stays on screen, at minimum, in seconds.
HOLD_SECONDS = 5.0

#: Card geometry.
CARD_SIZE = (580, 540)


class SplashScreen(QWidget):
    """Frameless, translucent launch card on a white canvas."""

    finished = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(*CARD_SIZE)
        self.setWindowTitle("Nora")

        self._intro_value = 0.0
        self._progress = 0.0
        self._status = STEPS[0]
        self._detail = ""
        self._pulse = 0.0
        self._failed = False

        # eased 0..1 sub-animations, derived from one intro value
        self._tile = 0.0
        self._letter = 0.0
        self._word = 0.0
        self._line = 0.0

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(33)
        self._pulse_timer.timeout.connect(self._tick)

        self._intro = QPropertyAnimation(self, b"introProgress", self)
        self._intro.setDuration(1400)
        self._intro.setStartValue(0.0)
        self._intro.setEndValue(1.0)
        self._intro.setEasingCurve(QEasingCurve.OutCubic)

    # ------------------------------------------------------------- animation
    def _get_intro(self) -> float:
        return self._intro_value

    def _set_intro(self, value: float) -> None:
        self._intro_value = float(value)
        # staggered: tile 0.00-0.45, letter 0.20-0.70, word 0.55-0.90, line 0.75-1
        self._tile = min(1.0, self._intro_value / 0.45)
        self._letter = max(0.0, min(1.0, (self._intro_value - 0.20) / 0.50))
        self._word = max(0.0, min(1.0, (self._intro_value - 0.55) / 0.35))
        self._line = max(0.0, min(1.0, (self._intro_value - 0.75) / 0.25))
        self.update()

    introProgress = pyqtProperty(float, fget=_get_intro, fset=_set_intro)

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.045) % 1.0
        self.update()

    def start(self) -> None:
        """Show the card and play the entrance."""
        self._set_intro(0.0)
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
        path.addRoundedRect(card, 30.0, 30.0)
        painter.setClipPath(path)
        splash_gradient(painter, card)

        # a whisper of the product's glass: light from above, shadow below
        top_light = QLinearGradient(card.topLeft(), QPointF(card.left(), card.top() + 150))
        top_light.setColorAt(0.0, QColor(255, 255, 255, 255))
        top_light.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(card, top_light)
        painter.setClipping(False)

        painter.setPen(QPen(QColor(24, 18, 40, 26), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # ---- the mark -------------------------------------------------
        mark_size = 132.0
        mark = QRectF(
            card.center().x() - mark_size / 2.0,
            card.top() + 96.0,
            mark_size,
            mark_size,
        )

        # The tile draws itself left→right, then the N fades up inside it.
        # One draw_mark call per frame: the letter is part of the mark, so a
        # second "reveal" would paint a second N.
        if self._tile > 0.0:
            ease = 1.0 - (1.0 - self._tile) ** 3
            painter.save()
            painter.setClipRect(
                QRectF(mark.left(), mark.top(), mark.width() * ease, mark.height())
            )
            painter.translate(mark.topLeft())
            painter.setOpacity(0.35 + 0.65 * self._letter)
            # glow off: the card is already white, a halo would be invisible
            draw_mark(painter, int(round(mark_size)), spark=False, glow=False)
            painter.restore()


        # ---- wordmark --------------------------------------------------
        if self._word > 0.0:
            painter.save()
            painter.setOpacity(self._word)
            tracking = 10.0 + 6.0 * (1.0 - self._word)
            font = QFont("Segoe UI", 21, QFont.DemiBold)
            font.setLetterSpacing(QFont.AbsoluteSpacing, tracking)
            painter.setFont(font)
            painter.setPen(INK)
            title_rect = QRectF(card.left(), mark.bottom() + 30.0, card.width(), 44.0)
            painter.drawText(title_rect, Qt.AlignCenter, "NORA")

            caption_font = QFont("Segoe UI", 8)
            caption_font.setLetterSpacing(QFont.AbsoluteSpacing, 3.2)
            painter.setFont(caption_font)
            painter.setPen(INK_SOFT)
            painter.drawText(
                QRectF(card.left(), title_rect.bottom() - 2.0, card.width(), 22.0),
                Qt.AlignCenter,
                "MASAÜSTÜ ASİSTANI",
            )
            painter.restore()

        # ---- progress --------------------------------------------------
        bar = QRectF(
            card.left() + 108.0, card.bottom() - 96.0, card.width() - 216.0, 3.0
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(24, 18, 40, 20))
        painter.drawRoundedRect(bar, 1.5, 1.5)

        if self._failed:
            fill = QColor("#ff3b5c")
        else:
            fill = QBrush(self._brand_gradient(bar))
        if self._progress <= 0.001:
            # indeterminate pulse until the first real step lands
            width = bar.width() * 0.18
            travel = bar.width() * (0.9 - 0.18)
            x = bar.left() + travel * self._pulse
            painter.setBrush(QColor(123, 92, 255, 150))
            painter.drawRoundedRect(
                QRectF(x, bar.top(), width, bar.height()), 1.5, 1.5
            )
        else:
            painter.setBrush(fill)
            painter.drawRoundedRect(
                QRectF(bar.left(), bar.top(), bar.width() * self._progress, bar.height()),
                1.5,
                1.5,
            )

        # ---- status text ----------------------------------------------
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor("#ff3b5c") if self._failed else INK_SOFT)
        caption = self._detail or self._status
        painter.drawText(
            QRectF(card.left(), bar.bottom() + 10.0, card.width(), 20.0),
            Qt.AlignCenter,
            caption,
        )

        # a quiet brand bloom at the bottom edge, so the white card has depth
        bloom = QRadialGradient(
            QPointF(card.center().x(), card.bottom()), card.width() * 0.55
        )
        bloom.setColorAt(0.0, QColor(123, 92, 255, 20))
        bloom.setColorAt(1.0, QColor(123, 92, 255, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bloom))
        painter.drawEllipse(
            QPointF(card.center().x(), card.bottom()), card.width() * 0.55, 70.0
        )

        painter.end()

    @staticmethod
    def _brand_gradient(rect: QRectF) -> QLinearGradient:
        grad = QLinearGradient(rect.topLeft(), rect.topRight())
        grad.setColorAt(0.0, BRAND_VIOLET)
        grad.setColorAt(0.5, BRAND_ORCHID)
        grad.setColorAt(1.0, BRAND_PINK)
        return grad


__all__ = ["HOLD_SECONDS", "STEPS", "SplashScreen"]

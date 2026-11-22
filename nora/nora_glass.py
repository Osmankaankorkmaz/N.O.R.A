"""Frosted-glass ("glassmorphism") chat surfaces for Nora.

The chat panel follows the modern desktop-assistant look: a translucent blurred
card floating over the desktop, rounded corners, hairline highlight on the top
edge, soft outer shadow and message bubbles that mix translucent fills with a
subtle gradient.

True desktop blur is not available on every platform/Qt build, so the module
degrades in three honest steps:

1. ``AcrylicBackdrop``: real OS blur-behind (Windows 7+/10/11 DWM), used when it
   is available and enabled by the user.
2. ``FrostedPanel``: paints a blurred snapshot of the screen area underneath the
   window, which looks like real glass on every platform that can grab the
   screen.
3. Plain translucent gradient: no screen capture, just a semi-transparent card.

Nothing here captures screen pixels unless the panel is shown, and the captured
pixmap stays in memory only — it is never written to disk or sent anywhere.
"""

from __future__ import annotations

import math
from typing import Any

from PyQt5.QtCore import (
    QEasingCurve,
    pyqtSignal,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Palette: cool violet-tinted glass with a warm accent, mirroring the avatar.
GLASS_TINT = QColor(28, 22, 38, 168)
GLASS_TINT_LIGHT = QColor(46, 36, 60, 150)
HAIRLINE = QColor(255, 255, 255, 46)
ACCENT = QColor("#c78bb8")
ACCENT_BRIGHT = QColor("#f2a7d0")
TEXT = QColor("#f4ecf7")
TEXT_DIM = QColor("#c4b2cf")

STYLE = f"""
QWidget#glassRoot {{ background: transparent; }}
QFrame#glassCard {{
    background: transparent;
}}
QLabel {{ color: {TEXT.name()}; background: transparent; }}
QLabel#title {{ color: #ffffff; font-size: 15px; font-weight: 600; letter-spacing: 0.4px; }}
QLabel#subtitle {{ color: {TEXT_DIM.name()}; font-size: 11px; }}
QLabel#status {{ color: {TEXT_DIM.name()}; font-size: 11px; }}
QPushButton {{
    background: rgba(255,255,255,18);
    color: #f3e8f6;
    border: 1px solid rgba(255,255,255,34);
    border-radius: 11px;
    padding: 5px 9px;
    font-size: 12px;
}}
QPushButton:hover {{ background: rgba(255,255,255,38); border-color: rgba(255,255,255,74); }}
QPushButton:pressed {{ background: rgba(199,139,184,120); }}
QPushButton:disabled {{ color: rgba(220,205,225,110); background: rgba(255,255,255,10); }}
QPushButton#sendButton {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #c78bb8, stop:1 #8a6fc4);
    border: none; border-radius: 14px; color: white; font-size: 15px;
}}
QPushButton#sendButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #e2a3cd, stop:1 #a086e0); }}
QLineEdit {{
    background: rgba(255,255,255,22);
    color: #ffffff;
    border: 1px solid rgba(255,255,255,40);
    border-radius: 16px;
    padding: 9px 13px;
    font-size: 13px;
    selection-background-color: rgba(199,139,184,140);
}}
QLineEdit:focus {{ border: 1px solid rgba(242,167,208,190); background: rgba(255,255,255,30); }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 7px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,54); border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,90); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QToolTip {{ color: white; background: #2c2238; border: 1px solid rgba(255,255,255,60); padding: 4px; border-radius: 6px; }}
"""


def desktop_blur_supported() -> bool:
    """True when this Qt/OS build can ask the compositor to blur behind us."""
    if QGuiApplication.platformName().lower() not in {
        "windows",
        "cocoa",
        "wayland",
        "xcb",
    }:
        return False
    # Wayland/xcb have no portable blur hint in Qt5, so only Windows is claimed.
    import sys

    return sys.platform == "win32"


def enable_windows_blur(widget: QWidget, *, dark: bool = True) -> bool:
    """Ask DWM for acrylic/blur-behind. Best effort; never raises."""
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(widget.winId())
        accent_state = 4 if dark else 3
        class_name = ctypes.c_int(19)  # ACCENT_ENABLE_ACRYLICBLURBEHIND

        class AccentPolicy(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_int),
            ]

        class WindowCompositionAttributeData(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t),
            ]

        policy = AccentPolicy()
        policy.AccentState = class_name.value
        policy.AccentFlags = 2
        policy.GradientColor = 0x281A0F1C if dark else 0x28F0EEF6
        data = WindowCompositionAttributeData()
        data.Attribute = 19
        data.Data = ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(policy)
        user32 = ctypes.windll.user32
        user32.SetWindowCompositionAttribute(wintypes.HWND(hwnd), ctypes.byref(data))
        del accent_state
        return True
    except Exception:
        return False


class FrostedPanel(QWidget):
    """Paints a translucent card, optionally over a blurred screen snapshot."""

    def __init__(self, parent: QWidget | None = None, *, radius: int = 22) -> None:
        super().__init__(parent)
        self.radius = radius
        self._backdrop: QPixmap | None = None
        self._backdrop_enabled = True
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)

    # -- backdrop ---------------------------------------------------------
    def set_backdrop_enabled(self, enabled: bool) -> None:
        self._backdrop_enabled = bool(enabled)
        if not self._backdrop_enabled:
            self._backdrop = None
        self.update()

    def backdrop_enabled(self) -> bool:
        return self._backdrop_enabled

    def refresh_backdrop(self) -> None:
        """Grab the screen under this widget and blur it (best effort)."""
        if not self._backdrop_enabled:
            return
        window = self.window()
        screen = QGuiApplication.screenAt(window.geometry().center())
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        try:
            shot = screen.grabWindow(
                0,
                window.x(),
                window.y(),
                max(1, window.width()),
                max(1, window.height()),
            )
        except Exception:
            return
        if shot.isNull():
            return
        # Downscale → upscale is a cheap, dependency-free blur approximation.
        small = shot.scaled(
            max(1, shot.width() // 14),
            max(1, shot.height() // 14),
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )
        self._backdrop = small.scaled(
            self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation
        )
        self.update()

    def clear_backdrop(self) -> None:
        self._backdrop = None
        self.update()

    # -- painting ---------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        painter.setClipPath(path)

        if self._backdrop is not None and not self._backdrop.isNull():
            painter.setOpacity(0.55)
            painter.drawPixmap(self.rect(), self._backdrop)
            painter.setOpacity(1.0)

        tint = QLinearGradient(rect.topLeft(), rect.bottomRight())
        tint.setColorAt(0.0, QColor(58, 46, 74, 150))
        tint.setColorAt(0.55, QColor(34, 27, 46, 168))
        tint.setColorAt(1.0, QColor(24, 19, 33, 182))
        painter.fillPath(path, QBrush(tint))

        # top-left specular sheen
        sheen = QRadialGradient(
            QPointF(rect.left() + rect.width() * 0.24, rect.top()),
            rect.width() * 0.9,
        )
        sheen.setColorAt(0.0, QColor(255, 255, 255, 52))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(path, QBrush(sheen))

        painter.setClipping(False)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(HAIRLINE, 1.2))
        painter.drawPath(path)
        # brighter hairline along the top edge
        top = QPainterPath()
        top.moveTo(rect.left() + self.radius * 0.4, rect.top() + 1)
        top.lineTo(rect.right() - self.radius * 0.4, rect.top() + 1)
        painter.setPen(QPen(QColor(255, 255, 255, 88), 1.4))
        painter.drawPath(top)


#: Message bubbles stay readable on wide windows without turning into
#: edge-to-edge text: ~62% of the 760 px panel, capped for very large windows.
BUBBLE_LABEL_MAX = 560
BUBBLE_MAX = 592


class GlassBubble(QFrame):
    """One chat message in a translucent bubble.

    The sender name is painted rather than added as a second ``QLabel`` so the
    bubble contains exactly one child label (the message body) — that keeps
    ``findChild(QLabel)`` and the accessibility tree unambiguous.
    """

    def __init__(self, text: str, sender: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sender = "user" if sender == "user" else "bot"
        self.sender_name = "Sen" if self.sender == "user" else "Nora"
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 21, 14, 10)
        layout.setSpacing(0)
        label = QLabel(str(text))
        label.setWordWrap(True)
        label.setMaximumWidth(BUBBLE_LABEL_MAX)
        label.setTextFormat(Qt.PlainText)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet("color: #f6effa; background: transparent; font-size: 13px;")
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout.addWidget(label)
        self.label = label
        self.setMaximumWidth(BUBBLE_MAX)
        # QLabel's wrapped size hint collapses to a narrow column; give the
        # bubble a sensible preferred width derived from the actual text.
        metrics = label.fontMetrics()
        ideal = metrics.boundingRect(str(text)).width() + 30
        self.setMinimumWidth(max(96, min(BUBBLE_LABEL_MAX, ideal)))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -0.6)
        path = QPainterPath()
        radius = 16.0
        path.addRoundedRect(rect, radius, radius)
        if self.sender == "user":
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, QColor(199, 139, 184, 205))
            grad.setColorAt(1.0, QColor(138, 111, 196, 195))
            painter.setPen(QPen(QColor(255, 255, 255, 66), 1.0))
            name_color = QColor(255, 242, 250, 220)
        else:
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, QColor(58, 46, 74, 196))
            grad.setColorAt(1.0, QColor(38, 30, 52, 188))
            painter.setPen(QPen(QColor(255, 255, 255, 40), 1.0))
            name_color = QColor(245, 184, 214, 225)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)
        painter.setPen(name_color)
        painter.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
        painter.drawText(
            QRectF(14, 5, rect.width() - 28, 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            self.sender_name,
        )


class TypingIndicator(QWidget):
    """Three glass dots that pulse while Nora is generating a reply."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(64, 28)
        self._phase = 0
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._step)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _step(self) -> None:
        self._phase = (self._phase + 1) % 12
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for index in range(3):
            wave = math.sin((self._phase - index * 2) / 12.0 * math.tau)
            alpha = int(90 + 110 * max(0.0, wave))
            radius = 3.4 + max(0.0, wave) * 1.2
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(240, 200, 230, alpha))
            painter.drawEllipse(
                QPointF(16 + index * 16, 14 - max(0.0, wave) * 2), radius, radius
            )


class GlassChatWindow(QWidget):
    """Frameless, draggable glass card that hosts the conversation."""

    def __init__(self, host: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.host = host
        self._drag_offset: QPoint | None = None
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Nora · Sohbet")
        self.setObjectName("glassRoot")
        self.setStyleSheet(STYLE)
        self.setMinimumSize(380, 500)
        self.resize(420, 620)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        self.panel = FrostedPanel(self)
        self.panel.setObjectName("glassCard")
        shadow = _shadow_effect(self.panel)
        shadow.setBlurRadius(42)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(8, 4, 14, 170))
        if shadow is not None:
            self.panel.setGraphicsEffect(shadow)
        outer.addWidget(self.panel)

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        self._build_header(layout)
        self._build_messages(layout)
        self._build_composer(layout)
        self._build_quick_row(layout)
        self._blur_timer = QTimer(self)
        self._blur_timer.setSingleShot(True)
        self._blur_timer.setInterval(180)
        self._blur_timer.timeout.connect(self.panel.refresh_backdrop)

    # ---- construction ---------------------------------------------------
    def _build_header(self, layout: QVBoxLayout) -> None:
        header = QWidget()
        header.setFixedHeight(40)
        header.setCursor(Qt.SizeAllCursor)
        header.installEventFilter(self)
        self.header = header
        row = QHBoxLayout(header)
        row.setContentsMargins(2, 0, 0, 0)
        row.setSpacing(8)

        avatar = AvatarDot(self)
        avatar.setFixedSize(26, 26)
        self.avatar = avatar
        row.addWidget(avatar)

        titles = QVBoxLayout()
        titles.setContentsMargins(0, 0, 0, 0)
        titles.setSpacing(0)
        title = QLabel("Nora")
        title.setObjectName("title")
        subtitle = QLabel("Yerel companion · çevrimiçi")
        subtitle.setObjectName("subtitle")
        self.subtitle = subtitle
        titles.addWidget(title)
        titles.addWidget(subtitle)
        row.addLayout(titles)
        row.addStretch(1)

        for text, tip, name in (
            ("📸", "Ekran görüntüsü al ve analiz et", "screenButton"),
            ("🎤", "Sesli komut ver", "micButton"),
            ("⚙", "Ayarlar", "settingsButton"),
            ("─", "Sohbeti gizle", "minimizeButton"),
        ):
            button = QPushButton(text)
            button.setObjectName(name)
            button.setToolTip(tip)
            button.setAccessibleName(tip)
            button.setFixedSize(28, 28)
            row.addWidget(button)
            setattr(self, f"_{name}", button)
        layout.addWidget(header)

    def _build_messages(self, layout: QVBoxLayout) -> None:
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("background: transparent;")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self.message_layout = QVBoxLayout(content)
        self.message_layout.setContentsMargins(2, 6, 2, 6)
        self.message_layout.setSpacing(9)
        self.message_layout.addStretch(1)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)

        self.typing = TypingIndicator()
        self.typing.hide()
        layout.addWidget(self.typing)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        self.status_label.setFixedHeight(16)
        layout.addWidget(self.status_label)

    def _build_composer(self, layout: QVBoxLayout) -> None:
        from PyQt5.QtWidgets import QLineEdit

        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("Nora'ya bir şey yaz…")
        self.input.setMaxLength(4000)
        row.addWidget(self.input, 1)
        self.cancel_button = QPushButton("⏹")
        self.cancel_button.setFixedSize(34, 34)
        self.cancel_button.setToolTip("İsteği iptal et")
        self.cancel_button.hide()
        row.addWidget(self.cancel_button)
        self.send_button = QPushButton("➤")
        self.send_button.setObjectName("sendButton")
        self.send_button.setFixedSize(40, 34)
        self.send_button.setToolTip("Gönder (Enter)")
        row.addWidget(self.send_button)
        layout.addLayout(row)

    def _build_quick_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)
        self.quick_buttons: list[QPushButton] = []
        for text in ("🔍 Ara", "⏰ Saat", "📝 Notlar", "🌤️ Hava", "🎮 Oyun"):
            button = QPushButton(text)
            button.setStyleSheet("font-size: 11px; padding: 4px 6px;")
            row.addWidget(button)
            self.quick_buttons.append(button)
        layout.addLayout(row)

    # ---- behaviour ------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        if enable_windows_blur(self):
            self.panel.set_backdrop_enabled(False)
        self._blur_timer.start()
        self.fade_in()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.panel.clear_backdrop()
        super().hideEvent(event)

    def moveEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().moveEvent(event)
        self._blur_timer.start()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._blur_timer.start()

    def fade_in(self) -> None:
        self.setWindowOpacity(0.0)
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(170)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start(QPropertyAnimation.DeleteWhenStopped)
        self._fade = animation

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        from PyQt5.QtCore import QEvent

        if obj is self.header:
            if (
                event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton
            ):
                self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
                return True
            if event.type() == QEvent.MouseMove and self._drag_offset is not None:
                self.move(event.globalPos() - self._drag_offset)
                return True
            if event.type() == QEvent.MouseButtonRelease:
                self._drag_offset = None
                self.host._chat_user_moved = True
                return True
        return super().eventFilter(obj, event)

    def set_busy(
        self, busy: bool, status: str = "", *, cancellable: bool = False
    ) -> None:
        self.status_label.setText(status)
        self.typing.setVisible(bool(busy))
        if busy:
            self.typing.start()
        else:
            self.typing.stop()
        self.cancel_button.setVisible(bool(busy and cancellable))

    def add_bubble(self, text: str, sender: str) -> GlassBubble:
        bubble = GlassBubble(text, sender)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if sender == "user":
            row.addStretch(1)
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        holder.setStyleSheet("background: transparent;")
        self.message_layout.insertWidget(self.message_layout.count() - 1, holder)
        return bubble

    def clear_messages(self) -> None:
        while self.message_layout.count() > 1:
            item = self.message_layout.takeAt(0)
            widget = item.widget() if item else None
            if widget is not None:
                widget.deleteLater()

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)


class AvatarDot(QWidget):
    """Tiny circular avatar preview in the header (uses the real renderer)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None

    def set_appearance(self, appearance: dict | None, emotion: str = "idle") -> None:
        """Show the same character the desktop pet uses, cropped to the face."""
        self._pixmap = None
        try:
            from .nora_sprite import SpriteAssets, SpriteCharacter

            assets = SpriteAssets()
            if assets.usable:
                # illustrated sheets first: one character, one art style
                image = SpriteCharacter(assets.library).portrait(128, emotion)
            else:
                from .nora_body import FullBodyCharacter

                image = FullBodyCharacter().portrait(
                    128, appearance=appearance or {}, crop="face"
                )
            self._pixmap = QPixmap.fromImage(image)
        except Exception:
            self._pixmap = None
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        circle = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addEllipse(circle)
        painter.setClipPath(path)
        if self._pixmap is not None and not self._pixmap.isNull():
            painter.drawPixmap(self.rect(), self._pixmap)
        else:
            grad = QLinearGradient(circle.topLeft(), circle.bottomRight())
            grad.setColorAt(0.0, QColor("#c78bb8"))
            grad.setColorAt(1.0, QColor("#7c4dff"))
            painter.fillPath(path, QBrush(grad))
        painter.setClipping(False)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 90), 1.2))
        painter.drawEllipse(circle)


def _shadow_effect(widget: QWidget) -> QGraphicsDropShadowEffect | None:
    """Drop shadow only where the platform honours it (offscreen crashes)."""
    if QGuiApplication.platformName().lower() in {"offscreen", "minimal"}:
        return None
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(42)
    effect.setOffset(0, 10)
    effect.setColor(QColor(8, 4, 14, 170))
    return effect


def glass_style() -> str:
    return STYLE


class PetLogoButton(QWidget):
    """Nora's brand logo (the white **N**) in the chat header.

    The mark *is* the character's door: pressing it plays the "she climbs out
    of the logo" animation and drops her onto the desktop; pressing it again
    pulls her back in.  Drawn from :mod:`nora.nora_brand`, never from a file, so
    it stays crisp at any size and can be repainted on a light or dark card.
    """

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, size: int = 46) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Nora'yı masaüstüne indir")
        self._released = False
        self._hover = False
        self._pulse = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------- behaviour
    def set_released(self, released: bool) -> None:
        self._released = bool(released)
        self.update()

    @property
    def released(self) -> bool:
        return self._released

    def _tick(self) -> None:
        self._pulse = (self._pulse + 0.12) % 1.0
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    # --------------------------------------------------------------- drawing
    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        from .nora_brand import draw_mark

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        box = min(rect.width(), rect.height())

        # A brand tile, not a character badge.  The mark is pure white, so it
        # needs a dark plate to sit on: on a white fill it vanished into the
        # glass.  Hover lifts the plate, "she is outside" tints it pink.
        fill = QColor(24, 18, 34, 220 if not self._hover else 240)
        if self._released:
            fill = QColor(78, 38, 62, 235)
        painter.setBrush(fill)
        border = QColor(255, 255, 255, 64 if self._hover else 34)
        if self._released:
            border = QColor(255, 190, 225, 170)
        painter.setPen(QPen(border, 1.1))
        radius = box * 0.30
        painter.drawRoundedRect(rect, radius, radius)

        if self._released:
            glow = QColor(255, 190, 225, int(70 * (1.0 - self._pulse)))
            painter.setPen(QPen(glow, 2.0))
            grow = 2.5 * self._pulse
            painter.drawRoundedRect(
                rect.adjusted(-grow, -grow, grow, grow), radius + grow, radius + grow
            )

        mark = box * 0.60
        painter.translate(
            rect.center().x() - mark / 2.0,
            rect.center().y() - mark / 2.0,
        )
        draw_mark(
            painter,
            int(round(mark)),
            ring=False,
            spark=False,
            color=QColor(255, 255, 255, 255 if self._hover else 236),
        )
        painter.end()

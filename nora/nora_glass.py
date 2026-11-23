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
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QAbstractButton,
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

from .nora_brand import CARD_RADIUS

# ---------------------------------------------------------------------------
# Design tokens.  One place for colour, type and rhythm so no widget invents
# its own numbers and the whole app stays on the same grid.
# ---------------------------------------------------------------------------

#: Ink, not black: a warm violet-black reads as depth on white.
TEXT = QColor("#181423")
TEXT_DIM = QColor("#6e6a80")
TEXT_FAINT = QColor("#9a95a8")

ACCENT = QColor("#7b5cff")
ACCENT_MID = QColor("#b45cf5")
ACCENT_BRIGHT = QColor("#ff4d94")

#: Surfaces, from the page up to the floating cards.
PAGE_TOP = QColor("#fbfaff")
PAGE_BOTTOM = QColor("#f6f4fd")
SURFACE = QColor(255, 255, 255, 236)
SURFACE_SOLID = QColor("#ffffff")
HAIRLINE = QColor(24, 18, 40, 16)
HAIRLINE_STRONG = QColor(24, 18, 40, 26)


def css(color: QColor) -> str:
    """A QColor as CSS, *including* its alpha.

    ``QColor.name()`` silently drops the alpha channel, so ``rgba(24,18,40,34)``
    becomes ``#181428`` — an almost-black hairline instead of a whisper of one.
    Every translucent colour in the stylesheet goes through here.
    """
    if color.alpha() == 255:
        return color.name()
    return (
        f"rgba({color.red()},{color.green()},{color.blue()},{color.alpha() / 255:.3f})"
    )


def gradient_brush(box: QRectF, *, vertical: bool = False) -> QBrush:
    """The brand ink: violet → orchid → pink across ``box``.

    One gradient for every glyph in the app, so an icon, the send button and
    the active rail pill all read as the same material.
    """
    if vertical:
        grad = QLinearGradient(box.topLeft(), box.bottomLeft())
    else:
        grad = QLinearGradient(box.topLeft(), box.bottomRight())
    grad.setColorAt(0.0, QColor(ACCENT))
    grad.setColorAt(0.55, QColor(ACCENT_MID))
    grad.setColorAt(1.0, QColor(ACCENT_BRIGHT))
    return QBrush(grad)


def brand_icon_pixmap(kind: str, size: int, *, dpr: float = 1.0) -> QPixmap:
    """A hand-drawn brand-glyph icon: gradient ink, no background.

    Used where a widget cannot paint itself (the send button, which is a plain
    ``QPushButton``).  Drawn at ``dpr`` scale so it stays sharp on scaled
    displays.
    """
    from .nora_glyphs import draw_glyph

    px = max(1, int(round(size * dpr)))
    image = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    box = QRectF(0, 0, px, px).adjusted(px * 0.18, px * 0.18, -px * 0.18, -px * 0.18)
    ink = gradient_brush(box)
    painter.setPen(QPen(ink, max(1.4, px * 0.055)))
    # The plane reads as a solid object; the outline glyphs must not be filled.
    painter.setBrush(ink if kind == "send" else Qt.NoBrush)
    draw_glyph(painter, kind, box)
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


#: Kept for callers that still name the glass tint.
GLASS_TINT = SURFACE
GLASS_TINT_LIGHT = QColor(252, 250, 255, 232)

#: The rhythm.  Every gap in the app is one of these.
GAP_XS = 4
GAP_SM = 8
GAP_MD = 12
GAP_LG = 18
GAP_XL = 26

#: Radii: pills for actions, cards for surfaces.
RADIUS_PILL = 999
RADIUS_CARD = 18
RADIUS_INPUT = 22
RADIUS_BUBBLE = 20

STYLE = f"""
QWidget#glassRoot {{ background: transparent; }}
QWidget#whitePage {{ background: #ffffff; }}
QFrame#glassCard {{ background: transparent; }}
QWidget#chatHeader {{ background: transparent; }}
QWidget#stage {{ background: transparent; }}
QWidget#stageBody {{ background: transparent; }}
QWidget#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255,255,255,214), stop:1 rgba(250,247,255,168));
    border-right: 1px solid rgba(24,18,40,22);
}}
QLabel#wordmark {{ color: {TEXT.name()}; font-size: 17px; font-weight: 700; letter-spacing: -0.2px; }}
QLabel#railCaption {{ color: {TEXT_FAINT.name()}; font-size: 9px; font-weight: 600; letter-spacing: 1.1px; }}
QFrame#railDivider {{ background: {css(HAIRLINE)}; border: none; max-height: 1px; }}
QWidget#heroCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(255,255,255,244), stop:1 rgba(252,248,255,238));
    border: 1px solid {css(HAIRLINE)};
    border-radius: 28px;
}}
QLabel#navCaption {{ color: {TEXT_FAINT.name()}; font-size: 9px; letter-spacing: 0.6px; }}
QWidget#composerCard {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255,255,255,246), stop:1 rgba(250,248,255,240));
    border: 1px solid {css(HAIRLINE)};
    border-radius: {RADIUS_INPUT + 4}px;
}}

QLabel {{ color: {TEXT.name()}; background: transparent; }}
QLabel#title {{ color: {TEXT.name()}; font-size: 16px; font-weight: 600; letter-spacing: 0.2px; }}
QLabel#subtitle {{ color: {TEXT_DIM.name()}; font-size: 11px; letter-spacing: 0.3px; }}
QLabel#status {{ color: {TEXT_DIM.name()}; font-size: 11px; }}
QLabel#heroTitle {{ color: {TEXT.name()}; font-size: 34px; font-weight: 700; letter-spacing: -0.7px; }}
QLabel#heroBody {{ color: {TEXT_DIM.name()}; font-size: 13.5px; }}
QLabel#heroCaption {{ color: {TEXT_FAINT.name()}; font-size: 11px; font-weight: 600; letter-spacing: 0.4px; }}

QPushButton {{
    background: rgba(24,18,40,7);
    color: {TEXT.name()};
    border: 1px solid {css(HAIRLINE)};
    border-radius: 13px;
    padding: 6px 12px;
    font-size: 12px;
}}
QPushButton:hover {{ background: rgba(123,92,255,20); border-color: rgba(123,92,255,110); }}
QPushButton:pressed {{ background: rgba(123,92,255,44); }}
QPushButton:disabled {{ color: {TEXT_FAINT.name()}; background: rgba(24,18,40,5); border-color: rgba(24,18,40,12); }}

/* The send action is a gradient glyph, not a filled disc: the disc was the
   loudest object in the composer and competed with the bubbles. */
QPushButton#sendGlyph {{
    background: transparent;
    border: none;
    border-radius: 21px;
}}
QPushButton#sendGlyph:hover {{ background: rgba(123,92,255,26); }}
QPushButton#sendGlyph:pressed {{ background: rgba(123,92,255,52); }}
QPushButton#sendGlyph:disabled {{ background: transparent; }}

QPushButton#chip {{
    background: {SURFACE_SOLID.name()};
    border: 1px solid {css(HAIRLINE_STRONG)};
    border-radius: 17px;
    padding: 7px 14px;
    font-size: 12px;
    color: {TEXT.name()};
}}
QPushButton#chip:hover {{
    background: rgba(123,92,255,16);
    border-color: rgba(123,92,255,130);
    color: {ACCENT.name()};
}}

QPushButton#cancelButton {{
    background: rgba(255,77,148,18);
    border: 1px solid rgba(255,77,148,90);
    border-radius: 20px;
    color: {ACCENT_BRIGHT.name()};
    font-size: 12px;
}}

QLineEdit {{
    background: transparent;
    color: {TEXT.name()};
    border: none;
    padding: 10px 4px;
    font-size: 13.5px;
    selection-background-color: rgba(123,92,255,90);
}}
QLineEdit:focus {{ border: none; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{
    background: rgba(24,18,40,38);
    border-radius: 4px;
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{ background: rgba(24,18,40,80); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QToolTip {{
    color: {TEXT.name()};
    background: #ffffff;
    border: 1px solid rgba(24,18,40,38);
    padding: 5px 8px;
    border-radius: 8px;
}}
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

    def __init__(
        self, parent: QWidget | None = None, *, radius: float = CARD_RADIUS
    ) -> None:
        super().__init__(parent)
        #: One radius for the whole product: the launch card and the window that
        #: replaces it must have visibly identical corners.
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
        # Full-bleed rect, exactly like the launch card: the card paints its
        # rounded rect from (0, 0) with the full radius, so anything inset here
        # would make the window's corners visibly tighter than the card's.
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)

        # This widget is the window, so it cannot be "translucent over a page":
        # WA_NoSystemBackground leaves the buffer it inherits, which the page has
        # already filled square, and the corners would stay square.  Erase to
        # transparent and paint the card as one opaque shape instead.
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setClipPath(path)

        if self._backdrop is not None and not self._backdrop.isNull():
            painter.setOpacity(0.55)
            painter.drawPixmap(self.rect(), self._backdrop)
            painter.setOpacity(1.0)

        # White glass: opaque enough to read type on, soft enough to feel like
        # a card floating over the desktop.
        tint = QLinearGradient(rect.topLeft(), rect.bottomRight())
        tint.setColorAt(0.0, QColor(255, 255, 255, 255))
        tint.setColorAt(0.55, QColor(252, 250, 255, 252))
        tint.setColorAt(1.0, QColor(247, 244, 253, 249))
        painter.fillPath(path, QBrush(tint))

        # a barely-there brand bloom in the top-left corner
        sheen = QRadialGradient(
            QPointF(rect.left() + rect.width() * 0.18, rect.top()),
            rect.width() * 0.85,
        )
        sheen.setColorAt(0.0, QColor(123, 92, 255, 26))
        sheen.setColorAt(0.55, QColor(255, 77, 148, 10))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(path, QBrush(sheen))

        painter.setClipping(False)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(24, 18, 40, 30), 1.2))
        painter.drawPath(path)
        # crisp white highlight along the top edge, the classic glass cue
        top = QPainterPath()
        top.moveTo(rect.left() + self.radius * 0.4, rect.top() + 1)
        top.lineTo(rect.right() - self.radius * 0.4, rect.top() + 1)
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.4))
        painter.drawPath(top)


#: Message bubbles stay readable on wide windows without turning into
#: edge-to-edge text: ~62% of the 760 px panel, capped for very large windows.
BUBBLE_LABEL_MAX = 560
BUBBLE_MAX = 592


class GlassBubble(QFrame):
    """One chat message.

    Nora's replies are white cards with a soft shadow-free hairline; the user's
    own words are the brand gradient.  Both get a small tail on the side they
    belong to, so the reading direction is obvious at a glance without needing
    avatars on every row.

    The sender name is painted rather than added as a second ``QLabel`` so the
    bubble contains exactly one child label (the message body) — that keeps
    ``findChild(QLabel)`` and the accessibility tree unambiguous.
    """

    #: Room reserved above the text for the painted sender name.
    NAME_BAND = 20

    def __init__(self, text: str, sender: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Normalise *before* any subclass logic runs: NoraApp's ChatBubble reads
        # self.sender while the base is still initialising.
        self.sender = "user" if str(sender).lower() == "user" else "bot"
        self.sender_name = "Sen" if self.sender == "user" else "Nora"
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12 + self.NAME_BAND, 16, 12)
        layout.setSpacing(0)
        label = QLabel(str(text))
        label.setWordWrap(True)
        label.setMaximumWidth(BUBBLE_LABEL_MAX)
        label.setTextFormat(Qt.PlainText)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ink = "#ffffff" if self.sender == "user" else TEXT.name()
        # No line-height: Qt's stylesheet engine does not implement it, and a
        # declaration it drops can take neighbouring ones with it.
        label.setStyleSheet(f"color: {ink}; background: transparent; font-size: 13px;")
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout.addWidget(label)
        self.label = label
        self.setMaximumWidth(BUBBLE_MAX)
        # QLabel's wrapped size hint collapses to a narrow column; give the
        # bubble a sensible preferred width derived from the actual text.
        metrics = label.fontMetrics()
        ideal = metrics.boundingRect(str(text)).width() + 34
        self.setMinimumWidth(max(110, min(BUBBLE_MAX, ideal)))

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -0.6)

        # A squared-off corner on the side the tail grows from is what makes a
        # bubble read as speech rather than as a floating card.
        radius = RADIUS_BUBBLE
        tail = 7.0
        path = self._bubble_path(rect, radius, tail)

        if self.sender == "user":
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, QColor("#7d5eff"))
            grad.setColorAt(1.0, QColor("#ff4d94"))
            painter.setPen(QPen(QColor(255, 255, 255, 66), 1.0))
            name_color = QColor(255, 255, 255, 230)
        else:
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0.0, QColor(255, 255, 255, 252))
            grad.setColorAt(1.0, QColor(250, 247, 255, 248))
            painter.setPen(QPen(QColor(24, 18, 40, 24), 1.0))
            name_color = QColor(ACCENT)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)

        painter.setPen(name_color)
        painter.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
        painter.drawText(
            QRectF(16, 6, rect.width() - 32, self.NAME_BAND),
            Qt.AlignLeft | Qt.AlignVCenter,
            self.sender_name,
        )

    def _bubble_path(self, rect: QRectF, radius: float, tail: float) -> QPainterPath:
        """A rounded rect with one corner pulled towards the speaker's side."""
        path = QPainterPath()
        big = radius
        small = 6.0
        if self.sender == "user":
            corners = (
                big,
                big,
                small,
                big,
            )  # top-left, top-right, bottom-right, bottom-left
        else:
            corners = (big, big, big, small)
        tl, tr, br, bl = (
            corners[0],
            corners[1],
            corners[2] + (tail if self.sender == "user" else 0.0),
            corners[3] + (tail if self.sender != "user" else 0.0),
        )
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        path.moveTo(x + tl, y)
        path.lineTo(x + w - tr, y)
        path.quadTo(x + w, y, x + w, y + tr)
        path.lineTo(x + w, y + h - br)
        path.quadTo(x + w, y + h, x + w - br, y + h)
        path.lineTo(x + bl, y + h)
        path.quadTo(x, y + h, x, y + h - bl)
        path.lineTo(x, y + tl)
        path.quadTo(x, y, x + tl, y)
        path.closeSubpath()
        return path


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
            painter.setBrush(QColor(123, 92, 255, alpha))
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
        shadow.setColor(QColor(60, 40, 110, 70))
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
            grad.setColorAt(0.0, QColor("#7b5cff"))
            grad.setColorAt(1.0, QColor("#ff4d94"))
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


class GradientWindowButton(QPushButton):
    """A frameless window control: a gradient glyph, no panel behind it.

    The window is frameless, so these are the only minimise / maximise / close
    controls it has.  They are drawn, not typed: an emoji would be multicoloured
    and a text glyph would be a font run at the wrong weight.

    The button paints **no background at all** — the glyph carries the brand and
    the row stays quiet on the white page.  Hover adds a soft tinted disc so the
    hit target is still obvious; close tilts one step further into pink.
    """

    GLYPHS = ("minimize", "maximize", "restore", "close")

    def __init__(
        self,
        glyph: str,
        parent: QWidget | None = None,
        *,
        size: int = 30,
        danger: bool = False,
    ) -> None:
        super().__init__(parent)
        if glyph not in self.GLYPHS:
            raise ValueError(f"bilinmeyen düğme simgesi: {glyph}")
        self.glyph = glyph
        self.danger = danger
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFlat(True)
        # Without these Qt paints an opaque buffer under the button and every
        # pixel the glyph does not cover turns black (seen on Windows).
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self._hover = False

    # -- painting ---------------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        if self._hover:
            # A tinted disc only on hover: the resting state is pure glyph.
            painter.setPen(Qt.NoPen)
            painter.setBrush(
                QColor(255, 77, 148, 40) if self.danger else QColor(123, 92, 255, 30)
            )
            painter.drawEllipse(box)

        # The ink: the brand gradient, or the pink end of it for close.
        if self.danger:
            ink = QBrush(QColor("#ff2d78"))
        else:
            ink = gradient_brush(box)
        width = 1.7 if self.glyph != "close" else 1.9
        painter.setPen(QPen(ink, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)

        cx, cy = box.center().x(), box.center().y()
        arm = box.width() * 0.19
        if self.glyph == "minimize":
            painter.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
        elif self.glyph == "maximize":
            painter.drawRoundedRect(
                QRectF(cx - arm, cy - arm, arm * 2, arm * 2), 2.0, 2.0
            )
        elif self.glyph == "restore":
            painter.drawRoundedRect(
                QRectF(cx - arm + 1.6, cy - arm - 1.6, arm * 2 - 1, arm * 2 - 1),
                1.8,
                1.8,
            )
            painter.drawRoundedRect(
                QRectF(cx - arm - 1.6, cy - arm + 1.6, arm * 2 - 1, arm * 2 - 1),
                1.8,
                1.8,
            )
        else:  # close
            painter.drawLine(QPointF(cx - arm, cy - arm), QPointF(cx + arm, cy + arm))
            painter.drawLine(QPointF(cx - arm, cy + arm), QPointF(cx + arm, cy - arm))
        painter.end()


class NavButton(QAbstractButton):
    """A rail destination: a hand-drawn glyph painted in the brand gradient.

    The panel is deliberately *empty*.  Filled gradient pills behind five icons
    turned the rail into a row of buttons competing with the page; the glyph
    itself carries the brand instead, and the active destination is marked by
    ink strength plus a short gradient bar on the rail's edge.  Nothing here
    paints a background, so the rail's glass shows through.
    """

    GLYPHS = ("chat", "notes", "tools", "profile", "settings")

    #: Active glyphs are saturated; idle ones fall back to this ink.
    IDLE_INK = QColor(TEXT_DIM)

    #: The caption under each glyph, used when the rail is wide enough.
    LABELS = {
        "chat": "Sohbet",
        "notes": "Notlar",
        "tools": "Araçlar",
        "profile": "Kişisel",
        "settings": "Ayarlar",
    }

    def __init__(
        self,
        glyph: str,
        parent: QWidget | None = None,
        *,
        size: int = 42,
        with_label: bool = False,
    ) -> None:
        super().__init__(parent)
        if glyph not in self.GLYPHS:
            raise ValueError(f"bilinmeyen gezinme simgesi: {glyph}")
        self.glyph = glyph
        #: A wide rail carries a caption under the glyph; the compact rail does
        #: not.  The label rides in the same widget so hover/active stay in one
        #: place and the whole row is one hit target.
        self.with_label = bool(with_label)
        if self.with_label:
            self.setFixedHeight(size)
            self.setMinimumWidth(120)
        else:
            self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        # Both attributes are required for a self-painting widget on a
        # translucent parent: without them Qt hands paintEvent a buffer with no
        # alpha channel and anything left unpainted comes out opaque black.
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.setCheckable(False)
        self._hover = False
        self._active = False

    def setActive(self, active: bool) -> None:  # noqa: N802 - Qt style naming
        if self._active == bool(active):
            return
        self._active = bool(active)
        self.update()

    def isActive(self) -> bool:  # noqa: N802 - Qt style naming
        return self._active

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        from .nora_glyphs import draw_glyph

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        if self.with_label:
            self._paint_row(painter, draw_glyph)
        else:
            self._paint_compact(painter, draw_glyph)
        painter.end()

    def _paint_compact(self, painter: QPainter, draw_glyph) -> None:
        """The icon-only form: a whisper behind the glyph, nothing else."""
        box = QRectF(self.rect()).adjusted(9, 9, -9, -9)
        if self._active or self._hover:
            pill = QPainterPath()
            pill.addRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 14, 14)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(123, 92, 255, 26 if self._active else 14))
            painter.drawPath(pill)

        if self._active:
            painter.setPen(QPen(gradient_brush(self.rect(), vertical=True), 1.9))
        elif self._hover:
            painter.setPen(QPen(QColor(ACCENT), 1.9))
        else:
            painter.setPen(QPen(self.IDLE_INK, 1.7))
        painter.setBrush(Qt.NoBrush)
        draw_glyph(painter, self.glyph, box)

    def _paint_row(self, painter: QPainter, draw_glyph) -> None:
        """The wide form: glyph on the left, caption on the right.

        The rail reads as a list of destinations rather than a strip of icons —
        the same reason a desktop app names its sections.  The active row is a
        full-width soft pill in the brand tint; the glyph alone carries the
        gradient, so the row stays calm.
        """
        full = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._active or self._hover:
            pill = QPainterPath()
            pill.addRoundedRect(full, 13, 13)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(123, 92, 255, 30 if self._active else 16))
            painter.drawPath(pill)
            if self._active:
                # A 3 px gradient bar on the rail's edge marks the destination.
                bar = QRectF(full.left() + 1, full.top() + 9, 3.0, full.height() - 18)
                painter.setBrush(gradient_brush(bar, vertical=True))
                painter.drawRoundedRect(bar, 1.5, 1.5)

        glyph_box = QRectF(full.left() + 8, full.top(), 34, full.height())
        glyph_box = glyph_box.adjusted(6, 7, -6, -7)

        if self._active:
            painter.setPen(QPen(gradient_brush(glyph_box, vertical=True), 1.9))
        elif self._hover:
            painter.setPen(QPen(QColor(ACCENT), 1.9))
        else:
            painter.setPen(QPen(self.IDLE_INK, 1.7))
        painter.setBrush(Qt.NoBrush)
        draw_glyph(painter, self.glyph, glyph_box)

        # The caption.  Weight carries the state, colour stays quiet so the
        # icons remain the loudest thing in the rail.
        font = QFont(self.font())
        font.setPointSizeF(9.4)
        font.setWeight(QFont.DemiBold if self._active else QFont.Medium)
        painter.setFont(font)
        painter.setPen(QColor(TEXT if self._active else TEXT_DIM))
        text_rect = QRectF(
            glyph_box.right() + 10,
            full.top(),
            full.width() - glyph_box.width() - 26,
            full.height(),
        )
        painter.drawText(
            text_rect, int(Qt.AlignLeft | Qt.AlignVCenter), self.LABELS[self.glyph]
        )


class SuggestionCard(QAbstractButton):
    """A way into the product: a gradient glyph, a name, and what it gives you.

    The greeting used to offer three bare pills.  A card that also says *what
    will happen* teaches the product while it waits — and it gives the empty
    state a grid to sit on instead of a void.  Painted, not styled: the icon is
    the same hand-drawn glyph family as the rail, so the two read as one app.
    """

    GLYPHS = ("screen", "clock", "notes", "spark")

    def __init__(
        self,
        glyph: str,
        title: str,
        blurb: str,
        parent: QWidget | None = None,
        *,
        width: int = 344,
        height: int = 92,
    ) -> None:
        super().__init__(parent)
        if glyph not in self.GLYPHS:
            raise ValueError(f"bilinmeyen öneri simgesi: {glyph}")
        self.glyph = glyph
        self.title = title
        self.blurb = blurb
        # Flexible in *both* directions.  A fixed height clipped the blurb on a
        # narrow window (the title wraps to two lines and the promise had no
        # room).  The grid still keeps a rhythm because every card in a row
        # gets the row's height.
        self.setMinimumSize(width // 2, height)
        self.setMaximumWidth(width)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAutoFillBackground(False)
        self.setAccessibleName(title)
        self.setToolTip(blurb)
        self._hover = False

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        """Tall enough for a wrapped title *and* the blurb underneath it."""
        return QSize(self.maximumWidth(), self._wrapped_height())

    def _wrapped_height(self) -> int:
        """The height this card needs at its **current** width."""
        width = max(self.width(), self.minimumWidth()) - 13 - 34 - 11 - 11
        title_font = QFont(self.font())
        title_font.setPointSizeF(10.6)
        title_font.setWeight(QFont.DemiBold)
        blurb_font = QFont(self.font())
        blurb_font.setPointSizeF(8.8)
        title_h = (
            QFontMetrics(title_font)
            .boundingRect(QRect(0, 0, width, 1000), int(Qt.TextWordWrap), self.title)
            .height()
        )
        blurb_h = (
            QFontMetrics(blurb_font)
            .boundingRect(QRect(0, 0, width, 1000), int(Qt.TextWordWrap), self.blurb)
            .height()
        )
        return title_h + blurb_h + 16 + 20 + 14

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        from .nora_glyphs import draw_glyph

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        card = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        # The surface: white paper, a hairline, and a brand-tinted shadow that
        # only appears on hover.  Resting cards must not look clickable-loud.
        painter.setPen(QPen(QColor(123, 92, 255, 54 if self._hover else 0), 1.2))
        painter.setBrush(QColor(255, 255, 255, 250))
        painter.drawRoundedRect(card, 16, 16)
        painter.setPen(QPen(QColor(123, 92, 255, 40) if self._hover else HAIRLINE, 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(card, 16, 16)

        # The glyph badge: a rounded gradient tile, the same material as the
        # mark, so each card carries the brand without becoming a button.
        badge = QRectF(card.left() + 13, card.top() + 16, 34, 34)
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient_brush(badge))
        painter.drawRoundedRect(badge, 11, 11)
        glyph_box = badge.adjusted(8, 8, -8, -8)
        painter.setPen(
            QPen(
                QColor(255, 255, 255, 240), 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin
            )
        )
        painter.setBrush(Qt.NoBrush)
        draw_glyph(painter, self.glyph, glyph_box)

        text_left = badge.right() + 11
        text_width = card.right() - text_left - 11

        # Both strings wrap.  A card can be 180 px wide on a small window, and
        # a single-line title was simply cut off at the badge ("Ekranımı öz…"):
        # the promise the card makes has to survive the narrow case.
        title_font = QFont(self.font())
        title_font.setPointSizeF(10.6)
        title_font.setWeight(QFont.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(TEXT))
        title_flags = int(Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
        title_rect = QRectF(text_left, card.top() + 18, text_width, 34)
        painter.drawText(title_rect, title_flags, self.title)

        # The blurb starts under the title, wherever the title actually ended,
        # so a two-line title never collides with it.
        used = painter.boundingRect(
            title_rect.toRect(),
            int(Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap),
            self.title,
        ).height()
        blurb_font = QFont(self.font())
        blurb_font.setPointSizeF(8.8)
        painter.setFont(blurb_font)
        painter.setPen(QColor(TEXT_DIM))
        painter.drawText(
            QRectF(
                text_left,
                card.top() + 20 + used,
                text_width,
                card.bottom() - (card.top() + 20 + used) - 12,
            ),
            int(Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap),
            self.blurb,
        )
        painter.end()


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
        from .nora_brand import draw_mark, tile_path

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        box = min(self.width(), self.height())

        # The tile *is* the mark: the aurora squircle with the white N on it.
        # It brightens on hover, and gets a pink halo while Nora is outside.
        painter.save()
        if self._released:
            halo = QRadialGradient(
                QPointF(self.width() / 2.0, self.height() / 2.0), box * 0.75
            )
            glow = QColor(255, 77, 148, int(90 * (1.0 - self._pulse)))
            halo.setColorAt(0.5, QColor(255, 77, 148, 0))
            halo.setColorAt(1.0, glow)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(halo))
            painter.drawEllipse(
                QRectF(-box * 0.12, -box * 0.12, box * 1.24, box * 1.24)
            )
        draw_mark(painter, int(round(box)), glow=False)
        if self._hover:
            # a soft white wash over the tile, so the whole badge reacts
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 34))
            painter.drawPath(tile_path(QRectF(0, 0, box, box)))
        painter.restore()
        painter.end()

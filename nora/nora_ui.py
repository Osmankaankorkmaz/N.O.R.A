"""Chat window, tray icon and thread-safe integration of every Nora module."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .nora_brain import ChatReply, NoraBrain
from .nora_personality import (
    EMOTIONS,
    CommandError,
    normalize_command,
    startup_greeting,
)
from .nora_pet import NoraPet
from .nora_proactive import ProactiveEngine
from .nora_tools import NoraTools
from .nora_voice import NoraVoice

logger = logging.getLogger(__name__)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "evet"}


@dataclass
class NoraOptions:
    wake_word: bool | None = None
    tts: bool | None = None
    proactive: bool | None = None
    offline: bool = False
    allow_code: bool | None = None


class ChatWorker(QThread):
    done = pyqtSignal(int, object)

    def __init__(
        self, brain: NoraBrain, message: str, request_id: int, parent=None
    ) -> None:
        super().__init__(parent)
        self.brain, self.message, self.request_id = brain, message, request_id

    def run(self) -> None:
        try:
            reply = self.brain.chat(self.message)
        except Exception as exc:
            logger.exception("Sohbet worker hatası: %s", type(exc).__name__)
            reply = ChatReply(
                "Pff, bir şeyler ters gitti senpai. Tekrar dener misin?",
                "sad",
                error=True,
            )
        self.done.emit(self.request_id, reply)


class ImageWorker(QThread):
    done = pyqtSignal(int, object)

    def __init__(
        self, brain: NoraBrain, image: str, prompt: str, request_id: int, parent=None
    ) -> None:
        super().__init__(parent)
        self.brain, self.image, self.prompt, self.request_id = (
            brain,
            image,
            prompt,
            request_id,
        )

    def run(self) -> None:
        try:
            reply = self.brain.analyze_image(self.image, self.prompt)
        except Exception as exc:
            logger.exception("Görsel worker hatası: %s", type(exc).__name__)
            reply = ChatReply(
                "Görüntüyü analiz edemedim senpai. Bir daha dener misin?",
                "sad",
                error=True,
            )
        self.done.emit(self.request_id, reply)


class ToolWorker(QThread):
    done = pyqtSignal(int, bool, object)

    def __init__(
        self, function: Callable[[], Any], request_id: int, parent=None
    ) -> None:
        super().__init__(parent)
        self.function, self.request_id = function, request_id

    def run(self) -> None:
        try:
            result = self.function()
            self.done.emit(self.request_id, True, result)
        except Exception as exc:
            logger.warning("Araç worker hatası: %s", type(exc).__name__)
            self.done.emit(
                self.request_id,
                False,
                "Bu işlemi tamamlayamadım senpai. Araç/izin desteğini kontrol et. 🐾",
            )


class ChatBubble(QFrame):
    def __init__(self, text: str, sender: str, parent=None) -> None:
        super().__init__(parent)
        color = "#7c4dff" if sender == "user" else "#ff6b9d"
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"ChatBubble {{ background: {color}; border-radius: 14px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(11, 8, 11, 8)
        label = QLabel(str(text))
        label.setWordWrap(True)
        label.setMaximumWidth(280)
        label.setTextFormat(Qt.PlainText)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setStyleSheet("color: white; background: transparent; font-size: 13px;")
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout.addWidget(label)
        self.setMaximumWidth(304)


class NoraApp(QWidget):
    """Invisible owner widget; the visible UI is NoraPet + a separate chat."""

    def __init__(self, options: NoraOptions | None = None, parent=None) -> None:
        super().__init__(parent)
        self.options = options or NoraOptions()
        self.setWindowTitle("Nora")
        self.setWindowFlags(Qt.Tool)
        self.setFixedSize(0, 0)
        self.hide()
        self._closing = False
        self._busy = False
        self._listening = False
        self._wake_followup = False
        self._resume_wake_after_audio = False
        self._request_seq = 0
        self._active_request = 0
        self._workers: set[QThread] = set()
        self._message_rows: list[QWidget] = []
        self._chat_user_moved = False
        self._chat_drag_offset: QPoint | None = None
        self._notified_errors: set[str] = set()
        self._last_city = ""

        wake = (
            self.options.wake_word
            if self.options.wake_word is not None
            else env_bool("NORA_WAKE_WORD", True)
        )
        tts = (
            self.options.tts
            if self.options.tts is not None
            else env_bool("NORA_TTS", True)
        )
        proactive_enabled = (
            self.options.proactive
            if self.options.proactive is not None
            else env_bool("NORA_PROACTIVE", True)
        )
        self.brain = NoraBrain(
            offline=self.options.offline or env_bool("NORA_OFFLINE", False)
        )
        self.tools = NoraTools(allow_code=self.options.allow_code, parent=self)
        self.voice = NoraVoice(tts_enabled=tts, parent=self)
        self.pet = NoraPet()
        self.proactive = ProactiveEngine(self.tools, parent=self)
        self._build_chat()
        self._build_tray()
        self._connect_signals()

        self.tts_action.setChecked(tts)
        self.wake_action.setChecked(bool(wake))
        self.proactive_action.setChecked(proactive_enabled)
        if wake:
            self.voice.start_wake_word_listener()
        if proactive_enabled:
            self.proactive.start()
        self._update_mic_indicator()
        QTimer.singleShot(1000, self._greet)

    # ------------------------------------------------------------------ build UI
    @staticmethod
    def _emoji_font(point_size: int = 10) -> QFont:
        font = QFont("Segoe UI", point_size)
        try:
            font.setFamilies(
                [
                    "Segoe UI Emoji",
                    "Noto Color Emoji",
                    "Apple Color Emoji",
                    "Segoe UI Symbol",
                    "Segoe UI",
                ]
            )
        except AttributeError:
            pass
        return font

    def _build_chat(self) -> None:
        self.chat_window = QWidget(None)
        self.chat_window.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.chat_window.setAttribute(Qt.WA_TranslucentBackground)
        self.chat_window.setWindowTitle("Nora · Sohbet")
        self.chat_window.resize(380, 560)
        self.chat_window.setMinimumSize(340, 430)
        root = QVBoxLayout(self.chat_window)
        root.setContentsMargins(6, 6, 6, 6)
        shell = QFrame()
        shell.setObjectName("chatShell")
        shell.setStyleSheet("""
            QFrame#chatShell { background: rgba(30,20,40,235); border: 1px solid #ff6b9d; border-radius: 20px; }
            QLabel { color: #f7ecff; background: transparent; }
            QLabel#title { color: #ff6b9d; font-size: 17px; font-weight: 700; }
            QLabel#status { color: #d7a8cc; font-size: 11px; }
            QPushButton { background: rgba(255,107,157,35); color: #ffd6e6; border: 1px solid rgba(255,107,157,80);
                          border-radius: 9px; padding: 4px 7px; font-size: 12px; }
            QPushButton:hover { background: #7c4dff; border-color: #b388ff; }
            QPushButton:pressed { background: #ff6b9d; }
            QPushButton:disabled { color: #796b85; background: rgba(80,60,95,60); }
            QLineEdit { background: rgba(15,10,24,170); color: white; border: 1px solid #a45c8c;
                        border-radius: 12px; padding: 8px 10px; font-size: 13px; selection-background-color: #7c4dff; }
            QLineEdit:focus { border: 1px solid #ff6b9d; }
            QScrollArea { background: rgba(15,10,24,120); border: none; border-radius: 12px; }
            QScrollBar:vertical { background: rgba(30,20,40,100); width: 6px; border-radius: 3px; }
            QScrollBar::handle:vertical { background: #ff6b9d; border-radius: 3px; min-height: 24px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QToolTip { color: white; background: #3a204c; border: 1px solid #ff6b9d; padding: 4px; }
        """)
        root.addWidget(shell)
        layout = QVBoxLayout(shell)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)

        header = QWidget()
        header.setFixedHeight(34)
        header.setCursor(Qt.SizeAllCursor)
        header.installEventFilter(self)
        self.chat_header = header
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Nora")
        title.setObjectName("title")
        header_layout.addWidget(title)
        self.mic_indicator = QLabel("🎙️")
        self.mic_indicator.setFont(self._emoji_font(10))
        self.mic_indicator.setToolTip("Mikrofon durumu")
        header_layout.addWidget(self.mic_indicator)
        header_layout.addStretch()
        for text, tip, slot in (
            ("📸", "Ekran görüntüsü al ve analiz et", self._analyze_screen),
            ("📷", "Kameradan bir kare analiz et", self._analyze_camera),
            ("🎤", "Sesli komut ver", self._start_listening),
            ("💻", "Sistem bilgisi", self._show_system_info),
            ("─", "Sohbeti küçült", self.chat_window.hide),
            ("✕", "Sohbeti gizle (Nora çalışmaya devam eder)", self.chat_window.hide),
        ):
            button = QPushButton(text)
            button.setToolTip(tip)
            button.setAccessibleName(tip)
            button.setFont(self._emoji_font(10))
            button.setFixedSize(29, 28)
            button.clicked.connect(slot)
            header_layout.addWidget(button)
            if text == "📸":
                self.screen_button = button
            elif text == "📷":
                self.camera_button = button
            elif text == "🎤":
                self.mic_button = button
            elif text == "💻":
                self.system_button = button
        layout.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self.message_layout = QVBoxLayout(content)
        self.message_layout.setContentsMargins(8, 10, 8, 10)
        self.message_layout.setSpacing(8)
        self.message_layout.addStretch(1)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)

        self.status_label = QLabel("")
        self.status_label.setObjectName("status")
        self.status_label.setFixedHeight(18)
        layout.addWidget(self.status_label)
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Mesajını yaz senpai~ 💕")
        self.input.setMaxLength(4000)
        self.input.returnPressed.connect(self._send_from_input)
        self.send_button = QPushButton("💝")
        self.send_button.setFixedSize(38, 36)
        self.send_button.setToolTip("Gönder (Enter)")
        self.send_button.setFont(self._emoji_font(11))
        self.send_button.clicked.connect(self._send_from_input)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)
        quick_row = QHBoxLayout()
        self.quick_buttons: list[QPushButton] = []
        for text, slot in (
            ("🔍 Ara", self._quick_search),
            ("⏰ Saat", self._quick_time),
            ("📝 Notlar", self._show_notes),
            ("🌤️ Hava", self._quick_weather),
        ):
            button = QPushButton(text)
            button.setFont(self._emoji_font(9))
            button.clicked.connect(slot)
            quick_row.addWidget(button)
            self.quick_buttons.append(button)
        layout.addLayout(quick_row)
        self.chat_window.installEventFilter(self)

    def _tray_icon(self) -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ff6b9d"))
        p.drawEllipse(2, 2, 60, 60)
        p.setBrush(QColor("#3b2055"))
        ears = QPainterPath()
        ears.moveTo(14, 25)
        ears.lineTo(16, 9)
        ears.lineTo(28, 21)
        ears.moveTo(36, 21)
        ears.lineTo(48, 9)
        ears.lineTo(50, 25)
        p.drawPath(ears)
        p.drawEllipse(12, 17, 40, 36)
        p.setBrush(QColor("#ffe0d0"))
        p.drawEllipse(17, 24, 30, 27)
        p.setBrush(QColor("#3b2055"))
        p.drawEllipse(22, 33, 5, 7)
        p.drawEllipse(37, 33, 5, 7)
        p.setPen(QPen(QColor("#9c4665"), 2, Qt.SolidLine, Qt.RoundCap))
        p.setBrush(Qt.NoBrush)
        mouth = QPainterPath(QPointF(28, 44))
        mouth.quadTo(32, 48, 36, 44)
        p.drawPath(mouth)
        p.end()
        return QIcon(pixmap)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip("Nora 💕")
        menu = QMenu()
        menu.setStyleSheet(self._menu_style())
        menu.addAction("Göster", self._show_pet)
        menu.addAction("Sohbet Aç", self.show_chat)
        menu.addAction("Ekran Analiz", self._analyze_screen)
        menu.addAction("Sesli Komut", self._start_listening)
        menu.addAction("🎙️ Mikrofon Testi", self._test_microphone)
        menu.addAction("🎧 Mikrofon Seç", self._select_microphone)
        menu.addAction("🩺 Groq Bağlantısı", self._check_groq)
        emotions = menu.addMenu("Duygular")
        emotions.setStyleSheet(self._menu_style())
        labels = {
            "happy": "Mutlu",
            "thinking": "Düşünceli",
            "surprised": "Şaşkın",
            "love": "Aşık",
            "angry": "Kızgın",
            "sad": "Üzgün",
            "sleepy": "Uykulu",
            "smug": "Kibirli",
        }
        for key, label in labels.items():
            emotions.addAction(
                f"{EMOTIONS[key]['emoji']} {label}",
                lambda k=key: self.pet.set_emotion(k),
            )
        menu.addSeparator()
        self.tts_action = menu.addAction("Sesli yanıt")
        self.tts_action.setCheckable(True)
        self.tts_action.toggled.connect(self._toggle_tts)
        self.wake_action = menu.addAction("Hey Nora bekçisi (yerel) 🎙️")
        self.wake_action.setCheckable(True)
        self.wake_action.toggled.connect(self._toggle_wake)
        self.proactive_action = menu.addAction("Proaktif konuşma")
        self.proactive_action.setCheckable(True)
        self.proactive_action.toggled.connect(self._toggle_proactive)
        menu.addSeparator()
        menu.addAction("Hafızayı Sıfırla", self._reset_memory)
        menu.addAction("Kapat", self.shutdown)
        self.tray.setContextMenu(menu)
        self.tray_menu = menu
        self.tray.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        else:
            logger.warning("System tray yok; pet sağ tık menüsü kullanılabilir.")

    @staticmethod
    def _menu_style() -> str:
        return """QMenu { background: #2a193c; color: white; border: 1px solid #ff6b9d; padding: 5px; }
                  QMenu::item { padding: 6px 22px; border-radius: 5px; }
                  QMenu::item:selected { background: #ff6b9d; }
                  QMenu::separator { height: 1px; background: #6a3d7e; margin: 4px 8px; }"""

    def _connect_signals(self) -> None:
        self.pet.clicked.connect(self.toggle_chat)
        self.pet.double_clicked.connect(self.show_chat)
        self.pet.right_clicked.connect(self._pet_menu)
        self.pet.position_changed.connect(self._on_pet_moved)
        self.voice.speaking_started.connect(self._on_speaking_started)
        self.voice.speaking_finished.connect(self._on_speaking_finished)
        self.voice.speech_error.connect(self._on_voice_error)
        self.voice.voice_error.connect(self._on_voice_error)
        self.voice.listening_started.connect(self._on_listening_started)
        self.voice.listening_stopped.connect(self._on_listening_stopped)
        self.voice.listening_finished.connect(self._on_listen_done)
        self.voice.wake_word_detected.connect(self._on_wake_word)
        self.tools.timer_finished.connect(self._on_timer)
        self.proactive.speak_requested.connect(self._on_proactive)
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.shutdown)

    def start(self) -> None:
        self.pet.show()
        self.pet.raise_()

    # ------------------------------------------------------------------- helpers
    def _next_request(self) -> int:
        self._request_seq += 1
        self._active_request = self._request_seq
        return self._request_seq

    def _track_worker(self, worker: QThread) -> None:
        self._workers.add(worker)
        worker.finished.connect(lambda w=worker: self._forget_worker(w))

    def _forget_worker(self, worker: QThread) -> None:
        self._workers.discard(worker)
        worker.deleteLater()
        if self._closing and not self._workers:
            app = QApplication.instance()
            if app:
                app.quit()

    def _sync_pause(self) -> None:
        self.proactive.set_suspended(
            self._busy or self._listening or self.voice.is_speaking
        )

    def _set_busy(self, busy: bool, status: str = "") -> None:
        self._busy = busy
        self.status_label.setText(status)
        for button in (
            self.send_button,
            self.screen_button,
            self.camera_button,
            self.mic_button,
            self.system_button,
            *self.quick_buttons,
        ):
            button.setEnabled(not busy)
        self._sync_pause()

    def add_message(self, text: str, sender: str = "bot") -> None:
        text = str(text).strip()
        if not text:
            return
        if len(text) > 8000:
            text = text[:8000] + "…"
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        bubble = ChatBubble(text, sender)
        if sender == "user":
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)
        else:
            row_layout.addWidget(bubble)
            row_layout.addStretch(1)
        self.message_layout.insertWidget(self.message_layout.count() - 1, row)
        self._message_rows.append(row)
        while len(self._message_rows) > 200:
            old = self._message_rows.pop(0)
            self.message_layout.removeWidget(old)
            old.deleteLater()
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _clear_messages(self) -> None:
        for row in self._message_rows:
            self.message_layout.removeWidget(row)
            row.deleteLater()
        self._message_rows.clear()

    def show_chat(self) -> None:
        if self._closing:
            return
        self.proactive.user_interacted()
        self.pet.show()
        self._chat_user_moved = False
        self._position_chat()
        self.chat_window.show()
        self.chat_window.raise_()
        self.input.setFocus()

    def toggle_chat(self) -> None:
        if self.chat_window.isVisible():
            self.chat_window.hide()
        else:
            self.show_chat()

    def _show_pet(self) -> None:
        self.pet.show()
        self.pet.raise_()

    def _position_chat(self) -> None:
        if not self.chat_window.isVisible() and not self.chat_window.isHidden():
            return
        app = QApplication.instance()
        screen = (
            app.screenAt(
                self.pet.pos() + QPoint(self.pet.width() // 2, self.pet.height() // 2)
            )
            if app
            else None
        )
        screen = screen or self.pet.screen() or (app.primaryScreen() if app else None)
        if screen is None:
            return
        area = screen.availableGeometry()
        width, height = self.chat_window.width(), self.chat_window.height()
        right = self.pet.x() + self.pet.width() + 10
        x = right if right + width <= area.right() + 1 else self.pet.x() - width - 10
        x = max(area.left(), min(x, area.right() - width + 1))
        y = self.pet.y() + self.pet.height() - height - 8
        y = max(area.top(), min(y, area.bottom() - height + 1))
        self.chat_window.move(x, y)

    def _on_pet_moved(self, point: QPoint) -> None:
        if self.chat_window.isVisible() and not self._chat_user_moved:
            self._position_chat()

    def eventFilter(self, obj, event) -> bool:
        header = getattr(self, "chat_header", None)
        window = getattr(self, "chat_window", None)
        if header is not None and obj is header:
            if (
                event.type() == QEvent.MouseButtonPress
                and event.button() == Qt.LeftButton
            ):
                self._chat_drag_offset = event.globalPos() - window.pos()
                return True
            if (
                event.type() == QEvent.MouseMove
                and self._chat_drag_offset is not None
                and event.buttons() & Qt.LeftButton
            ):
                window.move(event.globalPos() - self._chat_drag_offset)
                self._chat_user_moved = True
                return True
            if event.type() == QEvent.MouseButtonRelease:
                self._chat_drag_offset = None
                return True
        if window is not None and obj is window and event.type() == QEvent.Close:
            event.ignore()
            window.hide()
            return True
        return super().eventFilter(obj, event)

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_chat()

    def _pet_menu(self, point: QPoint) -> None:
        self.proactive.user_interacted()
        menu = QMenu()
        menu.setStyleSheet(self._menu_style())
        menu.addAction(
            "Sohbeti Kapat" if self.chat_window.isVisible() else "Sohbet Aç",
            self.toggle_chat,
        )
        menu.addAction("📸 Ekran Analiz", self._analyze_screen)
        menu.addAction("📷 Kamera", self._analyze_camera)
        menu.addAction("🎤 Sesli Komut", self._start_listening)
        menu.addAction("🎙️ Mikrofon Testi", self._test_microphone)
        menu.addAction("🎧 Mikrofon Seç", self._select_microphone)
        menu.addAction("🩺 Groq Bağlantısı", self._check_groq)
        menu.addAction("💻 Sistem Bilgisi", self._show_system_info)
        menu.addAction("📝 Notlarım", self._show_notes)
        menu.addAction("🌤️ Hava Durumu", self._quick_weather)
        emotions = menu.addMenu("Duygu Değiştir")
        emotions.setStyleSheet(self._menu_style())
        for key, data in EMOTIONS.items():
            emotions.addAction(
                f"{data['emoji']} {key}", lambda k=key: self.pet.set_emotion(k)
            )
        menu.addSeparator()
        menu.addAction("Hafızayı Sıfırla", self._reset_memory)
        menu.addAction("Kapat", self.shutdown)
        menu.exec_(point)

    def _update_mic_indicator(self) -> None:
        active = self.voice.wake_word_active
        self.mic_indicator.setText("🎙️" if active else "🔇")
        self.mic_indicator.setToolTip(
            "Yerel 'Hey Nora' bekçisi AÇIK · komut dinlemiyor, ses buluta gitmez"
            if active
            else "Hey Nora bekçisi kapalı · yalnızca 🎤 ile dinlenir"
        )

    def _toggle_tts(self, enabled: bool) -> None:
        self.voice.set_tts_enabled(enabled)
        self._sync_pause()

    def _toggle_wake(self, enabled: bool) -> None:
        if enabled:
            self.voice.start_wake_word_listener()
        else:
            self.voice.stop_wake_word_listener()
        QTimer.singleShot(250, self._update_mic_indicator)

    def _toggle_proactive(self, enabled: bool) -> None:
        if enabled:
            self.proactive.user_interacted()
            self.proactive.start()
        else:
            self.proactive.stop()

    def _confirm(self, title: str, text: str) -> bool:
        box = QMessageBox(self.chat_window)
        box.setIcon(QMessageBox.Question)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        box.button(QMessageBox.Yes).setText("Evet")
        box.button(QMessageBox.No).setText("Hayır")
        box.setStyleSheet(
            "QMessageBox { background: #2a193c; } QLabel { color: white; } QPushButton { color: white; background: #7c4dff; padding: 6px 14px; border-radius: 6px; }"
        )
        return box.exec_() == QMessageBox.Yes

    # ---------------------------------------------------------------------- chat
    def _send_from_input(self) -> None:
        text = self.input.text().strip()
        self.input.clear()
        self._send_message(text)

    def _send_message(self, text: str) -> None:
        if self._closing or not text.strip():
            return
        if self._busy or self._listening:
            self.status_label.setText("Bir saniye senpai, önce bu işi bitireyim…")
            return
        self.proactive.user_interacted()
        self.add_message(text, "user")
        self.pet.show_user_speech(text)
        self.pet.set_emotion("thinking")
        self._set_busy(True, "Düşünüyorum…")
        request_id = self._next_request()
        worker = ChatWorker(self.brain, text, request_id)
        worker.done.connect(self._on_chat_done)
        self._track_worker(worker)
        worker.start()

    def _on_chat_done(self, request_id: int, reply: ChatReply) -> None:
        if self._closing or request_id != self._active_request:
            return
        self._set_busy(False)
        self.add_message(reply.text, "bot")
        self.pet.set_emotion(reply.emotion)
        self.voice.speak(reply.text)
        if reply.command and not reply.error:
            self._execute_command(reply.command)
        self._sync_pause()

    def _run_tool(
        self,
        function: Callable[[], Any],
        status: str = "Hallediyorum…",
        *,
        speak: bool = True,
    ) -> None:
        if self._closing or self._busy:
            return
        self._set_busy(True, status)
        request_id = self._next_request()
        worker = ToolWorker(function, request_id)
        worker.done.connect(
            lambda rid, ok, result, s=speak: self._on_tool_done(rid, ok, result, s)
        )
        self._track_worker(worker)
        worker.start()

    def _on_tool_done(
        self, request_id: int, ok: bool, result: Any, speak: bool
    ) -> None:
        if self._closing or request_id != self._active_request:
            return
        self._set_busy(False)
        text = str(result) if result is not None else "İşlem tamamlandı senpai. 🐾"
        self.add_message(text, "bot")
        self.pet.set_emotion("happy" if ok else "sad")
        if speak and len(text) <= 300:
            self.voice.speak(text)

    def _execute_command(self, command: dict[str, Any]) -> None:
        try:
            cmd = normalize_command(command)
        except CommandError as exc:
            self.add_message(f"Hımm, bu komutu çalıştıramam: {exc}", "bot")
            return
        name = cmd["command"]
        if name == "screenshot":
            self._analyze_screen(cmd.get("prompt"))
        elif name == "camera":
            self._analyze_camera(cmd.get("prompt"))
        elif name == "shutdown":
            if self._confirm(
                "Bilgisayarı kapat",
                "Bilgisayar 60 saniye sonra kapanacak. Planlayayım mı senpai?",
            ):
                self.add_message(self.tools.shutdown(), "bot")
        elif name == "cancel_shutdown":
            self.add_message(self.tools.cancel_shutdown(), "bot")
        elif name == "run_code":
            if not self.tools.allow_code:
                self.add_message(
                    "Kod çalıştırma kapalı senpai. NORA_ALLOW_CODE=1 ile açabilirsin; her kod yine onay ister. 😾",
                    "bot",
                )
            elif self._confirm(
                "Python kodu çalıştır",
                "Bu kod SENİN kullanıcı yetkilerinle çalışır; güvenli bir sandbox değildir.\n\n"
                + cmd["code"][:1500]
                + "\n\nÇalıştırayım mı?",
            ):
                self._run_tool(
                    lambda: self.tools.run_code(cmd["code"], cmd["language"]),
                    "Kodu çalıştırıyorum…",
                )
        elif name == "type_text":
            if self._confirm(
                "Etkin pencereye yaz",
                "Şu metin etkin pencereye yazılacak:\n\n"
                + cmd["text"][:500]
                + "\n\nDevam edeyim mi senpai?",
            ):
                self._run_tool(
                    lambda: self.tools.type_text(cmd["text"]),
                    "Metni yazıyorum…",
                    speak=False,
                )
        elif name == "clipboard_copy":
            self.add_message(self.tools.clipboard_copy(cmd["text"]), "bot")
        elif name == "note":
            result = (
                self.tools.add_note(cmd["text"])
                if cmd["action"] == "add"
                else self.tools.list_notes()
            )
            self.add_message(result, "bot")
            if cmd["action"] == "add":
                self.voice.speak(result)
        elif name == "set_timer":
            self.add_message(
                self.tools.set_timer(cmd["seconds"], cmd["message"]), "bot"
            )
        elif name == "weather":
            self._last_city = cmd["city"]
            self._run_tool(lambda: self.tools.weather(cmd["city"]), "Havaya bakıyorum…")
        elif name == "system_info":
            self._run_tool(
                self.tools.system_info, "Sistem bilgisi okunuyor…", speak=False
            )
        elif name == "open_app":
            self.add_message(self.tools.open_app(cmd["app"]), "bot")
        elif name == "search":
            self._run_tool(lambda: self.tools.search(cmd["query"]), "Aramayı açıyorum…")
        elif name == "open_url":
            self._run_tool(
                lambda: self.tools.open_url(cmd["url"]), "Bağlantıyı açıyorum…"
            )
        elif name == "play_music":
            self._run_tool(
                lambda: self.tools.play_music(cmd["query"]), "Müzik arıyorum…"
            )
        elif name == "volume":
            self._run_tool(
                lambda: self.tools.set_volume(cmd["level"]), "Sesi ayarlıyorum…"
            )
        elif name == "brightness":
            self._run_tool(
                lambda: self.tools.set_brightness(cmd["level"]),
                "Parlaklığı ayarlıyorum…",
            )
        elif name == "lock_screen":
            self.add_message(self.tools.lock_screen(), "bot")

    # -------------------------------------------------------------------- vision
    def _analyze_screen(self, prompt: str | None = None) -> None:
        if self._closing or self._busy or self._listening:
            return
        if not self.brain.available:
            self.show_chat()
            self.add_message(
                "Ekran analizi için Groq bağlantısı gerekli senpai. GROQ_API_KEY ayarla. 🐾",
                "bot",
            )
            return
        self.proactive.user_interacted()
        self._set_busy(True, "Ekran hazırlanıyor…")
        request_id = self._next_request()
        chat_was_visible = self.chat_window.isVisible()
        pet_was_visible = self.pet.isVisible()
        self.chat_window.hide()
        self.pet.hide()
        QTimer.singleShot(
            500,
            lambda: self._capture_screen(
                request_id,
                prompt or "Ekranımda ne görüyorsun? Kısaca anlat.",
                chat_was_visible,
                pet_was_visible,
            ),
        )

    def _capture_screen(
        self, request_id: int, prompt: str, chat_visible: bool, pet_visible: bool
    ) -> None:
        if self._closing:
            return
        try:
            image = self.tools.screenshot()
        finally:
            if pet_visible:
                self.pet.show()
            if chat_visible:
                self.chat_window.show()
                self._position_chat()
        if image is None:
            self._set_busy(False)
            self.add_message(
                "Ekran görüntüsü alamadım senpai. Masaüstü/ekran kaydı iznini kontrol et. 📸",
                "bot",
            )
            self.pet.set_emotion("sad")
            return
        self.add_message("Ekranına bakıyorum senpai~ 📸", "bot")
        self._start_image_worker(request_id, image, prompt, "Ekran analiz ediliyor…")

    def _analyze_camera(self, prompt: str | None = None) -> None:
        if self._closing or self._busy or self._listening:
            return
        if not self.brain.available:
            self.show_chat()
            self.add_message(
                "Kamera analizi için Groq bağlantısı gerekli senpai. GROQ_API_KEY ayarla. 🐾",
                "bot",
            )
            return
        self.proactive.user_interacted()
        self._set_busy(True, "Kamera açılıyor…")
        request_id = self._next_request()
        worker = ToolWorker(self.tools.capture_camera, request_id)
        worker.done.connect(
            lambda rid, ok, image, p=prompt: self._on_camera_captured(rid, ok, image, p)
        )
        self._track_worker(worker)
        worker.start()

    def _on_camera_captured(
        self, request_id: int, ok: bool, image: Any, prompt: str | None
    ) -> None:
        if self._closing or request_id != self._active_request:
            return
        if not ok or not image:
            self._set_busy(False)
            self.add_message(
                "Kamerayı açamadım senpai. Kamera iznini ve başka uygulamanın kullanıp kullanmadığını kontrol et. 📷",
                "bot",
            )
            self.pet.set_emotion("sad")
            return
        self.add_message("Kameradan bakıyorum~ 📷", "bot")
        self._start_image_worker(
            request_id,
            image,
            prompt or "Kamerada ne görüyorsun? Kısaca Türkçe anlat.",
            "Kamera analiz ediliyor…",
        )

    def _start_image_worker(
        self, request_id: int, image: str, prompt: str, status: str
    ) -> None:
        self.status_label.setText(status)
        self.pet.set_emotion("thinking")
        worker = ImageWorker(self.brain, image, prompt, request_id)
        worker.done.connect(self._on_image_done)
        self._track_worker(worker)
        worker.start()

    def _on_image_done(self, request_id: int, reply: ChatReply) -> None:
        if self._closing or request_id != self._active_request:
            return
        self._set_busy(False)
        self.add_message(reply.text, "bot")
        self.pet.set_emotion(reply.emotion)
        self.voice.speak(reply.text)

    # --------------------------------------------------------------------- voice
    def _start_listening(self) -> None:
        if self._closing or self._busy or self._listening:
            return
        self.show_chat()
        self.proactive.user_interacted()
        self._listening = True
        self._pause_wake_for_audio()
        self._set_busy(True, "Mikrofon açılıyor…")
        self.mic_button.setStyleSheet("background: #e53950; border-color: #ff8fa3;")
        self.pet.set_listening(True)
        request_id = self._next_request()
        if not self.voice.listen_async(request_id):
            self._listening = False
            self.mic_button.setStyleSheet("")
            self.pet.set_listening(False)
            self._set_busy(False)
            self._resume_wake_after_audio_capture()
            self.add_message(
                "Şu an dinleyemiyorum senpai. Mikrofon meşgul veya ses açık. 🎤", "bot"
            )
        self._sync_pause()

    def _on_listen_done(self, request_id: int, text: str, error: str) -> None:
        if self._closing or request_id != self._active_request:
            return
        self._listening = False
        self.mic_button.setStyleSheet("")
        self.pet.set_listening(False)
        self._set_busy(False)
        self.proactive.user_interacted()
        if text:
            self._send_message(text)
        else:
            message = error or "Seni duyamadım senpai. Bir daha dener misin? 🎤"
            self.add_message(message, "bot")
            self.pet.set_emotion("sad")
            self.voice.speak(message)
        self._resume_wake_after_audio_capture()
        self._sync_pause()

    def _pause_wake_for_audio(self) -> None:
        if self.voice.wake_word_active:
            self._resume_wake_after_audio = True
            self.voice.stop_wake_word_listener()
            self._update_mic_indicator()

    def _resume_wake_after_audio_capture(self) -> None:
        if self._resume_wake_after_audio:
            self._resume_wake_after_audio = False
            if self.wake_action.isChecked() and not self._closing:
                self.voice.start_wake_word_listener()
            self._update_mic_indicator()

    def _on_listening_started(self, request_id: int) -> None:
        if self._closing:
            return
        self.pet.set_listening(True)
        if request_id > 0:
            self.status_label.setText("Dinliyorum senpai… konuşabilirsin 🎙️")
        else:
            self.mic_indicator.setToolTip("Nora şu an mikrofondan dinliyor 🎙️")

    def _on_listening_stopped(self, request_id: int) -> None:
        if self._closing:
            return
        self.pet.set_listening(False)
        if request_id > 0 and self._listening:
            self.status_label.setText("Sesini işliyorum…")
            self.pet.set_emotion("thinking")
        self._update_mic_indicator()

    def _test_microphone(self) -> None:
        if self._closing or self._busy or self._listening:
            return
        self.show_chat()
        self._pause_wake_for_audio()
        self._set_busy(True, "Mikrofon test ediliyor… konuş 🎙️")
        self.pet.set_listening(True)
        request_id = self._next_request()
        worker = ToolWorker(self.voice.test_microphone, request_id)
        worker.done.connect(self._on_mic_test_done)
        self._track_worker(worker)
        worker.start()

    def _on_mic_test_done(self, request_id: int, ok: bool, result: Any) -> None:
        if self._closing or request_id != self._active_request:
            return
        self.pet.set_listening(False)
        self._set_busy(False)
        self.add_message(
            str(result or "Mikrofon testi tamamlanamadı senpai. 🎤"), "bot"
        )
        self.pet.set_emotion("happy" if ok else "sad")
        self._resume_wake_after_audio_capture()

    def _select_microphone(self) -> None:
        if self._closing or self._busy or self._listening:
            return
        self.show_chat()
        names = self.voice.list_microphones()
        if not names:
            self.add_message(
                "Mikrofon listesi alınamadı senpai. PyAudio ve mikrofon iznini kontrol et. 🎤",
                "bot",
            )
            return
        items = ["Varsayılan mikrofon"] + [
            f"{i}: {name}" for i, name in enumerate(names)
        ]
        current = (
            0
            if self.voice.microphone_index is None
            else self.voice.microphone_index + 1
        )
        current = max(0, min(current, len(items) - 1))
        choice, ok = QInputDialog.getItem(
            self.chat_window, "Mikrofon Seç", "Giriş cihazı:", items, current, False
        )
        if not ok:
            return
        index = None if choice == items[0] else items.index(choice) - 1
        self.voice.set_microphone_index(index)
        was_wake = self.voice.wake_word_active
        if was_wake:
            self.voice.stop_wake_word_listener()
            self.voice.start_wake_word_listener()
        self._update_mic_indicator()
        self.add_message(
            f"Mikrofon seçildi: {choice}. Test etmek için 🎙️ Mikrofon Testi'ni kullan senpai. 🎧",
            "bot",
        )

    def _check_groq(self) -> None:
        if self._closing or self._busy:
            return
        self.show_chat()
        self._run_tool(
            self.brain.diagnose_connection,
            "Groq bağlantısı kontrol ediliyor…",
            speak=False,
        )

    def _on_wake_word(self, remainder: str = "") -> None:
        if self._closing or self._busy or self._listening or self.voice.is_speaking:
            return
        self.proactive.user_interacted()
        self.show_chat()
        if remainder:
            self._send_message(remainder)
            return
        # Do not speak first: TTS would occupy the microphone and could swallow
        # the command immediately after "Hey Nora". Show a visual cue instead.
        self.pet.show_speech("Efendim senpai? 🎙️", 2500)
        self._start_listening()

    def _on_speaking_started(self) -> None:
        if self._closing:
            return
        self.pet.set_speaking(True)
        self._sync_pause()

    def _on_speaking_finished(self) -> None:
        if self._closing:
            return
        self.pet.set_speaking(False)
        if (
            self._wake_followup
            and not self.voice.is_speaking
            and not self._busy
            and not self._listening
        ):
            self._wake_followup = False
            self._start_listening()
        self._sync_pause()

    def _on_voice_error(self, message: str) -> None:
        if self._closing:
            return
        self.mic_indicator.setToolTip(message)
        if message not in self._notified_errors:
            self._notified_errors.add(message)
            if self.tray.isVisible():
                self.tray.showMessage(
                    "Nora · Ses", message, QSystemTrayIcon.Warning, 5000
                )
            if not self._busy:
                self.status_label.setText(message[:70])

    # ----------------------------------------------------------------- proactive
    def _on_proactive(self, text: str) -> None:
        if self._closing or self._busy or self._listening or self.voice.is_speaking:
            return
        self.pet.show_speech(text, 6500)
        self.voice.speak(text)
        if self.chat_window.isVisible():
            self.add_message(text, "bot")

    def _on_timer(self, message: str) -> None:
        if self._closing:
            return
        text = f"⏰ {message}"
        self.pet.show_speech(text, 8000)
        self.pet.set_emotion("surprised")
        self.voice.speak(text)
        if self.chat_window.isVisible():
            self.add_message(text, "bot")
        if self.tray.isVisible():
            self.tray.showMessage(
                "Nora · Hatırlatıcı", text, QSystemTrayIcon.Information, 8000
            )

    def _greet(self) -> None:
        if self._closing:
            return
        text = startup_greeting()
        self.pet.show_speech(text, 6500)
        self.add_message(text, "bot")
        if not self.brain.available:
            self.add_message(
                "Heh, şu an çevrimdışı temel komut modundayım. Serbest sohbet için GROQ_API_KEY ayarla senpai. 🐾",
                "bot",
            )
        self.voice.speak(text)
        if self.tray.isVisible():
            mic = (
                "· yerel 'Hey Nora' bekçisi açık 🎙️"
                if self.voice.wake_word_active
                else "· sürekli dinleme kapalı"
            )
            self.tray.showMessage(
                "Nora burada 💕",
                f"Masaüstündeyim {mic}",
                QSystemTrayIcon.Information,
                4000,
            )

    # --------------------------------------------------------------------- quick
    def _quick_search(self) -> None:
        if self._busy:
            return
        self.show_chat()
        text, ok = QInputDialog.getText(self.chat_window, "Ara", "Ne arayım senpai? 🔍")
        if ok and text.strip():
            self._run_tool(lambda: self.tools.search(text.strip()), "Aramayı açıyorum…")

    def _quick_time(self) -> None:
        self.show_chat()
        now = datetime.now()
        text = f"Saat {now:%H:%M}, senpai. Tarih {now:%d.%m.%Y}. ⏰"
        self.add_message(text, "bot")
        self.pet.show_speech(text, 4500)
        self.voice.speak(text)

    def _show_notes(self) -> None:
        self.show_chat()
        self.add_message(self.tools.list_notes(), "bot")
        self.proactive.user_interacted()

    def _show_system_info(self) -> None:
        if self._busy:
            return
        self.show_chat()
        self._run_tool(self.tools.system_info, "Sistem bilgisi okunuyor…", speak=False)

    def _quick_weather(self) -> None:
        if self._busy:
            return
        self.show_chat()
        city, ok = QInputDialog.getText(
            self.chat_window,
            "Hava Durumu",
            "Hangi şehir senpai? 🌤️",
            text=self._last_city,
        )
        if ok and city.strip():
            self._last_city = city.strip()
            self._run_tool(
                lambda: self.tools.weather(city.strip()), "Havaya bakıyorum…"
            )

    def _reset_memory(self) -> None:
        self.brain.reset_memory()
        self._clear_messages()
        self.add_message(
            "Hafızamı sıfırladım senpai. Yeni bir sayfa açtık... notların hâlâ bende. 🐾",
            "bot",
        )
        self.pet.set_emotion("happy")
        self.proactive.user_interacted()

    # ----------------------------------------------------------------- lifecycle
    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self.proactive.stop()
        self.voice.close()
        self.tools.close()
        self.brain.close()
        self.pet.shutdown()
        self.chat_window.removeEventFilter(self)
        self.chat_header.removeEventFilter(self)
        self.chat_window.hide()
        self.tray.hide()
        self.hide()
        if not self._workers:
            app = QApplication.instance()
            if app:
                app.quit()
        else:
            logger.info("Arka plan işlemi bitince Nora kapanacak.")

    def closeEvent(self, event) -> None:
        if self._closing:
            event.accept()
        else:
            event.ignore()
            self.hide()

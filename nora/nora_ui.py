"""Chat window, tray icon and thread-safe integration of every Nora module."""

from __future__ import annotations

import json
import logging
import os
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Callable

from PyQt5.QtCore import QEvent, QPoint, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QFileDialog,
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

from .nora_activities import ModeManager, NumberGame, ReminderScheduler, WordGame
from .nora_briefing import daily_summary, morning_briefing, weekly_plan
from .nora_brain import ChatReply, NoraBrain
from .nora_calendar import format_events, format_free_slots, read_ics
from .nora_commands import normalize_text, parse_direct_command, parse_direct_sequence
from .nora_companion import mood_summary, reaction_details
from .nora_desktop import DesktopLayouts
from .nora_files import NoraFiles
from .nora_hotkeys import DEFAULT_PTT_KEY, PushToTalkHotkey
from .nora_local_ai import LocalOCR, LocalSpeech
from .nora_local_search import format_results, search_store
from .nora_personality import (
    EMOTIONS,
    CommandError,
    SAFE_ROUTINE_COMMANDS,
    normalize_command,
    startup_greeting,
)
from .nora_pet import NoraPet
from .nora_pixel_art import PixelCharacter
from .nora_proactive import ProactiveEngine
from .nora_settings_dialog import NoraSettingsDialog
from .nora_store import NoraStore, default_data_dir, now_local, parse_datetime
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
    data_dir: str | Path | None = None


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
            message = (
                str(exc)[:500]
                if isinstance(exc, ValueError)
                else "Bu işlemi tamamlayamadım senpai. Araç/izin desteğini kontrol et. 🐾"
            )
            self.done.emit(self.request_id, False, message)


class TextWorker(QThread):
    done = pyqtSignal(int, object)

    def __init__(
        self,
        brain: NoraBrain,
        text: str,
        action: str,
        language: str,
        request_id: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.brain, self.text, self.action = brain, text, action
        self.language, self.request_id = language, request_id

    def run(self) -> None:
        try:
            reply = self.brain.assist_text(self.text, self.action, self.language)
        except Exception as exc:
            logger.warning("Metin worker hatası: %s", type(exc).__name__)
            reply = ChatReply(
                "Metni işleyemedim senpai. Tekrar dener misin?", "sad", error=True
            )
        self.done.emit(self.request_id, reply)


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
        self._stt_test_request = 0
        self._conversation_active = False
        self._continuous_empty = 0
        self._ptt_active = False
        self._request_seq = 0
        self._active_request = 0
        self._workers: set[QThread] = set()
        self._message_rows: list[QWidget] = []
        self._chat_user_moved = False
        self._chat_drag_offset: QPoint | None = None
        self._notified_errors: set[str] = set()
        self._last_city = ""
        self._pending_commands: deque[dict[str, Any]] = deque(maxlen=24)
        self._last_repeatable: dict[str, Any] | None = None
        self._recent_commands: deque[dict[str, Any]] = deque(maxlen=8)
        self.data_dir = (
            Path(self.options.data_dir).expanduser()
            if self.options.data_dir is not None
            else default_data_dir()
        )
        self.store = NoraStore(self.data_dir / "state.json")
        self.files = NoraFiles()
        self.desktop_layouts = DesktopLayouts()
        self.local_speech = LocalSpeech(
            self.data_dir / "models",
            model_name=self.store.preference("whisper_model"),
            device=self.store.preference("whisper_device"),
        )
        self.ocr = LocalOCR()
        self.reminders = ReminderScheduler(self.store, parent=self)
        self.modes = ModeManager(self.store)
        self.game = WordGame()
        self.number_game = NumberGame()
        self.settings_dialog: NoraSettingsDialog | None = None

        wake = (
            self.options.wake_word
            if self.options.wake_word is not None
            else env_bool("NORA_WAKE_WORD", self.store.preference("wake_word"))
        )
        tts = (
            self.options.tts
            if self.options.tts is not None
            else env_bool("NORA_TTS", self.store.preference("tts"))
        )
        proactive_enabled = (
            self.options.proactive
            if self.options.proactive is not None
            else env_bool("NORA_PROACTIVE", self.store.preference("proactive"))
        )
        self.brain = NoraBrain(
            offline=self.options.offline or env_bool("NORA_OFFLINE", False)
        )
        self.tools = NoraTools(
            allow_code=self.options.allow_code, store=self.store, parent=self
        )
        self.voice = NoraVoice(
            tts_enabled=tts,
            stt_backend=self.store.preference("stt_backend"),
            local_speech=self.local_speech,
            speech_rate=self.store.preference("speech_rate"),
            speech_volume=self.store.preference("speech_volume"),
            voice_id=self.store.preference("voice_id"),
            parent=self,
        )
        self.pet = NoraPet()
        self.pet.set_appearance(self.store.preferences)
        self.proactive = ProactiveEngine(self.tools, store=self.store, parent=self)
        self.ptt_hotkey = PushToTalkHotkey(self)
        self._build_chat()
        self._build_tray()
        self._connect_signals()
        self._refresh_personal_context()
        self.reminders.start()

        self.tts_action.setChecked(tts)
        self.wake_action.setChecked(bool(wake))
        self.proactive_action.setChecked(proactive_enabled)
        self._apply_mode_appearance()
        if wake:
            self.voice.start_wake_word_listener()
        if proactive_enabled:
            self.proactive.start()
        self._sync_voice_modes()
        self._update_mic_indicator()
        self._update_tts_indicator()
        try:
            self.store.update_preferences(
                {"wake_word": bool(wake), "tts": tts, "proactive": proactive_enabled}
            )
        except ValueError as exc:
            logger.warning("Tercihler kaydedilemedi: %s", exc)
        if self.store.load_warning:
            QTimer.singleShot(
                1200, lambda: self.add_message(self.store.load_warning, "bot")
            )
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
        self.speaker_indicator = QLabel("🔊")
        self.speaker_indicator.setFont(self._emoji_font(10))
        self.speaker_indicator.setToolTip("Sesli yanıt durumu")
        header_layout.addWidget(self.speaker_indicator)
        header_layout.addStretch()
        for text, tip, slot in (
            ("📸", "Ekran görüntüsü al ve analiz et", self._analyze_screen),
            ("📷", "Kameradan bir kare analiz et", self._analyze_camera),
            ("🎤", "Sesli komut ver", lambda: self._start_listening()),
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
            (
                "🎮 Oyun",
                lambda: self._execute_command({"command": "game", "action": "start"}),
            ),
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
        painter = QPainter(pixmap)
        PixelCharacter.draw_icon(painter, 64, self.store.preferences)
        painter.end()
        return QIcon(pixmap)

    def _movement_menu(self, menu: QMenu) -> None:
        movements = menu.addMenu("🐾 Hareketler")
        movements.setStyleSheet(self._menu_style())
        for label, action in (
            ("😴 Uyu", "sleep"),
            ("☀️ Uyan", "wake"),
            ("🚶 Dolaş", "walk"),
            ("✋ Dur", "stop"),
            ("🦘 Zıpla", "jump"),
            ("💃 Dans et", "dance"),
            ("🪑 Otur", "sit"),
            ("👋 Selam ver", "wave"),
            ("💜 Başını okşa", "pet"),
        ):
            movements.addAction(
                label,
                lambda a=action: self._execute_command(
                    {"command": "pet_action", "action": a}
                ),
            )
        monitors = movements.addMenu("🖥️ Monitöre geç")
        monitors.setStyleSheet(self._menu_style())

        def fill():
            monitors.clear()
            for index, screen in enumerate(self.pet._monitor_screens(), 1):
                monitors.addAction(
                    f"{index}. {screen.name() or 'Ekran'}",
                    lambda target=index: self._execute_command(
                        {"command": "move_monitor", "target": target}
                    ),
                )
            monitors.addAction(
                "Sonraki monitör",
                lambda: self._execute_command(
                    {"command": "move_monitor", "target": "next"}
                ),
            )
            monitors.addAction(
                "Ana monitör",
                lambda: self._execute_command(
                    {"command": "move_monitor", "target": "primary"}
                ),
            )

        monitors.aboutToShow.connect(fill)

    def _mode_menu(self, menu: QMenu) -> None:
        modes = menu.addMenu("🎯 Modlar")
        modes.setStyleSheet(self._menu_style())
        for label, mode in (
            ("Odak / çalışma", "focus"),
            ("Oyun", "game"),
            ("Sessiz", "quiet"),
            ("Normal · önceki ayarlara dön", "normal"),
        ):
            modes.addAction(
                label,
                lambda m=mode: self._execute_command({"command": "mode", "mode": m}),
            )

    def _feature_menu(self, menu: QMenu) -> None:
        features = menu.addMenu("✨ Özellikler")
        features.setStyleSheet(self._menu_style())
        for label, slot in (
            (
                "⏰ Hatırlatıcılar",
                lambda: self._execute_command(
                    {"command": "reminder", "action": "list"}
                ),
            ),
            (
                "✅ Görevler",
                lambda: self._execute_command({"command": "task", "action": "list"}),
            ),
            (
                "🧠 Kayıtlı hafıza",
                lambda: self._execute_command({"command": "memory", "action": "list"}),
            ),
            (
                "📅 Bugünkü takvim",
                lambda: self._execute_command(
                    {"command": "calendar", "action": "today"}
                ),
            ),
            ("📅 Takvim dosyası içe aktar", self._import_calendar),
            (
                "🖥️ Pencere düzenini kaydet",
                lambda: self._execute_command(
                    {"command": "desktop_layout", "action": "save", "name": "son"}
                ),
            ),
            (
                "🖥️ Pencere düzenini geri yükle",
                lambda: self._execute_command(
                    {"command": "desktop_layout", "action": "restore", "name": "son"}
                ),
            ),
            (
                "🔁 Rutinler",
                lambda: self._execute_command({"command": "routine", "action": "list"}),
            ),
            ("🔁 Rutin oluştur", self._create_routine),
            (
                "📸 Ekrandaki yazıları yerelde oku",
                lambda: self._execute_command({"command": "screen_text"}),
            ),
            ("📁 Dosya bul", self._find_files_dialog),
            (
                "↩️ Son dosya taşımayı geri al",
                lambda: self._execute_command({"command": "undo_files"}),
            ),
            (
                "🎮 Kelime oyunu",
                lambda: self._execute_command({"command": "game", "action": "start"}),
            ),
            (
                "🔢 Sayı tahmin oyunu",
                lambda: self._execute_command(
                    {"command": "number_game", "action": "start"}
                ),
            ),
            (
                "🌅 Sabah brifingi",
                lambda: self._execute_command(
                    {"command": "briefing", "action": "morning"}
                ),
            ),
            (
                "🌙 Gün sonu özeti",
                lambda: self._execute_command(
                    {"command": "briefing", "action": "summary"}
                ),
            ),
            (
                "🗓️ Haftalık plan",
                lambda: self._execute_command(
                    {"command": "briefing", "action": "weekly"}
                ),
            ),
            ("🔎 Yerel ara", self._local_search_dialog),
            (
                "🔐 İzin merkezi",
                lambda: self._execute_command(
                    {"command": "permissions", "action": "list"}
                ),
            ),
            (
                "🧾 Son işlemler",
                lambda: self._execute_command(
                    {"command": "permissions", "action": "audit"}
                ),
            ),
            ("📦 Veriyi dışa aktar", self._export_data),
        ):
            features.addAction(label, slot)
        clipboard = features.addMenu("📋 Pano yardımı (onaylı)")
        clipboard.setStyleSheet(self._menu_style())
        for label, action in (
            ("Özetle", "summarize"),
            ("Çevir", "translate"),
            ("Düzenle", "rewrite"),
            ("Biçimlendir", "format"),
        ):
            clipboard.addAction(
                label,
                lambda a=action: self._execute_command(
                    {"command": "clipboard_help", "action": a}
                ),
            )
        live = features.addMenu("🔁 Canlı mod / otonomi")
        live.setStyleSheet(self._menu_style())
        for label, key in (
            ("Sürekli konuşma", "continuous_conversation"),
            ("Bas-konuş tuşu", "push_to_talk"),
            ("Ara sıra ekranımı incele", "auto_screen_watch"),
            ("Ara sıra kameradan beni incele", "auto_camera_watch"),
            ("Kendi kendine müzik/video aç", "auto_media"),
        ):
            action = live.addAction(label)
            action.setCheckable(True)
            action.blockSignals(True)
            action.setChecked(bool(self.store.preference(key)))
            action.blockSignals(False)
            action.toggled.connect(
                lambda checked, k=key: self._apply_settings({k: bool(checked)})
            )
        live.addSeparator()
        live.addAction(
            "🎧 Müzik aç",
            lambda: self._execute_command({"command": "media", "action": "music"}),
        )
        live.addAction(
            "🍿 Video aç",
            lambda: self._execute_command({"command": "media", "action": "video"}),
        )
        media_controls = features.addMenu("🎧 Medya kontrolü")
        media_controls.setStyleSheet(self._menu_style())
        for label, action in (
            ("⏯️ Çal/Duraklat", "play_pause"),
            ("⏭️ Sonraki", "next"),
            ("⏮️ Önceki", "previous"),
            ("⏹️ Durdur", "stop"),
            ("🎵 Şu an ne çalıyor?", "now_playing"),
        ):
            media_controls.addAction(
                label,
                lambda a=action: self._execute_command(
                    {"command": "media_control", "action": a}
                ),
            )
        companion = features.addMenu("💜 Companion")
        companion.setStyleSheet(self._menu_style())
        for label, action in (
            ("Modun nasıl?", "mood"),
            ("☕ Kahve ver", "coffee"),
            ("🍪 Kurabiye ver", "cookie"),
            ("🏆 Ödül ver", "reward"),
            ("🥺 Seni özledim", "miss"),
        ):
            companion.addAction(
                label,
                lambda a=action: self._execute_command(
                    {"command": "companion", "action": a}
                ),
            )
        features.addSeparator()
        features.addAction("🎤 Yerel ses modelini indir", self._download_local_model)
        features.addAction("🔊 Konuşma sesi seç", self._select_output_voice)
        features.addAction("⚙️ Ayarlar", self._show_settings)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self._tray_icon(), self)
        self.tray.setToolTip("Nora 💕")
        menu = QMenu()
        menu.setStyleSheet(self._menu_style())
        menu.addAction("Göster", self._show_pet)
        menu.addAction("Sohbet Aç", self.show_chat)
        menu.addAction("Ekran Analiz", self._analyze_screen)
        menu.addAction("Sesli Komut", lambda: self._start_listening())
        menu.addAction(
            "🗣️ Ses Tanıma Testi", lambda: self._start_listening(recognition_test=True)
        )
        menu.addAction("🎙️ Mikrofon Testi", self._test_microphone)
        menu.addAction("🔊 Sesli Yanıt Testi", self._test_speech)
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
        menu.addAction("Sohbet Geçmişini Sıfırla", self._reset_memory)
        menu.addAction("Kayıtlı Kişisel Hafızayı Sil", self._forget_all_memories)
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
        self.pet.double_clicked.connect(self._on_double_click)
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
        self.reminders.reminder_due.connect(self._on_timer)
        self.reminders.scheduler_error.connect(
            lambda message: self.add_message(message, "bot")
        )
        self.proactive.speak_requested.connect(self._on_proactive)
        self.proactive.autonomy_requested.connect(self._on_autonomy_request)
        self.ptt_hotkey.pressed.connect(self._on_ptt_pressed)
        self.ptt_hotkey.released.connect(self._on_ptt_released)
        self.ptt_hotkey.error.connect(self._on_ptt_error)
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

    def _sync_voice_modes(self) -> None:
        prefs = self.store.preferences
        if prefs.get("push_to_talk"):
            self.ptt_hotkey.start(prefs.get("ptt_key") or DEFAULT_PTT_KEY)
        else:
            self.ptt_hotkey.stop()
        if not prefs.get("continuous_conversation"):
            self._conversation_active = False
            self._continuous_empty = 0
            self._wake_followup = False
        self._update_mic_indicator()

    def _queue_conversation_followup(self) -> None:
        if (
            self._closing
            or not self._conversation_active
            or not self.store.preference("continuous_conversation")
        ):
            return
        if self.voice.is_speaking:
            self._wake_followup = True
            return
        QTimer.singleShot(450, self._conversation_followup)

    def _conversation_followup(self) -> None:
        if (
            self._closing
            or self._busy
            or self._listening
            or self.voice.is_speaking
            or not self._conversation_active
            or not self.store.preference("continuous_conversation")
        ):
            return
        self._start_listening()

    def _on_ptt_pressed(self) -> None:
        if self._closing or self._busy or self._listening:
            return
        if self.voice.is_speaking:
            self._wake_followup = False
            self.voice.stop_speaking()
        self.show_chat()
        self.proactive.user_interacted()
        self._conversation_active = bool(
            self.store.preference("continuous_conversation")
        )
        self._continuous_empty = 0
        self._listening = True
        self._ptt_active = True
        self._pause_wake_for_audio()
        self._set_busy(True, "Bas-konuş 🎙️ konuş, bırakınca cevaplayayım…")
        self.mic_button.setStyleSheet("background: #e53950; border-color: #ff8fa3;")
        self.pet.set_listening(True)
        self.pet.show_speech("Bas-konuş 🎙️", 2000)
        request_id = self._next_request()
        if not self.voice.start_push_to_talk(request_id):
            self._ptt_active = False
            self._listening = False
            self.mic_button.setStyleSheet("")
            self.pet.set_listening(False)
            self._set_busy(False)
            self._resume_wake_after_audio_capture()
            self.add_message(
                "Bas-konuşu başlatamadım senpai. Mikrofon meşgul veya ses açık. 🎤",
                "bot",
            )
        self._sync_pause()

    def _on_ptt_released(self) -> None:
        if self._ptt_active:
            self.status_label.setText("Sesini işliyorum…")
            self.voice.stop_push_to_talk()

    def _on_ptt_error(self, message: str) -> None:
        if not self._closing:
            self.add_message(message, "bot", speak=False)
            self._update_mic_indicator()

    def _on_autonomy_request(self, kind: str) -> None:
        if (
            self._closing
            or self._busy
            or self._listening
            or self.voice.is_speaking
            or self.modes.current != "normal"
        ):
            return
        if kind == "screen":
            if not self.brain.available:
                return
            self.add_message(
                "👀 Ekranına merak sardım, biraz bakıyorum…", "bot", speak=False
            )
            self._analyze_screen(
                "Kullanıcı otomatik ekran incelemeyi açıkça açtı. Ekranda ne olduğunu "
                "kısaca ve doğal biçimde yorumla; hassas veri/parola isteme."
            )
        elif kind == "camera":
            if not self.brain.available:
                return
            self.add_message(
                "📷 Kameradan sana bakıyorum, izin vermiştin~", "bot", speak=False
            )
            self._analyze_camera(
                "Kullanıcı otomatik kamera incelemeyi açıkça açtı. Kamerada ne gördüğünü "
                "kısaca, saygılı ve doğal biçimde anlat; fiziksel deneyim uydurma."
            )
        elif kind == "media":
            music = self.proactive.rng.random() < 0.6
            query = (
                self.proactive.rng.choice(
                    ["lofi hip hop", "synthwave", "anime opening", "jazz coffee"]
                )
                if music
                else self.proactive.rng.choice(
                    ["sevimli kediler", "lofi girl", "pixel art animation"]
                )
            )
            self._execute_command(
                {
                    "command": "media",
                    "action": "music" if music else "video",
                    "query": query,
                }
            )

    def _media_command(self, cmd: dict[str, Any]) -> None:
        action = cmd.get("action", "music")
        query = str(cmd.get("query", ""))[:200]
        if action == "music":
            self.pet.perform_action("dance")
            self._report(
                f"Canım müzik istedi; Spotify'da “{query or 'lofi hip hop'}” açıyorum 🎧"
            )
            self._run_tool(
                lambda: self.tools.spotify_search(query), "Spotify açılıyor…"
            )
        else:
            self.pet.perform_action("watch")
            self._report(
                f"Bir video açıyorum, birlikte izleyelim~ 🍿 “{query or 'sevimli kediler'}”"
            )
            self._run_tool(
                lambda: self.tools.video_search(query), "Video araması açılıyor…"
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
        if not busy:
            QTimer.singleShot(0, self._drain_commands)

    def add_message(
        self, text: str, sender: str = "bot", *, speak: bool = True
    ) -> None:
        original = str(text).strip()
        if not original:
            return
        text = original
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
        if sender == "bot" and speak:
            self._say(original)
        if (
            sender == "bot"
            and self._conversation_active
            and not original.startswith("🎙️")
            and self.store.preference("continuous_conversation")
        ):
            self._queue_conversation_followup()

    def _say(self, text: str) -> bool:
        if self._closing:
            return False
        if not self.voice.tts_enabled:
            self._update_tts_indicator()
            return False
        return self.voice.speak(str(text))

    def _update_tts_indicator(self) -> None:
        if not hasattr(self, "speaker_indicator"):
            return
        enabled = bool(self.voice.tts_enabled)
        volume = self.store.preference("speech_volume")
        mode = self.modes.current
        if enabled and volume > 0:
            self.speaker_indicator.setText("🔊")
            tip = "Sesli yanıt açık."
        else:
            self.speaker_indicator.setText("🔇")
            reasons = []
            if not enabled:
                reasons.append(
                    {
                        "focus": "Odak modu",
                        "quiet": "Sessiz mod",
                        "game": "Oyun modu",
                    }.get(mode, "Sesli yanıt")
                    + " kapalı"
                )
            if volume <= 0:
                reasons.append("Ses düzeyi 0")
            tip = (
                " · ".join(reasons)
                + ". 'sesli yanıtı aç' diyebilir veya tepsi menüsünden açabilirsin."
            )
        self.speaker_indicator.setToolTip(tip)
        if hasattr(self, "tray"):
            self.tray.setToolTip(f"Nora 💕 · {tip}")

    def _test_speech(self) -> None:
        self.show_chat()
        self.add_message(self.voice.diagnose_speech(), "bot", speak=False)
        if not self.voice.tts_enabled:
            self.add_message(
                "Sesli yanıt şu an kapalı senpai. 'sesli yanıtı aç' de ya da tepsideki 🔊 kutusunu işaretle. Odak/sessiz moddaysan 'normal mod' de. 🎧",
                "bot",
                speak=False,
            )
            return
        if not self._say(
            "Ses testi yapıyorum senpai. Beni duyuyorsan sesli yanıtlar çalışıyor demektir. "
        ):
            self.add_message(
                "Ses motoru kuyruğa yanıt ekleyemedi. 🔊", "bot", speak=False
            )

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
        menu.addAction("🎤 Sesli Komut", lambda: self._start_listening())
        menu.addAction(
            "🗣️ Ses Tanıma Testi", lambda: self._start_listening(recognition_test=True)
        )
        menu.addAction("🎙️ Mikrofon Testi", self._test_microphone)
        menu.addAction("🎧 Mikrofon Seç", self._select_microphone)
        menu.addAction("🩺 Groq Bağlantısı", self._check_groq)
        menu.addAction("💻 Sistem Bilgisi", self._show_system_info)
        menu.addAction("📝 Notlarım", self._show_notes)
        menu.addAction("🌤️ Hava Durumu", self._quick_weather)
        self._movement_menu(menu)
        self._mode_menu(menu)
        self._feature_menu(menu)
        emotions = menu.addMenu("Duygu Değiştir")
        emotions.setStyleSheet(self._menu_style())
        for key, data in EMOTIONS.items():
            emotions.addAction(
                f"{data['emoji']} {key}", lambda k=key: self.pet.set_emotion(k)
            )
        menu.addSeparator()
        menu.addAction("Sohbet Geçmişini Sıfırla", self._reset_memory)
        menu.addAction("Kayıtlı Kişisel Hafızayı Sil", self._forget_all_memories)
        menu.addAction("Kapat", self.shutdown)
        menu.exec_(point)

    def _update_mic_indicator(self) -> None:
        active = self.voice.wake_word_active
        self.mic_indicator.setText("🎙️" if active else "🔇")
        backend = (
            "Whisper · yerel komut STT"
            if self.voice.stt_backend == "local"
            else "Google · komut STT internet kullanır"
        )
        self.mic_indicator.setToolTip(
            (
                "Yerel 'Hey Nora' bekçisi AÇIK · şu an komut dinlemiyor. "
                if active
                else "Hey Nora bekçisi kapalı · yalnızca 🎤 ile dinlenir. "
            )
            + backend
        )

    def _toggle_tts(self, enabled: bool) -> None:
        self.voice.set_tts_enabled(enabled)
        try:
            self.store.set_preference("tts", bool(enabled))
        except ValueError as exc:
            self.status_label.setText(str(exc)[:70])
        self._update_tts_indicator()
        self._sync_pause()

    def _toggle_wake(self, enabled: bool) -> None:
        try:
            self.store.set_preference("wake_word", bool(enabled))
        except ValueError as exc:
            self.status_label.setText(str(exc)[:70])
        if enabled:
            self.voice.start_wake_word_listener()
        else:
            self.voice.stop_wake_word_listener()
        QTimer.singleShot(250, self._update_mic_indicator)

    def _toggle_proactive(self, enabled: bool) -> None:
        try:
            self.store.set_preference("proactive", bool(enabled))
        except ValueError as exc:
            self.status_label.setText(str(exc)[:70])
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

    def _send_message(self, text: str, *, transcript_note: str = "") -> None:
        if self._closing or not text.strip():
            return
        if self.store.preference("continuous_conversation"):
            self._conversation_active = True
            self._continuous_empty = 0
        direct = parse_direct_command(text)
        command = None
        sequence_commands: list[dict[str, Any]] = []
        if direct is not None:
            try:
                command = normalize_command(direct.command)
            except CommandError as exc:
                self.add_message(str(exc), "bot")
                return
        elif (
            normalize_text(text) in {"tekrar", "tekrar yap", "bir daha", "aynısını yap"}
            and self._last_repeatable
        ):
            command = dict(self._last_repeatable)
        if direct is None and command is None:
            sequence = parse_direct_sequence(text)
            if sequence:
                try:
                    sequence_commands = [
                        normalize_command(item.command) for item in sequence
                    ]
                    command = sequence_commands[0]
                except CommandError as exc:
                    self.add_message(str(exc), "bot")
                    return
        requested = sequence_commands or ([command] if command is not None else [])
        immediate = bool(requested) and all(
            item["command"]
            in {
                "pet_action",
                "move_monitor",
                "settings",
                "mode",
                "memory",
                "task",
                "reminder",
                "stt_backend",
                "game",
                "stt_test",
                "media",
                "briefing",
                "companion",
                "permissions",
                "export_data",
                "local_search",
                "media_control",
                "number_game",
            }
            for item in requested
        )
        if self._listening or (self._busy and not immediate):
            self.status_label.setText("Bir saniye senpai, önce bu işi bitireyim…")
            return
        self.proactive.user_interacted()
        self.add_message(text, "user")
        self.pet.show_user_speech(text)
        if transcript_note:
            self.add_message(transcript_note, "bot", speak=False)
        if sequence_commands:
            for item in sequence_commands:
                self._execute_command(item)
            return
        if command is not None:
            self._execute_command(command)
            return
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
        self.add_message(text, "bot", speak=speak)
        self.pet.set_emotion("happy" if ok else "sad")

    def _execute_command(self, command: dict[str, Any]) -> None:
        try:
            cmd = normalize_command(command)
        except CommandError as exc:
            self.add_message(f"Hımm, bu komutu çalıştıramam: {exc}", "bot")
            return
        name = cmd["command"]
        self._remember_command(cmd)
        self.store.add_audit("command", json.dumps(cmd, ensure_ascii=False)[:240])
        if name in {"pet_action", "move_monitor"}:
            self._last_repeatable = dict(cmd)
            if name == "pet_action":
                result = self.pet.perform_action(cmd["action"])
            else:
                ok, result = self.pet.move_to_monitor(cmd["target"])
                if ok and self.chat_window.isVisible():
                    self._position_chat()
            self._report(result)
        elif name == "mode":
            self._activate_mode(cmd["mode"])
        elif name == "memory":
            self._memory_command(cmd)
        elif name == "reminder":
            self._reminder_command(cmd)
        elif name == "task":
            self._task_command(cmd)
        elif name == "speech_test":
            self._test_speech()
        elif name == "stt_test":
            self._start_listening(recognition_test=True)
        elif name == "media":
            self._media_command(cmd)
        elif name == "briefing":
            self._briefing_command(cmd)
        elif name == "companion":
            self._companion_command(cmd)
        elif name == "permissions":
            self._permissions_command(cmd)
        elif name == "export_data":
            self._export_data()
        elif name == "local_search":
            self._local_search_command(cmd)
        elif name == "media_control":
            self._run_tool(
                lambda: self.tools.media_control(cmd["action"]),
                "Medya kontrol ediliyor…",
            )
        elif name == "number_game":
            self._number_game_command(cmd)
        elif name == "settings":
            if cmd["action"] == "list":
                prefs = self.store.preferences
                self._report(
                    "\n".join(
                        f"{key}: {value}"
                        for key, value in prefs.items()
                        if key not in {"voice_id", "appearance_version"}
                    ),
                    speak=False,
                )
            else:
                self._apply_settings({cmd["key"]: cmd["value"]})
                self._report(f"Ayarı kaydettim: {cmd['key']} = {cmd['value']}.")
        elif name == "stt_backend":
            self._apply_settings({"stt_backend": cmd["backend"]})
            message = (
                "Komut sesi artık cihazında işlenecek. Buluta ses gönderilmeyecek. 🎤"
                if cmd["backend"] == "local"
                else "Komut sesi Google STT kullanacak; yalnızca dinleme sırasında ses gönderilir."
            )
            if cmd["backend"] == "local" and not self.local_speech.cached():
                message += " Önce menüden yerel ses modelini indir senpai."
            self._report(message)
        elif name == "clipboard_help":
            self._clipboard_help(cmd)
        elif name == "screen_text":
            self._analyze_screen_text(cmd.get("prompt", ""))
        elif name == "find_files":
            self._run_tool(
                lambda: self.files.find(
                    cmd["query"], cmd["directory"], cmd["extension"], cmd["limit"]
                ),
                "Dosyalar aranıyor…",
                speak=False,
            )
        elif name == "move_files":
            self._preview_file_move(cmd)
        elif name == "undo_files":
            if self._confirm(
                "Dosya taşımayı geri al",
                "Son Nora taşımasını, hedefler değişmediyse geri alayım mı?",
            ):
                self._run_tool(self.files.undo, "Dosyalar geri alınıyor…")
        elif name == "routine":
            self._routine_command(cmd)
        elif name == "calendar":
            events = self.store.upcoming_events(
                days=1 if cmd["action"] in {"today", "free"} else 7
            )
            result = (
                format_free_slots(
                    events, duration_minutes=cmd.get("duration_minutes", 30)
                )
                if cmd["action"] == "free"
                else format_events(events)
            )
            self._report(result, speak=False)
        elif name == "desktop_layout":
            self._desktop_layout_command(cmd)
        elif name == "game":
            action = cmd["action"]
            result = (
                self.game.start()
                if action == "start"
                else self.game.hint()
                if action == "hint"
                else self.game.stop()
                if action == "stop"
                else self.game.guess(cmd.get("answer", ""))
            )
            self.show_chat()
            self._report(result)
        elif name == "screenshot":
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
                else self.tools.delete_note(cmd["id"])
                if cmd["action"] == "delete"
                else self.tools.list_notes()
            )
            self.add_message(result, "bot")
        elif name == "set_timer":
            self._reminder_command(
                {
                    "command": "reminder",
                    "action": "add",
                    "text": cmd["message"],
                    "seconds": cmd["seconds"],
                    "recurrence": "none",
                }
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

    # ------------------------------------------------------- personal features
    def _remember_command(self, cmd: dict[str, Any]) -> None:
        if cmd["command"] in SAFE_ROUTINE_COMMANDS and cmd["command"] != "routine":
            self._recent_commands.append(dict(cmd))

    def _briefing_command(self, cmd: dict[str, Any]) -> None:
        action = cmd.get("action", "morning")
        result = (
            morning_briefing(self.store)
            if action == "morning"
            else daily_summary(self.store)
            if action == "summary"
            else weekly_plan(self.store)
        )
        self._report(result, speak=False)

    def _companion_command(self, cmd: dict[str, Any]) -> None:
        action = cmd.get("action", "mood")
        if action in {"mood", "affection"}:
            self._report(
                mood_summary(
                    self.store.companion_state,
                    self.store.preference("address", "senpai"),
                ),
                speak=False,
            )
            return
        if not self.store.preference("companion_reactions", True):
            self._report(
                "Duygusal companion tepkileri kapalı senpai. 'duygusal tepkileri aç' diyebilirsin. 💜",
                speak=False,
            )
            return
        event = "pet" if action == "reward" else action
        line, emotion, delta = reaction_details(event)
        state = self.store.record_companion(event, affection_delta=delta, mood=emotion)
        self.pet.set_emotion(emotion)
        suffix = (
            f" (bağlılık {state['affection']}/100)" if action == "affection" else ""
        )
        self._report(line + suffix)

    def _permissions_command(self, cmd: dict[str, Any]) -> None:
        action = cmd.get("action", "list")
        if action == "audit":
            entries = self.store.audit_log
            result = (
                "Son işlemler 🧾\n"
                + "\n".join(
                    f"• {item['at']} · {item['detail']}" for item in entries[-12:]
                )
                if entries
                else "Denetim kaydı boş."
            )
            self._report(result, speak=False)
        elif action == "clear_audit":
            if self._confirm(
                "Denetim kaydını temizle",
                "Yerel denetim kaydını silmemi onaylıyor musun?",
            ):
                self.store.clear_audit()
                self._report("Denetim kaydını temizledim. 🧾")
        else:
            prefs = self.store.preferences
            keys = (
                "wake_word",
                "continuous_conversation",
                "push_to_talk",
                "auto_screen_watch",
                "auto_camera_watch",
                "auto_media",
                "media_keys",
                "companion_reactions",
                "briefing_on_startup",
                "audit_log",
            )
            result = "İzin merkezi 🔐\n" + "\n".join(
                f"• {key}: {'açık' if prefs.get(key) else 'kapalı'}" for key in keys
            )
            result += "\nNot: Kamera/ekran otonomisi varsayılan kapalıdır; açmak için açık onayın gerekir."
            self._report(result, speak=False)

    def _export_data(self) -> None:
        self.show_chat()
        path, _ = QFileDialog.getSaveFileName(
            self.chat_window,
            "Nora verisini dışa aktar",
            "nora-export.json",
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(self.store.export_data(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._report(f"Verilerini dışa aktardım: {path} 📦")
        except OSError as exc:
            self._report(f"Dışa aktaramadım senpai: {exc}")

    def _local_search_command(self, cmd: dict[str, Any]) -> None:
        results = search_store(
            self.store,
            cmd["query"],
            scope=cmd.get("scope", "all"),
            limit=cmd.get("limit", 8),
        )
        self._report(format_results(cmd["query"], results), speak=False)

    def _local_search_dialog(self) -> None:
        self.show_chat()
        query, ok = QInputDialog.getText(
            self.chat_window, "Yerel ara", "Not/hafıza/görevlerde ne arayım?"
        )
        if ok and query.strip():
            self._execute_command(
                {"command": "local_search", "query": query.strip(), "scope": "all"}
            )

    def _number_game_command(self, cmd: dict[str, Any]) -> None:
        action = cmd["action"]
        result = (
            self.number_game.start()
            if action == "start"
            else self.number_game.stop()
            if action == "stop"
            else self.number_game.guess(cmd.get("guess", 0))
        )
        self.show_chat()
        self._report(result)

    def _report(self, text: str, *, speak: bool = True, bubble: bool = True) -> None:
        self.add_message(str(text), "bot", speak=speak)
        if bubble:
            self.pet.show_speech(str(text), 5500)
        # add_message above already enforces the central spoken-reply policy.

    def _queue_commands(self, commands: list[dict[str, Any]]) -> None:
        self._pending_commands.extend(
            normalize_command(command) for command in commands
        )
        self._drain_commands()

    def _drain_commands(self) -> None:
        if self._closing or self._busy or self._listening or not self._pending_commands:
            return
        command = self._pending_commands.popleft()
        self._execute_command(command)
        if self._pending_commands:
            QTimer.singleShot(150, self._drain_commands)

    def _refresh_personal_context(self) -> None:
        prefs = self.store.preferences
        tone = {
            "tsundere": "Kişilik tonu: tsundere; dozunda takıl ama kullanıcı üzgünse nazik ol.",
            "sweet": "Kişilik tonu: tatlı ve destekleyici; alaycı/tsundere çıkışları yapma.",
            "serious": "Kişilik tonu: ciddi, kısa ve net; Japonca/emoji çok az.",
        }[prefs["tone"]]
        address = (
            f"Kullanıcıya '{prefs['address']}' diye hitap et; başka hitapı zorlama."
        )
        self.brain.set_personal_context(
            "\n".join((tone, address, self.store.memory_context()))
        )

    def _apply_settings(self, values: dict[str, Any]) -> None:
        try:
            self.store.update_preferences(values)
            prefs = self.store.preferences
            self.voice.configure_speech(
                prefs["speech_rate"], prefs["speech_volume"], prefs["voice_id"]
            )
            self.local_speech.configure(prefs["whisper_model"], prefs["whisper_device"])
            self.pet.set_appearance(prefs)
            self.tray.setIcon(self._tray_icon())
            for action, key in (
                (self.tts_action, "tts"),
                (self.wake_action, "wake_word"),
                (self.proactive_action, "proactive"),
            ):
                action.setChecked(bool(prefs[key]))
            self._apply_mode_appearance()
            self._refresh_personal_context()
            self._update_mic_indicator()
            self._update_tts_indicator()
            self._sync_voice_modes()
        except (ValueError, CommandError) as exc:
            self._report(f"Ayar uygulanamadı senpai: {exc}")

    def _apply_mode_appearance(self) -> None:
        mode = self.modes.current
        self.pet.set_appearance(
            {
                "autonomous": self.store.preference("autonomous")
                if mode == "normal"
                else False
            }
        )
        self._update_tts_indicator()
        if mode != "normal":
            self.status_label.setText(
                {
                    "focus": "Odak modu · sessiz companion",
                    "game": "Oyun modu · proaktif konuşma kapalı",
                    "quiet": "Sessiz mod",
                }[mode]
            )

    def _activate_mode(self, mode: str) -> None:
        try:
            settings = self.modes.activate(mode)
            self._apply_settings(settings)
            if mode == "focus":
                minutes = self.store.preference("focus_minutes")
                self.store.add_reminder(
                    f"Odak süresi bitti senpai! {minutes} dakikayı tamamladın. Bir mola ver. 💜",
                    now_local() + timedelta(minutes=minutes),
                )
                self.pet.perform_action("sit")
                message = f"{minutes} dakikalık odak modu başladı. Sesli/proaktif konuşma kapalı; hatırlatıcılar çalışır. Uygulamaları kapatmadım. 🎯"
            elif mode == "game":
                message = "Oyun modu açık. Proaktif konuşma kapalı; uygulamaları veya sistem sesini değiştirmedim. 'Kelime oyunu başlat' veya 'lofi çal' diyebilirsin. 🎮"
            elif mode == "quiet":
                message = "Sessiz mod açık. Sesli yanıt ve proaktif konuşma kapalı; yazılı komutlar çalışır. 🤫"
            else:
                message = "Normal moda döndüm; mod öncesi ses/proaktif ayarlarını geri yükledim. 🐾"
            self._report(message)
        except ValueError as exc:
            self._report(str(exc))

    def _memory_command(self, cmd: dict[str, Any]) -> None:
        action = cmd["action"]
        try:
            if action == "clear":
                if not self._confirm(
                    "Kişisel hafızayı sil",
                    "Açıkça kaydettiğin tüm kişisel bilgileri silmemi istiyor musun? Notlar ve görevler silinmez.",
                ):
                    return
                self.store.clear_memories()
                result = "Kayıtlı kişisel bilgileri sildim senpai. Notların duruyor."
            elif action == "add":
                self.store.remember(cmd["key"], cmd["value"])
                result = f"Kaydettim senpai: {cmd['key']} = {cmd['value']} 🧠"
            elif action == "delete":
                result = (
                    "Bu bilgiyi unuttum senpai."
                    if self.store.forget(cmd["key"])
                    else "Bu anahtarla kayıtlı bilgi bulamadım."
                )
            elif action == "get":
                value = self.store.memories.get(
                    cmd["key"].translate(str.maketrans("Iİ", "ıi")).lower()
                )
                result = (
                    f"{cmd['key']}: {value['value']}"
                    if value
                    else "Bu bilgi kayıtlı değil senpai."
                )
            else:
                memories = self.store.memories
                result = (
                    "Açıkça kaydettiğin bilgiler 🧠\n"
                    + "\n".join(
                        f"• {key}: {item['value']}" for key, item in memories.items()
                    )
                    if memories
                    else "Henüz kişisel bilgi kaydetmedim. 'Bunu hatırla: kahvem = şekersiz' diyebilirsin. Sohbetini kendiliğinden kaydetmiyorum."
                )
            self._refresh_personal_context()
            self._report(result, speak=action != "list")
        except ValueError as exc:
            self._report(str(exc))

    def _reminder_command(self, cmd: dict[str, Any]) -> None:
        try:
            if cmd["action"] == "list":
                result = self.reminders.listing()
            elif cmd["action"] == "cancel":
                result = (
                    "Hatırlatıcıyı iptal ettim senpai."
                    if self.store.cancel_reminder(cmd["id"])
                    else "Bu hatırlatıcıyı bulamadım senpai."
                )
            else:
                due = (
                    now_local() + timedelta(seconds=cmd["seconds"])
                    if "seconds" in cmd
                    else parse_datetime(cmd["due_at"])
                )
                item = self.store.add_reminder(
                    cmd["text"], due, cmd.get("recurrence", "none")
                )
                result = f"⏰ {due:%d.%m.%Y %H:%M} için kaydettim: {item['text']} [{item['id']}]. Nora yeniden başlasa da kalır."
            self._report(result, speak=cmd["action"] != "list")
        except (ValueError, TypeError) as exc:
            self._report(f"Hatırlatıcı kaydedilemedi: {exc}")

    def _task_command(self, cmd: dict[str, Any]) -> None:
        try:
            action = cmd["action"]
            if action == "list":
                tasks = self.store.tasks
                result = (
                    "Görevlerin ✅\n"
                    + "\n".join(
                        f"{index}. {'☑' if task['done'] else '☐'} {task['text']} [{task['id']}]"
                        for index, task in enumerate(tasks, 1)
                    )
                    if tasks
                    else "Görev listen boş. 'Görev ekle: raporu bitir' diyebilirsin."
                )
            elif action == "add":
                self.store.add_task(cmd["text"])
                result = f"Görevi ekledim: {cmd['text']} ✅"
            elif action == "from_note":
                result = f"{self.store.tasks_from_note(cmd['id'])} görev çıkardım senpai. Listelemek için 'görevler' de."
            elif action == "delete":
                result = (
                    "Görevi sildim."
                    if self.store.delete_task(cmd["id"])
                    else "Görev bulunamadı."
                )
            else:
                result = (
                    "Görevi güncelledim senpai. ✅"
                    if self.store.complete_task(cmd["id"], action == "complete")
                    else "Görev bulunamadı."
                )
            self._report(result, speak=action != "list")
        except ValueError as exc:
            self._report(str(exc))

    def _routine_command(self, cmd: dict[str, Any]) -> None:
        try:
            if cmd["action"] == "save_recent":
                steps = [dict(item) for item in self._recent_commands][-8:]
                if not steps:
                    raise ValueError(
                        "Kaydedilecek güvenli son komut yok. Önce birkaç komut çalıştır senpai."
                    )
                self.store.save_routine(cmd["name"], steps)
                result = f"Son {len(steps)} güvenli komutu '{cmd['name']}' rutini olarak kaydettim. 🔁"
            elif cmd["action"] == "add":
                self.store.save_routine(cmd["name"], cmd["steps"])
                result = f"'{cmd['name']}' rutinini kaydettim. Çalıştırmadan önce adım özetini ve onayını gösteririm. 🔁"
            elif cmd["action"] == "list":
                routines = self.store.routines
                result = (
                    "Rutinlerin 🔁\n"
                    + "\n".join(
                        f"• {item['name']}: "
                        + ", ".join(step["command"] for step in item["steps"])
                        for item in routines
                    )
                    if routines
                    else "Rutin yok. Menüden oluşturabilir veya örneğin 'sabah rutini oluştur' diyebilirsin."
                )
            elif cmd["action"] == "delete":
                result = (
                    "Rutini sildim."
                    if self.store.delete_routine(cmd["name"])
                    else "Rutin bulunamadı."
                )
            else:
                steps = self.store.routine(cmd["name"])
                summary = json.dumps(steps, ensure_ascii=False, indent=2)[:2500]
                if not self._confirm(
                    "Rutini çalıştır",
                    f"'{cmd['name']}' şu adımları yapacak:\n{summary}\n\nBaşlatayım mı?",
                ):
                    return
                self._queue_commands(steps)
                result = f"'{cmd['name']}' rutinini başlattım senpai. 🔁"
            self._report(result, speak=cmd["action"] != "list")
        except (ValueError, CommandError) as exc:
            self._report(str(exc))

    def _create_routine(self) -> None:
        self.show_chat()
        name, ok = QInputDialog.getText(self.chat_window, "Rutin oluştur", "Rutin adı:")
        if not ok or not name.strip():
            return
        text, ok = QInputDialog.getMultiLineText(
            self.chat_window,
            "Rutin adımları",
            "Her satıra bir komut yaz (en fazla 8):",
            "chrome aç\nmüzik lofi çal\notur",
        )
        if not ok:
            return
        try:
            steps = []
            for line in text.splitlines():
                if not line.strip():
                    continue
                direct = parse_direct_command(line)
                command = (
                    direct.command
                    if direct
                    else self.brain._offline_reply(line).command
                )
                if command is None:
                    raise ValueError(f"Komut anlaşılmadı: {line[:80]}")
                steps.append(command)
            self._routine_command(
                {"command": "routine", "action": "add", "name": name, "steps": steps}
            )
        except (ValueError, CommandError) as exc:
            self._report(str(exc))

    def _clipboard_help(self, cmd: dict[str, Any]) -> None:
        text = self.tools.clipboard_paste()
        if not text.strip():
            self._report(
                "Panoda okunabilir metin yok senpai. Önce bir metin kopyala. 📋"
            )
            return
        if len(text) > 12000:
            self._report(
                "Pano metni 12000 karakterden uzun; daha kısa bir bölüm kopyala."
            )
            return
        if not self.brain.available:
            self._report(
                "Pano analizi için Groq gerekli senpai. Panoyu değiştirmedim veya geçmişini kaydetmedim."
            )
            return
        language = cmd.get("target_language", "")
        if cmd["action"] == "translate" and not language:
            language, accepted = QInputDialog.getItem(
                self.chat_window,
                "Çeviri dili",
                "Hangi dile çevireyim?",
                ["İngilizce", "Türkçe", "Almanca", "Fransızca", "Japonca"],
                0,
                True,
            )
            if not accepted:
                return
        if self._confirm(
            "Panodaki metni analiz et",
            f"Bu metin Groq'a gönderilecek (pano geçmişi tutulmaz):\n\n{text[:600]}\n\nDevam edeyim mi?",
        ):
            self._run_text_assist(
                text, cmd["action"], cmd.get("target_language", "Türkçe")
            )

    def _run_text_assist(self, text: str, action: str, context: str) -> None:
        if self._closing or self._busy:
            return
        self._set_busy(True, "Metni işliyorum…")
        request_id = self._next_request()
        worker = TextWorker(self.brain, text, action, context, request_id)
        worker.done.connect(self._on_image_done)
        self._track_worker(worker)
        worker.start()

    def _analyze_screen_text(self, prompt: str = "") -> None:
        if self._closing or self._busy or self._listening:
            return
        self._set_busy(True, "Ekran yazıları yerelde okunacak…")
        request_id = self._next_request()
        chat_visible, pet_visible = self.chat_window.isVisible(), self.pet.isVisible()
        self.chat_window.hide()
        self.pet.hide()
        QTimer.singleShot(
            500,
            lambda: self._capture_screen_text(
                request_id, prompt, chat_visible, pet_visible
            ),
        )

    def _capture_screen_text(
        self, request_id: int, prompt: str, chat_visible: bool, pet_visible: bool
    ) -> None:
        if self._closing:
            return
        worker = ToolWorker(self.tools.screenshot, request_id)
        worker.done.connect(
            lambda rid, ok, image, p=prompt, c=chat_visible, v=pet_visible: (
                self._on_screen_text_captured(rid, ok, image, p, c, v)
            )
        )
        self._track_worker(worker)
        worker.start()

    def _on_screen_text_captured(
        self,
        request_id: int,
        ok: bool,
        image: Any,
        prompt: str,
        chat_visible: bool,
        pet_visible: bool,
    ) -> None:
        if self._closing or request_id != self._active_request:
            return
        if pet_visible:
            self.pet.show()
        if chat_visible:
            self.chat_window.show()
            self._position_chat()
        if not ok or not image:
            self._set_busy(False)
            self._report("Ekran yazılarını okuyamadım; ekran görüntüsü alınamadı. 📸")
            return
        self.status_label.setText("OCR cihazında çalışıyor; görüntü buluta gitmiyor…")
        worker = ToolWorker(lambda: self.ocr.read(image), request_id)
        worker.done.connect(
            lambda rid, success, text, p=prompt: self._on_ocr_done(
                rid, success, text, p
            )
        )
        self._track_worker(worker)
        worker.start()

    def _on_ocr_done(self, request_id: int, ok: bool, text: Any, prompt: str) -> None:
        if self._closing or request_id != self._active_request:
            return
        self._set_busy(False)
        if not ok:
            self._report(
                "Yerel OCR çalışmadı. Özellik bağımlılıkları için requirements-local.txt kurulumunu kontrol et senpai. 📸"
            )
            return
        text = str(text)
        self._report("Yerelde okuduğum ekran yazıları 📸\n" + text, speak=False)
        if self.brain.available and "bulamadım" not in text[:100]:
            if self._confirm(
                "Okunan yazıları analiz et",
                f"Yerelde okunan metin Groq'a gönderilecek. Görüntü gönderilmez.\n\n{text[:600]}\n\nAnaliz edeyim mi?",
            ):
                self._run_text_assist(
                    text,
                    "screen",
                    prompt
                    or "Ekrandaki yazıları kısaca açıkla; hata varsa çözüm öner.",
                )

    def _show_settings(self) -> None:
        self.show_chat()
        if self.settings_dialog is not None:
            self.settings_dialog.close()
            self.settings_dialog.deleteLater()
        self.settings_dialog = NoraSettingsDialog(
            self.store, on_apply=self._apply_settings, parent=self.chat_window
        )
        self.settings_dialog.show()
        self.settings_dialog.raise_()

    def _download_local_model(self) -> None:
        model = self.store.preference("whisper_model")
        if self._confirm(
            "Yerel ses modelini indir",
            f"Whisper '{model}' modeli Hugging Face'ten indirilecek. İnternet ve disk alanı gerekir; ses kayıtların gönderilmez. İndireyim mi?",
        ):
            self._run_tool(
                lambda: self.local_speech.ensure_model(download=True),
                "Yerel ses modeli indiriliyor…",
                speak=False,
            )

    def _select_output_voice(self) -> None:
        if self._busy or self._closing:
            return
        self._set_busy(True, "Sistem sesleri listeleniyor…")
        request_id = self._next_request()
        worker = ToolWorker(self.voice.list_output_voices, request_id)
        worker.done.connect(self._on_output_voices)
        self._track_worker(worker)
        worker.start()

    def _on_output_voices(self, request_id: int, ok: bool, voices: Any) -> None:
        if self._closing or request_id != self._active_request:
            return
        self._set_busy(False)
        if not ok or not voices:
            self._report(
                "Ses listesi alınamadı. pyttsx3 / Windows SAPI seslerini kontrol et senpai."
            )
            return
        items = ["Otomatik seçim"] + [
            f"{voice['name']} · {voice['id']}" for voice in voices
        ]
        choice, accepted = QInputDialog.getItem(
            self.chat_window, "Konuşma sesi", "Ses seç:", items, 0, False
        )
        if accepted:
            voice_id = (
                "" if choice == items[0] else voices[items.index(choice) - 1]["id"]
            )
            self._apply_settings({"voice_id": voice_id})
            self._report(
                "Konuşma sesini ayarladım senpai. Bir sonraki yanıtta kullanacağım. 🔊"
            )

    def _import_calendar(self) -> None:
        self.show_chat()
        path, _ = QFileDialog.getOpenFileName(
            self.chat_window, "Takvim içe aktar", str(Path.home()), "iCalendar (*.ics)"
        )
        if not path:
            return
        self._set_busy(True, "Takvim yerelde okunuyor…")
        request_id = self._next_request()
        worker = ToolWorker(lambda: read_ics(path), request_id)
        worker.done.connect(self._on_calendar_import)
        self._track_worker(worker)
        worker.start()

    def _on_calendar_import(self, request_id: int, ok: bool, events: Any) -> None:
        if self._closing or request_id != self._active_request:
            return
        self._set_busy(False)
        try:
            result = (
                f"{self.store.import_events(events if ok else [])} etkinliği yerel takvime ekledim. 📅"
                if ok
                else "Takvim okunamadı; geçerli bir .ics dosyası ve requirements-local.txt kurulumunu kontrol et."
            )
        except (ValueError, TypeError, KeyError) as exc:
            result = str(exc)
        self._report(result)

    def _find_files_dialog(self) -> None:
        self.show_chat()
        query, ok = QInputDialog.getText(
            self.chat_window, "Dosya bul", "Dosya adında aranacak metin:"
        )
        if not ok or not query.strip():
            return
        labels = [
            self.files.LABELS[key] for key in ("downloads", "documents", "desktop")
        ]
        label, ok = QInputDialog.getItem(
            self.chat_window, "Klasör", "Nerede arayım?", labels, 0, False
        )
        if ok:
            directory = ("downloads", "documents", "desktop")[labels.index(label)]
            self._execute_command(
                {"command": "find_files", "query": query, "directory": directory}
            )

    def _preview_file_move(self, cmd: dict[str, Any]) -> None:
        try:
            moves, conflicts = self.files.preview_move(
                cmd["selection"], cmd["destination"], cmd["folder"]
            )
            summary = "\n".join(f"{source} → {target}" for source, target in moves)
            if not moves:
                self._report("Taşınacak dosya yok. " + " ".join(conflicts))
                return
            if self._confirm(
                "Dosyaları taşı",
                f"Silme/üzerine yazma yapılmaz:\n{summary}\n"
                + "\n".join(conflicts)
                + "\n\nTaşıyayım mı?",
            ):
                self._run_tool(
                    lambda: self.files.move(
                        cmd["selection"], cmd["destination"], cmd["folder"]
                    ),
                    "Dosyalar taşınıyor…",
                )
        except ValueError as exc:
            self._report(str(exc))

    def _desktop_layout_command(self, cmd: dict[str, Any]) -> None:
        try:
            if cmd["action"] == "list":
                self._report(
                    "Pencere düzenleri 🖥️\n"
                    + "\n".join(item["name"] for item in self.store.layouts),
                    speak=False,
                )
            elif cmd["action"] == "delete":
                self._report(
                    "Düzeni sildim."
                    if self.store.delete_layout(cmd["name"])
                    else "Düzen bulunamadı."
                )
            elif cmd["action"] == "save":
                self._set_busy(True, "Pencere konumları yerelde kaydediliyor…")
                request_id = self._next_request()
                worker = ToolWorker(self.desktop_layouts.snapshot, request_id)
                worker.done.connect(
                    lambda rid, ok, entries, name=cmd["name"]: self._on_layout_saved(
                        rid, ok, entries, name
                    )
                )
                self._track_worker(worker)
                worker.start()
            else:
                entries = self.store.layout(cmd["name"])
                if self._confirm(
                    "Pencere düzenini geri yükle",
                    "Yalnızca hâlâ açık ve başlığı eşleşen pencereler taşınacak; uygulama açılmaz/kapatılmaz:\n"
                    + self.desktop_layouts.preview(entries),
                ):
                    self._run_tool(
                        lambda: self.desktop_layouts.restore(entries),
                        "Pencereler eski konumuna alınıyor…",
                    )
        except ValueError as exc:
            self._report(str(exc))

    def _on_layout_saved(
        self, request_id: int, ok: bool, entries: Any, name: str
    ) -> None:
        if self._closing or request_id != self._active_request:
            return
        self._set_busy(False)
        try:
            if not ok:
                raise ValueError(str(entries))
            self.store.save_layout(name, entries)
            result = f"'{name}' pencere düzenini yerelde kaydettim ({len(entries)} pencere). Geri yüklemeden önce yine onay isterim. 🖥️"
        except (ValueError, TypeError, KeyError) as exc:
            result = str(exc)
        self._report(result)

    def _on_double_click(self) -> None:
        action = self.store.preference("double_click_action")
        if action == "game":
            self._execute_command({"command": "game", "action": "start"})
        elif action == "pet" and self.store.preference("pet_reactions"):
            self._report(self.pet.perform_action("pet"))
        else:
            self.show_chat()

    def _forget_all_memories(self) -> None:
        self._memory_command({"command": "memory", "action": "clear"})

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

    # --------------------------------------------------------------------- voice
    def _start_listening(self, *, recognition_test: bool = False) -> None:
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
        self._stt_test_request = request_id if recognition_test else 0
        if recognition_test:
            self.pet.show_speech("Ses tanıma testi 🎙️ 'Hey Nora, uyu' de.", 4000)
        if not self.voice.listen_async(request_id):
            self._stt_test_request = 0
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
        self._ptt_active = False
        self.mic_button.setStyleSheet("")
        self.pet.set_listening(False)
        self._set_busy(False)
        self.proactive.user_interacted()
        repair = self.voice.last_transcript
        if repair is not None and repair.request_id != request_id:
            repair = None
        if request_id == self._stt_test_request:
            self._stt_test_request = 0
            if text:
                original = repair.original if repair is not None else text
                message = (
                    f"🎙️ Ses tanıma testi\nDuyduğum: “{original}”\nAnladığım: “{text}”"
                )
                if repair is not None and repair.address_corrected:
                    message += "\nAdını yanlış duymuşum; Nora olarak düzelttim."
                self.add_message(message, "bot", speak=False)
                self.pet.show_speech(f"Şöyle anladım: {text}", 5000)
                self.pet.set_emotion("happy")
            else:
                self.add_message(
                    error or "Ses tanıma testinde ses duyamadım senpai. 🎤", "bot"
                )
                self.pet.set_emotion("sad")
            self._resume_wake_after_audio_capture()
            self._sync_pause()
            return
        if (
            self.store.preference("continuous_conversation")
            and self._conversation_active
        ):
            if text:
                self._continuous_empty = 0
            else:
                self._continuous_empty += 1
                if self._continuous_empty >= 2:
                    self._conversation_active = False
                    self._wake_followup = False
                    self.add_message(
                        "Sürekli konuşmayı durdurdum senpai. İstersen 'sürekli konuşma modu' ile tekrar aç. 🎙️",
                        "bot",
                        speak=False,
                    )
        if text:
            self._send_message(
                text, transcript_note=repair.notice() if repair is not None else ""
            )
        else:
            message = error or "Seni duyamadım senpai. Bir daha dener misin? 🎤"
            self.add_message(message, "bot")
            self.pet.set_emotion("sad")
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
        if self.store.preference("continuous_conversation"):
            self._conversation_active = True
            self._continuous_empty = 0
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
        if hasattr(self, "speaker_indicator"):
            self.speaker_indicator.setText("🔊")
            self.speaker_indicator.setToolTip("Nora konuşuyor…")
        self._sync_pause()

    def _on_speaking_finished(self) -> None:
        if self._closing:
            return
        self.pet.set_speaking(False)
        self._update_tts_indicator()
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
        if hasattr(self, "speaker_indicator"):
            self.speaker_indicator.setToolTip(message)
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
        self._say(text)
        if self.chat_window.isVisible():
            self.add_message(text, "bot", speak=False)

    def _on_timer(self, message: str) -> None:
        if self._closing:
            return
        text = f"⏰ {message}"
        self.pet.show_speech(text, 8000)
        self.pet.set_emotion("surprised")
        self._say(text)
        if self.chat_window.isVisible():
            self.add_message(text, "bot", speak=False)
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
        if self.store.preference("briefing_on_startup"):
            QTimer.singleShot(
                1800, lambda: self._briefing_command({"action": "morning"})
            )
        if self.tray.isVisible():
            mic = (
                "· yerel 'Hey Nora' bekçisi açık 🎙️"
                if self.voice.wake_word_active
                else "· sürekli dinleme kapalı"
            )
            silent = "" if self.voice.tts_enabled else " · sesli yanıt kapalı 🔇"
            self.tray.showMessage(
                "Nora burada 💕",
                f"Masaüstündeyim {mic}{silent}",
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
            "Sohbet geçmişini sıfırladım senpai. Açıkça kaydettiğin kişisel bilgiler, notlar ve hatırlatıcılar hâlâ duruyor. 🐾",
            "bot",
        )
        self.pet.set_emotion("happy")
        self.proactive.user_interacted()

    # ----------------------------------------------------------------- lifecycle
    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._pending_commands.clear()
        if self.settings_dialog is not None:
            self.settings_dialog.close()
        self.proactive.stop()
        self.ptt_hotkey.stop()
        self.reminders.stop()
        self.local_speech.close()
        self.ocr.close()
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

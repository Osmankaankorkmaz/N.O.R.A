"""Nora's personal panel: the glass card that opens on a double click.

Three pages, one consistent look:

* **Ruh hâli** — how she feels right now, and a picker to change it.
* **Anılar** — the things she has been told and remembers about you.
* **Özel** — nickname, relationship tone, her speaking style and voice.

Design notes

* Everything is drawn on the same translucent card as the chat window, so the
  two windows look like one product.
* Moods are *buttons*, not a dropdown: the user should see the character react
  immediately.
* Nothing here talks to the network.  Preferences are written through
  :class:`nora.nora_store.NoraStore`, so they survive a restart.
"""

from __future__ import annotations

from typing import Any, Iterable

from PyQt5 import sip
from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
)
from PyQt5.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .nora_glass import glass_style
from .nora_pixel_art import PixelCharacter

#: Moods offered in the panel, in the order they are shown.
MOODS: tuple[tuple[str, str], ...] = (
    ("happy", "Mutlu"),
    ("love", "Sevgi dolu"),
    ("shy", "Utangaç"),
    ("thinking", "Düşünceli"),
    ("surprised", "Şaşkın"),
    ("angry", "Kızgın"),
    ("sad", "Üzgün"),
    ("sleepy", "Uykulu"),
)

#: Relationship tones.  The value is the key stored in the preferences.
TONES: tuple[tuple[str, str], ...] = (
    ("friend", "Arkadaş"),
    ("close", "Yakın"),
    ("playful", "Şakacı"),
    ("formal", "Resmî"),
)

SECTIONS: tuple[tuple[str, str], ...] = (
    ("mood", "Ruh hâli"),
    ("memories", "Anılar"),
    ("personal", "Özel"),
)


class MoodChip(QPushButton):
    """A mood button carrying a tiny 8-bit portrait of that mood."""

    def __init__(self, mood: str, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.mood = mood
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(38)
        self.setObjectName("moodChip")
        self.setStyleSheet(
            """
            QPushButton#moodChip {
                background: rgba(255,255,255,225);
                border: 1px solid rgba(24,18,40,30);
                border-radius: 12px;
                padding: 6px 12px 6px 34px;
                color: #1b1725;
                font-size: 12px;
                text-align: left;
            }
            QPushButton#moodChip:hover { background: #ffffff; border-color: rgba(123,92,255,110); }
            QPushButton#moodChip:checked {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #7b5cff, stop:1 #ff4d94);
                border: 1px solid rgba(123,92,255,150);
                color: #ffffff;
            }
            """
        )

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.save()
        # Head only, at 1x: a 40x54 figure would dwarf the 38 px chip.
        painter.setClipRect(0, 0, 40, self.height())
        painter.translate(2, (self.height() - 22) // 2 - 2)
        PixelCharacter().draw_scaled(
            painter,
            scale=1,
            state="idle",
            emotion=self.mood,
            frame=0,
            appearance={"outfit": "cream"},
            animations=False,
        )
        painter.restore()


class MemoryRow(QFrame):
    """One remembered fact: the text, when it was learned, and a delete action."""

    deleted = pyqtSignal(str)

    def __init__(self, key: str, text: str, when: str = "", parent=None) -> None:
        super().__init__(parent)
        self.key = key
        self.setObjectName("memoryRow")
        self.setStyleSheet(
            """
            QFrame#memoryRow {
                background: rgba(255,255,255,235);
                border: 1px solid rgba(24,18,40,26);
                border-radius: 10px;
            }
            QFrame#memoryRow QLabel { color: #1b1725; font-size: 12px; }
            QFrame#memoryRow QLabel#when { color: #8b8399; font-size: 10px; }
            """
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 7, 8, 7)
        row.setSpacing(8)

        body = QVBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(1)
        label = QLabel(text)
        label.setWordWrap(True)
        body.addWidget(label)
        if when:
            stamp = QLabel(when)
            stamp.setObjectName("when")
            body.addWidget(stamp)
        row.addLayout(body, 1)

        remove = QPushButton("✕")
        remove.setCursor(Qt.PointingHandCursor)
        remove.setFixedSize(24, 24)
        remove.setStyleSheet(
            """
            QPushButton {
                background: rgba(24,18,40,16);
                border: none; border-radius: 12px; color: #1b1725;
            }
            QPushButton:hover { background: rgba(255,120,150,110); }
            """
        )
        remove.clicked.connect(lambda: self.deleted.emit(self.key))
        row.addWidget(remove, 0, Qt.AlignTop)


class PersonalPanel(QWidget):
    """The double-click card: mood, memories and personal preferences."""

    mood_chosen = pyqtSignal(str)
    preference_changed = pyqtSignal(str, object)
    memory_deleted = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window
            | Qt.CustomizeWindowHint
            | Qt.WindowTitleHint
            | Qt.WindowSystemMenuHint
            | Qt.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Nora · özel panel")
        try:
            from .nora_brand import logo_pixmap
            from PyQt5.QtGui import QIcon

            self.setWindowIcon(QIcon(logo_pixmap(256)))
        except Exception:  # pragma: no cover - an icon must never block a window
            pass
        self.setMinimumSize(460, 520)
        self.setStyleSheet(glass_style())

        from .nora_brand import CARD_RADIUS

        # Same corner language as the launch card and the chat window.
        self.setStyleSheet(
            self.styleSheet()
            + f"""
QFrame#glassCard {{
    background: transparent;
    border-radius: {int(CARD_RADIUS)}px;
}}
"""
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)

        self.card = QFrame()
        self.card.setObjectName("glassCard")
        outer.addWidget(self.card)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # ---- header: live portrait + her name ----------------------------
        header = QHBoxLayout()
        header.setSpacing(12)
        self.portrait = PortraitBadge()
        header.addWidget(self.portrait)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        name = QLabel("Nora")
        name.setStyleSheet("color:#1b1725; font-size:19px; font-weight:600;")
        self.mood_line = QLabel("şu an: mutlu")
        self.mood_line.setStyleSheet("color:#6a6380; font-size:11px;")
        titles.addWidget(name)
        titles.addWidget(self.mood_line)
        header.addLayout(titles, 1)
        layout.addLayout(header)

        # ---- section tabs ------------------------------------------------
        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self._tab_buttons: list[QPushButton] = []
        for index, (key, label) in enumerate(SECTIONS):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(32)
            button.setObjectName("sectionTab")
            button.setStyleSheet(
                """
                QPushButton#sectionTab {
                    background: rgba(255,255,255,220);
                    border: 1px solid rgba(24,18,40,26);
                    border-radius: 10px;
                    color: #1b1725;
                    font-size: 12px;
                    padding: 4px 14px;
                }
                QPushButton#sectionTab:hover { background: rgba(123,92,255,26); }
                QPushButton#sectionTab:checked {
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #7b5cff, stop:1 #ff4d94);
                    border-color: rgba(123,92,255,120);
                    color: #ffffff;
                }
                """
            )
            button.clicked.connect(lambda _=False, i=index: self.show_section(i))
            tabs.addWidget(button)
            self._tab_buttons.append(button)
        tabs.addStretch(1)
        layout.addLayout(tabs)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_mood_page())
        self.pages.addWidget(self._build_memory_page())
        self.pages.addWidget(self._build_personal_page())
        layout.addWidget(self.pages, 1)

        footer = QLabel(
            "Değişiklikler anında uygulanır · buradaki her şey yalnızca bu cihazda saklanır"
        )
        footer.setStyleSheet("color:#8b8399; font-size:10px;")
        footer.setWordWrap(True)
        layout.addWidget(footer)

        self._mood = "happy"
        self.show_section(0)

    # ------------------------------------------------------------------ pages
    def _build_mood_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        hint = QLabel("Nasıl hissetmesini istersin?")
        hint.setStyleSheet("color:#1b1725; font-size:12px;")
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(7)
        self._mood_chips: dict[str, MoodChip] = {}
        for index, (mood, label) in enumerate(MOODS):
            chip = MoodChip(mood, f"  {label}")
            chip.setMinimumWidth(140)
            chip.clicked.connect(lambda _=False, m=mood: self._choose_mood(m))
            grid.addWidget(chip, index // 2, index % 2)
            self._mood_chips[mood] = chip
        layout.addLayout(grid)

        layout.addSpacing(6)
        note = QLabel(
            "Nora normalde ruh hâlini konuşmanın duygusuna göre kendisi seçer. "
            "Buradan sabitlersen, sen değiştirene kadar o ruh hâlinde kalır."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#6a6380; font-size:11px; line-height:150%;")
        layout.addWidget(note)
        layout.addStretch(1)
        return page

    def _build_memory_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)

        self.memory_count = QLabel("Henüz bir şey hatırlamıyor.")
        self.memory_count.setStyleSheet("color:#1b1725; font-size:12px;")
        layout.addWidget(self.memory_count)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        self.memory_host = QWidget()
        self.memory_host.setStyleSheet("background: transparent;")
        self.memory_layout = QVBoxLayout(self.memory_host)
        self.memory_layout.setContentsMargins(0, 0, 0, 0)
        self.memory_layout.setSpacing(6)
        self.memory_layout.addStretch(1)
        scroll.setWidget(self.memory_host)
        layout.addWidget(scroll, 1)
        return page

    def _build_personal_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        layout.addWidget(self._field_label("Sana nasıl hitap etsin?"))
        self.nickname = QLineEdit()
        self.nickname.setPlaceholderText("ör. senpai, canım, adın…")
        self.nickname.setStyleSheet(self._input_style())
        self.nickname.editingFinished.connect(
            lambda: self.preference_changed.emit(
                "nickname", self.nickname.text().strip()
            )
        )
        layout.addWidget(self.nickname)

        layout.addWidget(self._field_label("İlişki tonu"))
        tone_row = QHBoxLayout()
        tone_row.setSpacing(6)
        self._tone_buttons: dict[str, QPushButton] = {}
        for key, label in TONES:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(30)
            button.setStyleSheet(self._chip_style())
            button.clicked.connect(lambda _=False, k=key: self._choose_tone(k))
            tone_row.addWidget(button)
            self._tone_buttons[key] = button
        layout.addLayout(tone_row)

        layout.addWidget(self._field_label("Konuşma tarzı"))
        self.style_note = QLabel()
        self.style_note.setWordWrap(True)
        self.style_note.setStyleSheet("color:#6a6380; font-size:11px;")
        layout.addWidget(self.style_note)

        layout.addSpacing(4)
        layout.addWidget(self._field_label("Sesi"))
        voice_row = QHBoxLayout()
        self.voice_toggle = QPushButton("Sesli konuşma")
        self.voice_toggle.setCheckable(True)
        self.voice_toggle.setCursor(Qt.PointingHandCursor)
        self.voice_toggle.setMinimumHeight(32)
        self.voice_toggle.setStyleSheet(self._chip_style())
        self.voice_toggle.clicked.connect(
            lambda: self.preference_changed.emit(
                "tts", bool(self.voice_toggle.isChecked())
            )
        )
        voice_row.addWidget(self.voice_toggle)
        voice_row.addStretch(1)
        layout.addLayout(voice_row)

        mic_note = QLabel(
            "Mikrofon kapalı: sen yazarak konuşursun, Nora sesli cevap verir."
        )
        mic_note.setWordWrap(True)
        mic_note.setStyleSheet("color:#9d8fab; font-size:10px;")
        layout.addWidget(mic_note)

        layout.addStretch(1)
        return page

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color:#4a4460; font-size:11px; font-weight:600;")
        return label

    @staticmethod
    def _chip_style() -> str:
        return """
            QPushButton {
                background: rgba(24,18,40,12);
                border: 1px solid rgba(24,18,40,26);
                border-radius: 10px;
                color: #1b1725;
                font-size: 12px;
                padding: 4px 12px;
            }
            QPushButton:hover { background: rgba(123,92,255,26); }
            QPushButton:checked {
                background: rgba(123,92,255,40);
                border-color: rgba(123,92,255,150);
                color: #ffffff;
            }
        """

    @staticmethod
    def _input_style() -> str:
        return """
            QLineEdit {
                background: rgba(24,18,40,18);
                border: 1px solid rgba(123,92,255,26);
                border-radius: 10px;
                padding: 7px 10px;
                color: #1b1725;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: rgba(123,92,255,150); }
        """

    # ------------------------------------------------------------- behaviour
    def show_section(self, index: int) -> None:
        index = max(0, min(index, len(SECTIONS) - 1))
        self.pages.setCurrentIndex(index)
        for position, button in enumerate(self._tab_buttons):
            button.setChecked(position == index)

    def _choose_mood(self, mood: str) -> None:
        self.set_mood(mood)
        self.mood_chosen.emit(mood)

    def _choose_tone(self, tone: str) -> None:
        for key, button in self._tone_buttons.items():
            button.setChecked(key == tone)
        self.preference_changed.emit("relationship_tone", tone)

    def set_mood(self, mood: str) -> None:
        """Reflect a mood without emitting — used on open and by the app."""
        self._mood = mood
        for key, chip in self._mood_chips.items():
            chip.setChecked(key == mood)
        self.portrait.set_mood(mood)
        label = dict(MOODS).get(mood, mood)
        self.mood_line.setText(f"şu an: {label.lower()}")

    def set_preferences(self, prefs: dict[str, Any]) -> None:
        self.nickname.setText(str(prefs.get("nickname") or ""))
        tone = str(prefs.get("relationship_tone") or "close")
        for key, button in self._tone_buttons.items():
            button.setChecked(key == tone)
        self.voice_toggle.setChecked(bool(prefs.get("tts", True)))
        style = str(prefs.get("speech_style") or "doğal")
        self.style_note.setText(
            f"Şu an «{style}» tarzında konuşuyor. Tonu değiştirdiğinde cevapların "
            "sıcaklığı da buna göre ayarlanır."
        )

    def set_memories(self, items: Iterable[tuple[str, str, str]]) -> None:
        """Replace the memory list with ``(key, text, when)`` triples."""
        while self.memory_layout.count() > 1:
            item = self.memory_layout.takeAt(0)
            widget = item.widget()
            # A row whose C++ side was already destroyed still comes back as a
            # non-None wrapper; touching it would crash the interpreter.
            if widget is not None and sip.isdeleted(widget):
                continue
            if widget is not None:
                # Detach *now*: deleteLater() leaves the row alive (and still
                # reachable through findChildren) until the event loop spins,
                # which makes a rebuild-during-build crash the interpreter.
                widget.setParent(None)
                widget.deleteLater()
        rows = 0
        for key, text, when in items:
            row = MemoryRow(key, text, when)
            row.deleted.connect(self.memory_deleted.emit)
            self.memory_layout.insertWidget(self.memory_layout.count() - 1, row)
            rows += 1
        if rows:
            self.memory_count.setText(f"Seninle ilgili {rows} şey hatırlıyor.")
        else:
            self.memory_count.setText("Henüz bir şey hatırlamıyor.")

    def show_for(self, mood: str, prefs: dict[str, Any]) -> None:
        """Prepare the panel before it is shown."""
        self.set_mood(mood)
        self.set_preferences(prefs)


class PortraitBadge(QWidget):
    """Her 8-bit portrait on a glass circle — the panel's identity mark."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(64, 64)
        self._mood = "happy"
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def set_mood(self, mood: str) -> None:
        self._mood = mood
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        full = QRectF(self.rect()).adjusted(1, 1, -1, -1)

        # A brand-gradient ring reads as "this is her" far better than a grey
        # card, and it ties the panel to the logo and the send button.
        ring = QLinearGradient(full.topLeft(), full.bottomRight())
        ring.setColorAt(0.0, QColor("#7b5cff"))
        ring.setColorAt(0.5, QColor("#b45cf5"))
        ring.setColorAt(1.0, QColor("#ff4d94"))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(ring))
        painter.drawEllipse(full)

        inner = full.adjusted(3, 3, -3, -3)
        path = QPainterPath()
        path.addEllipse(inner)
        painter.setClipPath(path)
        painter.fillPath(path, QColor(255, 255, 255, 248))
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.save()
        # Head only at 2x: 16 logical px of face fits the 64 px badge.
        # The head is 16x22 logical px; at 2x it needs 32x44. Centre it in the
        # ring instead of shaving the top of her hair off.
        painter.setClipRect(10, 10, self.width() - 20, self.height() - 20)
        painter.translate(14, 9)
        PixelCharacter().draw_scaled(
            painter,
            scale=2,
            state="idle",
            emotion=self._mood,
            frame=0,
            appearance={"outfit": "cream"},
            animations=False,
        )
        painter.restore()


__all__ = [
    "MOODS",
    "SECTIONS",
    "TONES",
    "MemoryRow",
    "MoodChip",
    "PersonalPanel",
    "PortraitBadge",
]

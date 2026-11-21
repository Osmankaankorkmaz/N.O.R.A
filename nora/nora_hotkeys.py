"""Optional global push-to-talk hotkey.

The heavy/global keyboard hook is optional and only started after the user
enables push-to-talk in settings.  It emits Qt signals from a small polling
thread; no keystrokes are logged or stored.
"""

from __future__ import annotations

import logging
import threading

from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

DEFAULT_PTT_KEY = "ctrl+alt+space"


def normalize_ptt_key(value: str) -> str:
    key = " ".join(str(value or "").lower().split())
    key = (
        key.replace(" ", "")
        if "+" not in key
        else "+".join(part.strip() for part in key.split("+") if part.strip())
    )
    if not key or len(key) > 60 or any(ord(c) < 32 for c in key):
        raise ValueError("Bas-konuş tuşu boş veya geçersiz.")
    return key


class PushToTalkHotkey(QObject):
    pressed = pyqtSignal()
    released = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._key = DEFAULT_PTT_KEY
        self._down = False

    @property
    def active(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    @property
    def key(self) -> str:
        return self._key

    def start(self, key: str = DEFAULT_PTT_KEY) -> bool:
        try:
            self._key = normalize_ptt_key(key)
        except ValueError as exc:
            self.error.emit(str(exc))
            return False
        if self.active:
            return True
        try:
            import keyboard  # type: ignore[import-not-found]
        except ImportError:
            self.error.emit(
                "Bas-konuş için 'keyboard' paketi gerekli senpai. requirements-local.txt kur veya 🎤 düğmesini kullan. ⌨️"
            )
            return False
        self._stop.clear()
        self._down = False

        def run() -> None:
            while not self._stop.wait(0.035):
                try:
                    down = bool(keyboard.is_pressed(self._key))
                except Exception as exc:
                    logger.warning("Bas-konuş tuşu okunamadı: %s", type(exc).__name__)
                    self.error.emit(
                        "Bas-konuş tuşu okunamadı. Tuş kombinasyonunu ayarlardan değiştir veya yönetici iznini kontrol et. ⌨️"
                    )
                    return
                if down and not self._down:
                    self._down = True
                    self.pressed.emit()
                elif not down and self._down:
                    self._down = False
                    self.released.emit()

        try:
            self._thread = threading.Thread(
                target=run, name="nora-ptt-hotkey", daemon=True
            )
            self._thread.start()
            return True
        except Exception as exc:
            logger.warning("Bas-konuş thread başlatılamadı: %s", type(exc).__name__)
            self.error.emit("Bas-konuş başlatılamadı senpai. ⌨️")
            return False

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.2)
        self._thread = None
        if self._down:
            self._down = False
            self.released.emit()

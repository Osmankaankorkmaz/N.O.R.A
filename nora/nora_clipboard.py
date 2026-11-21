"""Opt-in, session-only clipboard history. Nothing here is written to disk.

The watcher is disabled by default. When enabled it observes new text clipboard
changes; obvious secrets are skipped, entries expire, and the user can inspect,
copy, delete or clear them. Clipboard text is never sent to a model implicitly.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from typing import Any, Callable

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

MAX_ENTRIES = 20
MAX_TEXT = 4000
TTL_SECONDS = 30 * 60
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.I),
    re.compile(r"\b(?:sk|gsk|ghp|github_pat|xoxb|xoxp)[-_][A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(
        r"\b(?:password|passwd|parola|şifre|token|secret|api[_ -]?key)\s*[:=]\s*\S+",
        re.I,
    ),
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    re.compile(
        r"\b(?:otp|doğrulama kodu|verification code|2fa)\s*[:=]?\s*\d{4,8}\b", re.I
    ),
)


def looks_sensitive(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


class ClipboardHistory(QObject):
    changed = pyqtSignal()

    def __init__(
        self,
        *,
        reader: Callable[[], str] | None = None,
        writer: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._reader = reader
        self._writer = writer
        self._clock = clock
        self._entries: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        self._clipboard = None
        self._connected = False
        self.last_skip_reason = ""

    @property
    def active(self) -> bool:
        return self._connected

    def start(self) -> bool:
        """Observe future changes only; do not silently ingest the current clipboard."""
        if self._connected:
            return True
        if self._reader is not None:
            # Injected readers are used by tests/headless adapters; manual
            # capture_current() remains the explicit ingestion boundary.
            self._connected = True
            return True
        try:
            clipboard = QApplication.clipboard()
            if clipboard is None:
                return False
            clipboard.dataChanged.connect(self._on_data_changed)
            self._clipboard = clipboard
            self._connected = True
            return True
        except Exception:
            return False

    def stop(self) -> None:
        if self._clipboard is not None and self._connected:
            try:
                self._clipboard.dataChanged.disconnect(self._on_data_changed)
            except Exception:
                pass
        self._clipboard = None
        self._connected = False

    def _on_data_changed(self) -> None:
        self.capture_current()

    def capture_current(self) -> bool:
        try:
            if self._reader is not None:
                text = self._reader()
            else:
                clipboard = QApplication.clipboard()
                text = clipboard.text() if clipboard is not None else ""
        except Exception:
            self.last_skip_reason = "Pano okunamadı."
            return False
        return self.record(str(text or ""))

    def record(self, text: str, *, now: float | None = None) -> bool:
        now = self._clock() if now is None else now
        text = text.strip()
        if not text:
            self.last_skip_reason = "Panoda metin yok."
            return False
        if len(text) > MAX_TEXT:
            self.last_skip_reason = (
                f"Pano metni {MAX_TEXT} karakterden uzun; geçmişe alınmadı."
            )
            return False
        if looks_sensitive(text):
            self.last_skip_reason = (
                "Parola/anahtar/kart gibi hassas görünen pano metni geçmişe alınmadı."
            )
            return False
        with self._lock:
            self._prune(now)
            if self._entries and self._entries[-1]["text"] == text:
                return False
            self._entries.append(
                {
                    "id": uuid.uuid4().hex[:8],
                    "text": text,
                    "created_at": now,
                    "expires_at": now + TTL_SECONDS,
                }
            )
            del self._entries[:-MAX_ENTRIES]
            self.last_skip_reason = ""
        self.changed.emit()
        return True

    def _prune(self, now: float) -> None:
        self._entries = [item for item in self._entries if item["expires_at"] > now]

    def prune(self) -> None:
        with self._lock:
            before = len(self._entries)
            self._prune(self._clock())
            changed = before != len(self._entries)
        if changed:
            self.changed.emit()

    @property
    def entries(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune(self._clock())
            return [dict(item) for item in reversed(self._entries)]

    def get(self, identifier: str) -> str:
        with self._lock:
            self._prune(self._clock())
            for index, item in enumerate(reversed(self._entries), 1):
                if identifier in {item["id"], str(index)}:
                    return item["text"]
        raise ValueError("Pano geçmişi kaydı bulunamadı veya süresi doldu.")

    def delete(self, identifier: str) -> bool:
        with self._lock:
            self._prune(self._clock())
            for index, item in enumerate(reversed(self._entries), 1):
                if identifier in {item["id"], str(index)}:
                    self._entries.remove(item)
                    self.changed.emit()
                    return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
        self.changed.emit()

    def copy(self, identifier: str) -> str:
        text = self.get(identifier)
        try:
            if self._writer is not None:
                self._writer(text)
            else:
                clipboard = QApplication.clipboard()
                if clipboard is None:
                    raise ValueError("Pano kullanılamıyor.")
                clipboard.setText(text)
        except Exception as exc:
            raise ValueError("Pano kaydını panoya yazamadım.") from exc
        return "Pano kaydını panoya kopyaladım. Buluta göndermedim. 📋"

    def listing(self) -> str:
        entries = self.entries
        if not entries:
            return "Pano geçmişi boş. Geçmiş izlemeyi açabilir veya 'panoyu geçmişe ekle' diyebilirsin. 📋"
        lines = ["Pano geçmişi · yalnızca bellek, 30 dakika 📋"]
        for index, item in enumerate(entries, 1):
            preview = " ".join(item["text"].split())[:100]
            lines.append(f"{index}. [{item['id']}] {preview}")
        return "\n".join(lines)

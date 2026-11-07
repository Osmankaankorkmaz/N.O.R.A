"""Persistent reminders, reversible companion modes and small desktop games."""

from __future__ import annotations

import random
import re
from datetime import datetime
from typing import Any, Callable

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from .nora_store import NoraStore, now_local, parse_datetime


class ReminderScheduler(QObject):
    """Qt-thread scheduler; persistence and missed-event recovery live in the store."""

    reminder_due = pyqtSignal(str)
    scheduler_error = pyqtSignal(str)

    def __init__(
        self,
        store: NoraStore,
        *,
        parent: QObject | None = None,
        now: Callable[[], datetime] = now_local,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.now = now
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.check)
        self._checking = False

    def start(self) -> None:
        self._timer.start()
        QTimer.singleShot(0, self.check)

    def stop(self) -> None:
        self._timer.stop()

    def check(self) -> None:
        if self._checking:
            return
        self._checking = True
        try:
            for item in self.store.due_reminders(self.now()):
                self.reminder_due.emit(str(item["text"]))
        except ValueError as exc:
            self._timer.stop()
            self.scheduler_error.emit(str(exc))
        finally:
            self._checking = False

    def listing(self) -> str:
        items = self.store.reminders
        if not items:
            return "Kayıtlı hatırlatıcın yok senpai. '10 dakika sonra çayı hatırlat' diyebilirsin. ⏰"
        lines = ["Kalıcı hatırlatıcıların ⏰"]
        repeats = {
            "none": "",
            "daily": " · her gün",
            "weekdays": " · hafta içi",
            "weekly": " · her hafta",
        }
        for index, item in enumerate(
            sorted(items, key=lambda value: value["due_at"]), 1
        ):
            try:
                when = parse_datetime(item["due_at"]).strftime("%d.%m.%Y %H:%M")
            except (ValueError, TypeError):
                when = "geçersiz tarih"
            lines.append(
                f"{index}. {when} — {item['text']}{repeats.get(item.get('recurrence'), '')} [{item['id']}]"
            )
        return "\n".join(lines)


class ModeManager:
    """Changes Nora's behavior, never kills applications or changes OS settings."""

    def __init__(self, store: NoraStore) -> None:
        self.store = store

    @property
    def current(self) -> str:
        return self.store.preference("mode", "normal")

    def activate(self, mode: str) -> dict[str, Any]:
        if mode not in {"normal", "focus", "game", "quiet"}:
            raise ValueError("Bilinmeyen mod.")
        previous = self.current
        snapshot = self.store.mode_snapshot
        if previous == "normal" and mode != "normal":
            snapshot = {
                "tts": bool(self.store.preference("tts")),
                "proactive": bool(self.store.preference("proactive")),
            }
            self.store.save_mode_snapshot(snapshot)
        settings: dict[str, Any] = {"mode": mode}
        if mode == "normal":
            settings.update(snapshot or {"tts": True, "proactive": True})
            self.store.save_mode_snapshot({})
        elif mode == "focus":
            settings.update(tts=False, proactive=False)
        elif mode == "game":
            settings.update(tts=snapshot.get("tts", True), proactive=False)
        elif mode == "quiet":
            settings.update(tts=False, proactive=False)
        for key, value in settings.items():
            self.store.set_preference(key, value)
        return settings


class WordGame:
    """A Turkish anagram game; no network, account or persistent personal data."""

    WORDS = (
        ("kedi", "Mırlar, bıyıkları vardır ve kahveni devirmeye bayılır."),
        ("kahve", "Nora'nın gece kodlama yakıtı. ☕"),
        ("senpai", "Nora'nın sana seslenme şekli."),
        ("masaüstü", "Nora'nın küçük ayaklarıyla dolaştığı yer."),
        ("monitör", "İkincisine geçmemi isteyebilirsin."),
        ("kitap", "Sayfaları olan, sessiz bir arkadaş."),
        ("müzik", "Oyun modunda açılabilecek şey."),
        ("yıldız", "Gece gökyüzünde parlar."),
        ("çilek", "Kırmızı, küçük çekirdekli bir meyve."),
        ("bulut", "Gökyüzünde gezer; sunucularda da bulunur."),
    )

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.answer = ""
        self.scrambled = ""
        self.hints = 0
        self.score = 0

    def start(self) -> str:
        self.answer, self._hint = self.rng.choice(self.WORDS)
        letters = list(self.answer)
        for _ in range(10):
            self.rng.shuffle(letters)
            if "".join(letters) != self.answer:
                break
        else:
            letters = letters[::-1]
        self.scrambled = "".join(letters)
        self.hints = 0
        return f"Kelime oyunu başladı! Harfler: {self.scrambled.upper()}\n'Cevabım …' diye tahmin et; 'ipucu ver' de diyebilirsin. Skor: {self.score}"

    def hint(self) -> str:
        if not self.answer:
            return "Önce 'kelime oyunu başlat' de senpai."
        self.hints += 1
        if self.hints == 1:
            return f"İpucu: {self._hint}"
        return f"Bir harf daha: {self.answer[0].upper()}… ({len(self.answer)} harf)"

    def guess(self, guess: str) -> str:
        if not self.answer:
            return "Önce oyunu başlat senpai."
        if guess.strip().translate(str.maketrans("Iİ", "ıi")).lower() == "__reveal__":
            answer, self.answer = self.answer, ""
            return f"Cevap: {answer.upper()}. Yeni tur için 'kelime oyunu başlat' de."
        normalized = (
            re.sub(r"\s+", "", guess).translate(str.maketrans("Iİ", "ıi")).lower()
        )
        if normalized == self.answer:
            self.score += max(1, 3 - self.hints)
            self.answer = ""
            return f"Doğru senpai! Sugoi~ Skorun {self.score}. Yeni tur için 'kelime oyunu başlat'. 🐾"
        return "Bu değil senpai. Harflere tekrar bak; istersen 'ipucu ver'. 😼"

    def stop(self) -> str:
        self.answer = ""
        return (
            f"Oyun bitti. Skorun {self.score} senpai. İstediğin zaman yine oynarız. 💜"
        )


class NumberGame:
    """A tiny 1-100 guessing game; local, deterministic-friendly, no telemetry."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self.answer = 0
        self.attempts = 0
        self.score = 0
        self.low = 1
        self.high = 100

    def start(self) -> str:
        self.answer = self.rng.randint(1, 100)
        self.attempts = 0
        self.low, self.high = 1, 100
        return (
            "Sayı tahmin oyunu başladı! 1-100 arası bir sayı tuttum. 🔢\n"
            "'sayı tahminim 42' diye tahmin et; 'sayı oyununu bitir' ile çıkabilirsin."
        )

    def guess(self, guess: int) -> str:
        if not self.answer:
            return "Önce 'sayı oyunu başlat' de senpai."
        try:
            value = int(guess)
        except (TypeError, ValueError):
            return "1-100 arası bir sayı söyle senpai."
        if not 1 <= value <= 100:
            return "Sayı 1 ile 100 arasında olmalı senpai."
        self.attempts += 1
        if value == self.answer:
            gained = max(1, 8 - self.attempts)
            self.score += gained
            answer, self.answer = self.answer, 0
            return (
                f"Doğru! Sayı {answer} idi. {self.attempts}. denemede buldun; +{gained} puan. "
                f"Toplam skor: {self.score}. Yeni tur için 'sayı oyunu başlat'. 🎉"
            )
        if value < self.answer:
            self.low = max(self.low, value + 1)
            return f"Daha büyük söyle. Aralık: {self.low}-{self.high} 🔺"
        self.high = min(self.high, value - 1)
        return f"Daha küçük söyle. Aralık: {self.low}-{self.high} 🔻"

    def stop(self) -> str:
        answer, self.answer = self.answer, 0
        reveal = f" Tutuğum sayı {answer} idi." if answer else ""
        return f"Sayı oyunu bitti.{reveal} Skorun {self.score} senpai. 💜"

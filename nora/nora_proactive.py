"""Low-frequency proactive dialogue engine (Qt timer, no network calls)."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Callable

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from .nora_personality import get_time_category, is_quiet_hours, random_line

logger = logging.getLogger(__name__)


class ProactiveEngine(QObject):
    speak_requested = pyqtSignal(str)

    CHECK_INTERVAL_MS = 30_000
    MIN_INTERVAL_SECONDS = 120
    IDLE_THRESHOLD_SECONDS = 300

    def __init__(
        self,
        tools,
        *,
        rng: random.Random | None = None,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = datetime.now,
        store=None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.tools = tools
        self.store = store
        self._routine_last = {"hydration_minutes": clock(), "break_minutes": clock()}
        self.rng = rng or random.Random()
        self.clock = clock
        self.now = now
        self._last_interaction = clock()
        self._last_proactive = clock()
        self._last_hour_key = ""
        self._alert_cooldowns: dict[str, float] = {}
        self._suspended = False
        self._timer = QTimer(self)
        self._timer.setInterval(self.CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._check)

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def user_interacted(self) -> None:
        self._last_interaction = self.clock()

    def set_suspended(self, suspended: bool) -> None:
        """Pause while the user is busy, Nora is speaking, or mic is active."""
        self._suspended = bool(suspended)

    @property
    def suspended(self) -> bool:
        return self._suspended

    def _check(self) -> None:
        if self._suspended:
            return
        now_mono = self.clock()
        if now_mono - self._last_proactive < self.MIN_INTERVAL_SECONDS:
            return
        now = self.now()
        quiet = is_quiet_hours(now) and (
            self.store is None or self.store.preference("quiet_hours")
        )

        # 1. System health has priority, but a repeated alert is rate-limited.
        try:
            alert = self.tools.check_system_health()
        except Exception:
            logger.debug("Proaktif sistem kontrolü hatası", exc_info=True)
            alert = None
        if alert:
            kind = str(alert.get("kind", "system"))
            if now_mono - self._alert_cooldowns.get(kind, -1000) >= 600:
                self._alert_cooldowns[kind] = now_mono
                self._trigger(
                    str(alert.get("message") or random_line("system_alert", self.rng))
                )
                return

        # 2. Explicit opt-in wellbeing routines; disabled by default (0 minutes).
        if self.store is not None and not quiet:
            for key, message in (
                (
                    "hydration_minutes",
                    "Su molası senpai. Bir bardak su iç, sonra devam. 💧",
                ),
                (
                    "break_minutes",
                    "Ekran molası zamanı. Biraz uzağa bak ve omuzlarını gevşet. 🐾",
                ),
            ):
                minutes = self.store.preference(key, 0)
                if minutes > 0 and now_mono - self._routine_last[key] >= minutes * 60:
                    self._routine_last[key] = now_mono
                    self._trigger(message)
                    return

        # 3. Five minutes without interaction: 40% (12% during quiet hours).
        if now_mono - self._last_interaction >= self.IDLE_THRESHOLD_SECONDS:
            if self.rng.random() < (0.12 if quiet else 0.40):
                self._trigger(random_line("idle", self.rng))
                return

        # 3. Hourly greeting, at most once per calendar hour.
        if now.minute <= 2:
            key = f"{now:%Y-%m-%d-%H}"
            if key != self._last_hour_key and (not quiet or self.rng.random() < 0.25):
                self._last_hour_key = key
                self._trigger(random_line(get_time_category(now), self.rng))
                return

        # 4. Occasional personality line: 8% (2% during quiet hours).
        if self.rng.random() < (0.02 if quiet else 0.08):
            self._trigger(random_line("random", self.rng))

    def _trigger(self, text: str) -> None:
        self._last_proactive = self.clock()
        self.speak_requested.emit(text)

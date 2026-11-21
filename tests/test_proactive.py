from datetime import datetime

from nora.nora_proactive import ProactiveEngine


class Clock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value


class Tools:
    def __init__(self, alert=None):
        self.alert = alert

    def check_system_health(self):
        return self.alert


class FixedRNG:
    def __init__(self, value):
        self.value = value

    def random(self):
        return self.value

    def choice(self, items):
        return items[0]


def make_engine(alert=None, rng=None, minute=30):
    clock = Clock()
    now = datetime(2026, 1, 1, 15, minute)
    engine = ProactiveEngine(
        Tools(alert), rng=rng or FixedRNG(0.99), clock=clock, now=lambda: now
    )
    emitted = []
    engine.speak_requested.connect(emitted.append)
    return engine, clock, emitted


def test_minimum_interval():
    engine, clock, emitted = make_engine()
    clock.value += 119
    engine._check()
    assert not emitted
    clock.value += 2
    engine._check()
    assert not emitted  # rng 0.99 avoids random/idle/hour


def test_system_alert_priority_and_cooldown():
    alert = {"kind": "cpu", "value": 95, "message": "CPU yüksek"}
    engine, clock, emitted = make_engine(alert=alert)
    clock.value += 121
    engine._check()
    assert emitted == ["CPU yüksek"]
    clock.value += 121
    engine._check()
    assert len(emitted) == 1  # per-alert cooldown
    clock.value += 600
    engine._check()
    assert len(emitted) == 2


def test_idle_threshold_and_interaction_reset():
    engine, clock, emitted = make_engine(rng=FixedRNG(0.1))
    clock.value += 299
    engine._check()
    assert not emitted
    clock.value += 2
    engine._check()
    assert len(emitted) == 1
    engine.user_interacted()
    clock.value += 121
    engine._check()
    assert len(emitted) == 1


def test_hourly_greeting_once_per_hour():
    engine, clock, emitted = make_engine(minute=1)
    clock.value += 121
    engine._check()
    assert len(emitted) == 1
    clock.value += 121
    engine._check()
    assert len(emitted) == 1


def test_suspended_engine_does_not_speak():
    engine, clock, emitted = make_engine(alert={"kind": "ram", "message": "RAM"})
    engine.set_suspended(True)
    clock.value += 1000
    engine._check()
    assert not emitted
    engine.set_suspended(False)
    engine._check()
    assert emitted == ["RAM"]


def test_quiet_hours_reduce_random_probability():
    clock = Clock()
    engine = ProactiveEngine(
        Tools(),
        rng=FixedRNG(0.05),
        clock=clock,
        now=lambda: datetime(2026, 1, 1, 3, 30),
    )
    emitted = []
    engine.speak_requested.connect(emitted.append)
    clock.value += 121
    engine._check()
    assert not emitted  # 5% > quiet random threshold 2%, idle not reached


def test_autonomy_is_explicit_opt_in_and_rate_limited():
    class Store:
        def __init__(self):
            self.prefs = {
                "quiet_hours": True,
                "auto_screen_watch": True,
                "auto_camera_watch": False,
                "auto_media": False,
                "autonomy_minutes": 5,
                "hydration_minutes": 0,
                "break_minutes": 0,
            }

        def preference(self, key, default=None):
            return self.prefs.get(key, default)

    engine, clock, emitted = make_engine(rng=FixedRNG(0.1))
    engine.store = Store()
    requests = []
    engine.autonomy_requested.connect(requests.append)
    clock.value += 301
    engine._check()
    assert requests == ["screen"]
    clock.value += 121
    engine._check()
    assert len(requests) == 1
    engine.store.prefs["auto_screen_watch"] = False
    clock.value += 301
    engine._check()
    assert len(requests) == 1

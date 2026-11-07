import random
from datetime import timedelta

from nora.nora_activities import ModeManager, ReminderScheduler, WordGame
from nora.nora_store import NoraStore, now_local


def test_modes_restore_previous_preferences(tmp_path):
    store = NoraStore(tmp_path / "state.json")
    store.update_preferences({"tts": True, "proactive": True})
    modes = ModeManager(store)
    modes.activate("focus")
    assert not store.preference("tts") and not store.preference("proactive")
    modes.activate("game")
    assert store.preference("tts") is True
    modes.activate("normal")
    assert store.preference("tts") and store.preference("proactive")
    assert store.mode_snapshot == {}


def test_scheduler_emits_on_qt_thread(qapp, tmp_path):
    store = NoraStore(tmp_path / "state.json")
    store.add_reminder("çay", now_local() - timedelta(seconds=1))
    scheduler = ReminderScheduler(store)
    received = []
    scheduler.reminder_due.connect(received.append)
    scheduler.check()
    assert received == ["çay"]
    assert "çay" in scheduler.listing() or not store.reminders
    scheduler.stop()


def test_word_game_is_deterministic_and_scored():
    game = WordGame(random.Random(4))
    text = game.start()
    assert "Harfler:" in text
    assert game.hint()
    assert "Doğru" in game.guess(game.answer)
    assert game.score == 2
    assert "Oyun bitti" in game.stop()


def test_opt_in_wellbeing_routine(qapp, tmp_path):
    from nora.nora_proactive import ProactiveEngine
    from types import SimpleNamespace

    store = NoraStore(tmp_path / "state.json")
    store.update_preferences({"hydration_minutes": 1, "quiet_hours": False})
    current = [1000.0]
    engine = ProactiveEngine(
        SimpleNamespace(check_system_health=lambda: None),
        store=store,
        clock=lambda: current[0],
        rng=random.Random(1),
    )
    received = []
    engine.speak_requested.connect(received.append)
    engine._last_proactive = 0
    current[0] = 1200.0
    engine._check()
    assert received and "Su molası" in received[0]
    engine.stop()


def test_number_game_hints_bounds_and_scoring():
    from nora.nora_activities import NumberGame

    game = NumberGame(random.Random(7))
    assert "1-100" in game.start()
    answer = game.answer
    assert "Önce" in NumberGame().guess(5)
    low = game.guess(1)
    assert "Daha büyük" in low or answer == 1
    if answer != 1:
        high = game.guess(100)
        assert "Daha küçük" in high
    result = game.guess(answer)
    assert "Doğru" in result and game.score >= 1
    assert "Önce" in game.guess(5)
    game.start()
    assert "bitti" in game.stop()
    assert game.answer == 0

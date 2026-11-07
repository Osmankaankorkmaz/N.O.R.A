import time

import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import QLabel

from nora.nora_pet import NoraPet, PetState
from nora.nora_ui import ChatBubble, NoraApp, NoraOptions


def process_until(qapp, predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_pet_size_states_and_render(qapp):
    pet = NoraPet()
    pet._timer.stop()
    assert pet.width() == 120 and pet.height() == 150
    assert pet.testAttribute(Qt.WA_TranslucentBackground)
    pet.set_emotion("love")
    assert pet.emotion == "love" and pet.state == PetState.LOVE
    pet.set_emotion("sleepy")
    assert pet.state in (PetState.SLEEP, PetState.IDLE)
    pet.set_speaking(True)
    assert pet.state == PetState.TALK
    pet.set_speaking(False)
    pet.show_speech("x" * 100, 1000)
    assert pet._bubble is not None
    assert len(pet._bubble._text) == 63
    image = pet.grab().toImage()
    assert not image.isNull() and image.width() == 120
    assert any(
        image.pixelColor(x, y).alpha() > 0
        for x in range(0, 120, 5)
        for y in range(0, 150, 5)
    )
    pet.shutdown()


def test_pet_falls_to_floor_after_drag(qapp):
    pet = NoraPet()
    pet._timer.stop()
    pet.jump_to(pet.x(), pet.y() - 120)
    for _ in range(200):
        pet._tick()
    assert pet.state != PetState.FALL
    assert abs(pet.y() - pet._current_floor()) <= 1
    pet.shutdown()


def test_chat_bubble_plain_text_and_alignment(qapp):
    bubble = ChatBubble("<b>html değil</b>", "user")
    label = bubble.findChild(QLabel)
    assert label.textFormat() == Qt.PlainText
    assert label.maximumWidth() == 280


def test_app_offline_chat_and_command_flow(qapp, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    app = NoraApp(
        NoraOptions(wake_word=False, tts=False, proactive=False, offline=True)
    )
    app.start()
    qapp.processEvents()
    assert app.pet.isVisible()
    app.show_chat()
    assert app.chat_window.isVisible()
    app._send_message("not al: test notu")
    assert process_until(qapp, lambda: not app._busy)
    assert any("test notu" in n["text"] for n in app.tools.notes)
    assert app.pet._bubble is not None and app.pet._bubble._speaker == "user"
    assert len(app._message_rows) >= 3
    app._reset_memory()
    assert len(app.brain.history) == 1
    app.shutdown()
    qapp.processEvents()
    assert not app._workers
    assert not app.pet.isVisible()


def test_chat_close_hides_instead_of_quitting(qapp):
    app = NoraApp(
        NoraOptions(wake_word=False, tts=False, proactive=False, offline=True)
    )
    app.show_chat()
    event = QCloseEvent()
    qapp.sendEvent(app.chat_window, event)
    assert not event.isAccepted()
    assert not app.chat_window.isVisible()
    app.shutdown()


def test_screen_analysis_without_key_does_not_capture(qapp, monkeypatch):
    app = NoraApp(
        NoraOptions(wake_word=False, tts=False, proactive=False, offline=True)
    )
    called = []
    monkeypatch.setattr(app.tools, "screenshot", lambda: called.append(True))
    app._analyze_screen()
    assert not called
    assert not app._busy
    app.shutdown()


def test_pet_listening_pose_is_sticky_and_renderable(qapp):
    pet = NoraPet()
    pet._timer.stop()
    pet.set_listening(True)
    assert pet.state == PetState.LISTENING
    pet._choose_state()
    assert pet.state == PetState.LISTENING
    image = pet.grab().toImage()
    assert any(
        image.pixelColor(x, y).alpha() > 0
        for x in range(80, 115, 3)
        for y in range(40, 70, 3)
    )
    pet.set_speaking(True)
    pet.set_speaking(False)
    assert pet.state != PetState.LISTENING
    pet.set_listening(False)
    pet.shutdown()


def test_ui_listening_signals_drive_pet(qapp):
    app = NoraApp(
        NoraOptions(wake_word=False, tts=False, proactive=False, offline=True)
    )
    app._on_listening_started(5)
    assert app.pet.state == PetState.LISTENING
    app._on_listening_stopped(5)
    assert app.pet.state != PetState.LISTENING
    app.shutdown()


def test_user_speech_bubble_is_distinct(qapp):
    pet = NoraPet()
    pet._timer.stop()
    pet.show_user_speech("merhaba nora")
    assert pet._bubble is not None
    assert pet._bubble._speaker == "user"
    assert pet._bubble._text.startswith("Sen: ")
    pet.shutdown()

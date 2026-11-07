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


def test_explicit_pet_commands_bypass_chat_worker(qapp, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("movement must not need an AI worker")

    monkeypatch.setattr("nora.nora_ui.ChatWorker", forbidden)
    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    app.pet._timer.stop()
    app._send_message("Hey Nora, uyu")
    assert app.pet.state == PetState.SLEEP
    app.pet.set_emotion("happy")
    assert app.pet.state == PetState.SLEEP
    app._send_message("dolaş")
    assert app.pet.state in (PetState.WALK_LEFT, PetState.WALK_RIGHT)
    app._send_message("dur")
    assert app.pet.state == PetState.IDLE
    app._send_message("zıpla ve uyu")
    for _ in range(100):
        app.pet._tick()
    assert app.pet.state == PetState.SLEEP
    assert not app._workers
    app.shutdown()


def test_monitor_transfer_with_two_screen_geometries(qapp, monkeypatch):
    from PyQt5.QtCore import QRect
    from types import SimpleNamespace

    pet = NoraPet()
    pet._timer.stop()
    screens = [
        SimpleNamespace(
            geometry=lambda: QRect(0, 0, 1920, 1080),
            availableGeometry=lambda: QRect(0, 0, 1920, 1040),
            name=lambda: "Primary",
        ),
        SimpleNamespace(
            geometry=lambda: QRect(1920, 0, 1280, 1024),
            availableGeometry=lambda: QRect(1920, 0, 1280, 984),
            name=lambda: "Second",
        ),
    ]
    monkeypatch.setattr(pet, "_monitor_screens", lambda: screens)
    ok, message = pet.move_to_monitor(2)
    assert ok and pet.x() >= 1920 and "2." in message
    assert not pet.move_to_monitor(3)[0]
    pet.shutdown()


def test_memory_tasks_and_reminders_persist_across_app_restart(qapp, tmp_path):
    options = NoraOptions(
        wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
    )
    app = NoraApp(options)
    app._send_message("bunu hatırla: kahvem = şekersiz")
    app._send_message("görev ekle: raporu bitir")
    app._send_message("10 dakika sonra çayı hatırlat")
    assert app.store.memories["kahvem"]["value"] == "şekersiz"
    assert app.store.tasks and app.store.reminders
    app.shutdown()
    reopened = NoraApp(options)
    assert reopened.store.memories["kahvem"]["value"] == "şekersiz"
    assert reopened.store.tasks[0]["text"] == "raporu bitir"
    assert reopened.store.reminders[0]["text"] == "çayı"
    reopened.shutdown()


def test_settings_dialog_applies_pixel_appearance_and_persona(qapp, tmp_path):
    from nora.nora_settings_dialog import NoraSettingsDialog
    from nora.nora_store import NoraStore

    store = NoraStore(tmp_path / "state.json")
    applied = []

    def apply_values(values):
        store.update_preferences(values)
        applied.append(values)

    dialog = NoraSettingsDialog(store, on_apply=apply_values)
    dialog.fields["tone"].setCurrentIndex(dialog.fields["tone"].findData("sweet"))
    dialog.fields["accessory"].setCurrentIndex(
        dialog.fields["accessory"].findData("glasses")
    )
    dialog.apply()
    assert applied[0]["tone"] == "sweet"
    assert store.preference("accessory") == "glasses"
    pet = NoraPet()
    pet._timer.stop()
    pet.set_appearance(store.preferences)
    assert not pet.grab().isNull()
    pet.shutdown()


def test_pet_accessories_and_dance_render(qapp):
    pet = NoraPet()
    pet._timer.stop()
    for accessory in ("none", "headphones", "glasses", "ribbon"):
        pet.set_appearance(
            {"accessory": accessory, "outfit": "night", "hair_color": "#202b52"}
        )
        assert not pet.grab().isNull()
    pet.perform_action("dance")
    assert pet.state == PetState.DANCE
    pet._tick()
    assert not pet.grab().isNull()
    pet.shutdown()


def test_routine_runs_bounded_steps_after_confirmation(qapp, tmp_path, monkeypatch):
    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    app.pet._timer.stop()
    monkeypatch.setattr(app, "_confirm", lambda *args: True)
    app.store.save_routine(
        "test",
        [
            {"command": "pet_action", "action": "wave"},
            {"command": "pet_action", "action": "sit"},
        ],
    )
    app._execute_command({"command": "routine", "action": "run", "name": "test"})
    assert process_until(
        qapp, lambda: not app._pending_commands and app.pet.state == PetState.SIT
    )
    app.shutdown()


def test_screen_ocr_is_local_until_analysis_confirmation(qapp, tmp_path, monkeypatch):
    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    monkeypatch.setattr(app.tools, "screenshot", lambda: "fake-image")
    monkeypatch.setattr(app.ocr, "read", lambda image: "Hata: örnek kod")
    monkeypatch.setattr(app, "_confirm", lambda *args: False)

    def forbidden(*args, **kwargs):
        raise AssertionError("OCR text must not upload without consent")

    monkeypatch.setattr("nora.nora_ui.TextWorker", forbidden)
    app._execute_command({"command": "screen_text"})
    assert process_until(
        qapp,
        lambda: (
            not app._busy
            and any(
                "örnek kod" in row.findChild(QLabel).text()
                for row in app._message_rows
                if row.findChild(QLabel)
            )
        ),
    )
    app.shutdown()


def test_clipboard_is_not_uploaded_without_confirmation(qapp, tmp_path, monkeypatch):
    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    monkeypatch.setattr(app.tools, "clipboard_paste", lambda: "özel metin")
    monkeypatch.setattr(app.brain, "_client", object())
    app.brain.offline = False
    monkeypatch.setattr(app, "_confirm", lambda *args: False)

    def forbidden(*args, **kwargs):
        raise AssertionError("clipboard upload requires consent")

    monkeypatch.setattr("nora.nora_ui.TextWorker", forbidden)
    app._execute_command({"command": "clipboard_help", "action": "summarize"})
    assert not app._workers
    app.shutdown()


def test_bot_messages_use_central_spoken_reply_policy(qapp, monkeypatch):
    app = NoraApp(
        NoraOptions(wake_word=False, tts=False, proactive=False, offline=True)
    )
    spoken = []
    app.voice.tts_enabled = True
    monkeypatch.setattr(
        app.voice, "speak", lambda text, *a, **k: spoken.append(text) or True
    )
    app.add_message("Merhaba senpai", "bot")
    app.add_message("Benim yazdığım", "user")
    app._report("Uzun yanıt. " * 80)
    app._report("Sessiz veri dökümü", speak=False)
    assert spoken == ["Merhaba senpai", ("Uzun yanıt. " * 80).strip()]
    app.shutdown()


def test_chat_and_tool_replies_are_spoken_without_length_cap(qapp, monkeypatch):
    from nora.nora_brain import ChatReply

    app = NoraApp(
        NoraOptions(wake_word=False, tts=False, proactive=False, offline=True)
    )
    spoken = []
    app.voice.tts_enabled = True
    monkeypatch.setattr(
        app.voice, "speak", lambda text, *a, **k: spoken.append(text) or True
    )
    app._active_request = 7
    app._on_chat_done(7, ChatReply(text="Sesli sohbet yanıtı", emotion="happy"))
    app._active_request = 8
    app._on_tool_done(8, True, "Araç sonucu. " * 60, True)
    assert spoken == ["Sesli sohbet yanıtı", ("Araç sonucu. " * 60).strip()]
    app.shutdown()


def test_tts_indicator_and_mode_restore_are_visible(qapp, monkeypatch):
    app = NoraApp(NoraOptions(wake_word=False, tts=True, proactive=False, offline=True))
    monkeypatch.setattr(app.voice, "speak", lambda *a, **k: True)
    assert app.speaker_indicator.text() == "🔊"
    app._toggle_tts(False)
    assert app.speaker_indicator.text() == "🔇"
    assert app.store.preference("tts") is False
    app._toggle_tts(True)
    app._activate_mode("focus")
    assert app.voice.tts_enabled is False
    assert app.speaker_indicator.text() == "🔇"
    app._activate_mode("normal")
    assert app.voice.tts_enabled is True
    assert app.speaker_indicator.text() == "🔊"
    app.shutdown()


def test_tray_icon_refreshes_with_pixel_appearance(qapp, tmp_path):
    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    before = app.tray.icon().pixmap(64, 64).toImage()
    app._apply_settings({"hair_color": "#202b52", "outfit": "casual"})
    after = app.tray.icon().pixmap(64, 64).toImage()
    assert not after.isNull() and after != before
    app.shutdown()


def test_voice_name_correction_is_visible_and_executes_safe_command(qapp, tmp_path):
    from nora.nora_commands import parse_direct_command
    from nora.nora_speech import repair_transcript

    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    app.pet._timer.stop()
    request_id = app._next_request()
    app._listening = True
    app._set_busy(True)
    repair = repair_transcript(
        "hey nova uyu", command_parser=parse_direct_command, request_id=request_id
    )
    app.voice.last_transcript = repair
    app._on_listen_done(request_id, repair.text, "")
    qapp.processEvents()
    texts = [
        row.findChild(QLabel).text()
        for row in app._message_rows
        if row.findChild(QLabel)
    ]
    assert any("Adımı “nova” diye duydum" in text for text in texts)
    assert app.pet.state == PetState.SLEEP
    app.shutdown()


def test_speech_recognition_test_shows_transcript_without_executing(qapp, tmp_path):
    from nora.nora_commands import parse_direct_command
    from nora.nora_speech import repair_transcript

    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    app.pet._timer.stop()
    request_id = app._next_request()
    app._stt_test_request = request_id
    app._listening = True
    app._set_busy(True)
    repair = repair_transcript(
        "hey nova uyu", command_parser=parse_direct_command, request_id=request_id
    )
    app.voice.last_transcript = repair
    app._on_listen_done(request_id, repair.text, "")
    qapp.processEvents()
    texts = [
        row.findChild(QLabel).text()
        for row in app._message_rows
        if row.findChild(QLabel)
    ]
    assert any("Ses tanıma testi" in text and "Duyduğum" in text for text in texts)
    assert app.pet.state != PetState.SLEEP
    assert not app._busy and not app._listening
    app.shutdown()

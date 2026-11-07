import threading
import time

from nora.nora_voice import NoraVoice, speech_text


def test_speech_text_strips_emoji_and_tags_already_removed():
    assert speech_text("Merhaba 💕🐾  senpai~") == "Merhaba senpai~"


def test_tts_disabled_does_not_queue(qapp):
    voice = NoraVoice(tts_enabled=False)
    assert not voice.speak("merhaba")
    assert not voice.is_speaking
    voice.close()


def test_wake_word_extracts_remainder_and_ignores_substrings(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=False)
    results = []
    done = threading.Event()
    samples = iter([("Hey Nora chrome aç", ""), ("norayı severim", ""), ("nora", "")])
    monkeypatch.setattr(voice, "_capture", lambda *a, **k: next(samples, ("", "")))

    def callback(text):
        results.append(text)
        if len(results) >= 2:
            done.set()

    voice.start_wake_word_listener(callback)
    assert done.wait(3)
    voice.stop_wake_word_listener()
    assert results == ["chrome aç", ""]
    voice.close()


def test_wake_listener_pauses_while_speaking(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=False)
    called = []
    monkeypatch.setattr(
        voice, "_capture", lambda *a, **k: called.append(True) or ("nora selam", "")
    )
    with voice._speech_lock:
        voice._speech_pending = 1
    voice.start_wake_word_listener(lambda text: called.append(text))
    time.sleep(0.3)
    assert not called
    with voice._speech_lock:
        voice._speech_pending = 0
    deadline = time.time() + 2
    while not called and time.time() < deadline:
        time.sleep(0.05)
    voice.stop_wake_word_listener()
    assert called
    voice.close()


def test_listen_async_reserves_microphone_before_thread(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=False)
    release = threading.Event()

    def fake_listen_once(*a, **k):
        release.wait(1)
        return "merhaba"

    monkeypatch.setattr(voice, "listen_once", fake_listen_once)
    assert voice.listen_async(7)
    assert voice.is_listening
    assert not voice.listen_async(8)
    release.set()
    deadline = time.time() + 2
    while voice.is_listening and time.time() < deadline:
        time.sleep(0.02)
    assert not voice.is_listening
    voice.close()

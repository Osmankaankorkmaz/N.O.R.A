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


class _FakeAudio:
    sample_rate = 16000
    frame_data = b"\x00\x10" * 800  # little-endian 16-bit samples, amplitude 4096


class _FakeRecognizer:
    def __init__(self):
        self.energy_threshold = 250
        self.timeout = False

    def adjust_for_ambient_noise(self, source, duration=0.5):
        pass

    def listen(self, source, timeout=6, phrase_time_limit=10):
        if self.timeout:
            import speech_recognition as sr

            raise sr.WaitTimeoutError()
        return _FakeAudio()

    def recognize_google(self, audio, language="tr-TR", endpoint=None):
        return "nora selam"


class _FakeMicrophone:
    def __init__(self, sample_rate=16000, device_index=None):
        self.device_index = device_index

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @staticmethod
    def list_microphone_names():
        return ["Test Mic"]


def _install_fake_sr(monkeypatch, recognizer):
    import sys
    from types import SimpleNamespace
    import speech_recognition as real_sr

    fake = SimpleNamespace(
        Recognizer=lambda: recognizer,
        Microphone=_FakeMicrophone,
        WaitTimeoutError=real_sr.WaitTimeoutError,
        UnknownValueError=real_sr.UnknownValueError,
        RequestError=real_sr.RequestError,
    )
    monkeypatch.setitem(sys.modules, "speech_recognition", fake)


def test_capture_emits_listening_signals(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=False)
    rec = _FakeRecognizer()
    _install_fake_sr(monkeypatch, rec)
    started, stopped = [], []
    voice.listening_started.connect(started.append)
    voice.listening_stopped.connect(stopped.append)
    text, error = voice._capture(6, 10, 0.1, request_id=5)
    assert text == "nora selam" and not error
    assert started == [5] and stopped == [5]
    assert voice.last_capture_info["bytes"] > 0
    voice.close()


def test_manual_timeout_is_reported_but_wake_timeout_is_silent(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=False)
    rec = _FakeRecognizer()
    rec.timeout = True
    _install_fake_sr(monkeypatch, rec)
    text, error = voice._capture(6, 10, 0.1, wake=False, request_id=5)
    assert not text and "ses algılamadı" in error
    text, error = voice._capture(3, 4, 0.1, wake=True, request_id=0)
    assert not text and not error
    voice.close()


def test_microphone_test_is_local_and_reports_level(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=False)
    _install_fake_sr(monkeypatch, _FakeRecognizer())
    result = voice.test_microphone(timeout=1)
    assert "Sesini algıladım" in result
    assert voice.last_capture_info["heard"] is True
    voice.close()

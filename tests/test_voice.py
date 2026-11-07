import threading
import time

from nora.nora_voice import NoraVoice, speech_text, split_speech


def test_speech_text_strips_emoji_and_tags_already_removed():
    assert speech_text("Merhaba 💕🐾  senpai~") == "Merhaba senpai~"


def test_tts_disabled_does_not_queue(qapp):
    voice = NoraVoice(tts_enabled=False)
    assert not voice.speak("merhaba")
    assert not voice.is_speaking
    voice.close()


def test_wake_phrase_is_exact_and_local():
    assert NoraVoice._is_wake_hypothesis("hey nora")
    assert NoraVoice._is_wake_hypothesis("HEY   NORA")
    assert not NoraVoice._is_wake_hypothesis("nora")
    assert not NoraVoice._is_wake_hypothesis("norayı severim")
    assert not NoraVoice._is_wake_hypothesis("hey no ra")


def test_local_wake_decoder_uses_exact_keyphrase(qapp):
    pytest = __import__("pytest")
    pytest.importorskip("pocketsphinx")
    voice = NoraVoice(tts_enabled=False)
    decoder = voice._make_wake_decoder()
    assert decoder.get_kws("nora_wake") == "hey nora"
    voice.close()


def test_wake_loop_activates_without_cloud_stt(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=False)
    results = []
    started = []
    done = threading.Event()
    voice.listening_started.connect(started.append)

    def fail_cloud(*a, **k):
        raise AssertionError("wake watcher must not call cloud STT")

    monkeypatch.setattr(voice, "_capture", fail_cloud)
    sessions = iter([True, False, False])
    monkeypatch.setattr(voice, "_local_wake_session", lambda: next(sessions, False))

    def callback(text):
        results.append(text)
        done.set()

    voice.start_wake_word_listener(callback)
    assert done.wait(3)
    voice.stop_wake_word_listener()
    assert results == [""]
    assert not started  # background watcher is not command listening
    voice.close()


def test_wake_listener_pauses_while_speaking(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=False)
    called = []
    monkeypatch.setattr(
        voice, "_local_wake_session", lambda: called.append(True) or True
    )
    with voice._speech_lock:
        voice._speech_pending = 1
    voice.start_wake_word_listener()
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

    def get_raw_data(self, convert_rate=16000, convert_width=2):
        return self.frame_data


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

    def recognize_google(self, audio, language="tr-TR", endpoint=None, show_all=False):
        if show_all:
            return {
                "results": [
                    {"alternatives": [{"transcript": "nora selam", "confidence": 0.9}]}
                ]
            }
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


def test_local_command_stt_never_calls_google(qapp, monkeypatch):
    from types import SimpleNamespace

    rec = _FakeRecognizer()

    def forbidden(*args, **kwargs):
        raise AssertionError("local backend must not call Google")

    rec.recognize_google = forbidden
    _install_fake_sr(monkeypatch, rec)
    calls = []
    local = SimpleNamespace(
        transcribe=lambda pcm, rate: calls.append((pcm, rate)) or "uyu"
    )
    voice = NoraVoice(tts_enabled=False, stt_backend="local", local_speech=local)
    text, error = voice._capture(1, 2, 0.1, request_id=4)
    assert text == "uyu" and not error
    assert calls and voice.last_capture_info["backend"] == "local"
    voice.close()


def test_missing_local_model_does_not_fallback_to_cloud(qapp, monkeypatch):
    from types import SimpleNamespace
    from nora.nora_local_ai import LocalModelMissing

    rec = _FakeRecognizer()

    def forbidden(*args, **kwargs):
        raise AssertionError("missing local model must not upload audio")

    rec.recognize_google = forbidden
    _install_fake_sr(monkeypatch, rec)

    def missing(*args):
        raise LocalModelMissing("model yok")

    voice = NoraVoice(
        tts_enabled=False,
        stt_backend="local",
        local_speech=SimpleNamespace(transcribe=missing),
    )
    text, error = voice._capture(1, 2, 0.1)
    assert not text and "model yok" in error
    voice.close()


def test_speech_text_cleans_markdown_and_keeps_long_replies():
    cleaned = speech_text(
        "**Merhaba** [link](https://example.com) `kod` 💕\n```python\nprint(1)\n```"
    )
    assert "Merhaba" in cleaned and "link" in cleaned and "kod" in cleaned
    assert "https://" not in cleaned and "```" not in cleaned and "💕" not in cleaned
    long_text = "Bu uzun bir yanıt cümlesi. " * 200
    assert len(speech_text(long_text)) > 1200
    chunks = split_speech(speech_text(long_text))
    assert len(chunks) > 1
    assert " ".join(chunks) == speech_text(long_text)


class _FakeTTSEngine:
    def __init__(self, fail_times=0):
        self.said = []
        self.properties = {}
        self.fail_times = fail_times
        self.runs = 0

    def setProperty(self, name, value):
        self.properties[name] = value

    def getProperty(self, name):
        if name == "voices":
            return []
        return self.properties.get(name)

    def say(self, text):
        self.said.append(text)

    def runAndWait(self):
        self.runs += 1
        if self.runs <= self.fail_times:
            raise RuntimeError("engine busy")

    def stop(self):
        pass


def _wait_voice(qapp, voice, predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_tts_worker_speaks_all_chunks_and_clears_pending(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=True)
    engine = _FakeTTSEngine()
    monkeypatch.setattr(voice, "_make_engine", lambda: engine)
    started, finished = [], []
    voice.speaking_started.connect(lambda: started.append(True))
    voice.speaking_finished.connect(lambda: finished.append(True))
    text = "Sesli yanıt cümlesi. " * 120
    assert voice.speak(text)
    assert _wait_voice(
        qapp,
        voice,
        lambda: not voice.is_speaking and engine.runs > 1 and bool(finished),
    )
    qapp.processEvents()
    assert " ".join(engine.said) == speech_text(text)
    assert started and finished
    assert voice.diagnose_speech().startswith("Sesli yanıt açık")
    voice.close()


def test_tts_worker_retries_with_fresh_engine(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=True)
    engines = [_FakeTTSEngine(fail_times=1), _FakeTTSEngine()]
    monkeypatch.setattr(voice, "_make_engine", lambda: engines.pop(0))
    errors = []
    voice.speech_error.connect(errors.append)
    assert voice.speak("Tek denemede bozulursa yeniden dene.")
    assert _wait_voice(qapp, voice, lambda: not voice.is_speaking and len(engines) == 0)
    assert voice._engine is not None and voice._engine.said
    assert not errors
    assert not voice.last_speech_error
    voice.close()


def test_tts_failure_is_visible_not_silent(qapp, monkeypatch):
    voice = NoraVoice(tts_enabled=True)
    monkeypatch.setattr(voice, "_make_engine", lambda: _FakeTTSEngine(fail_times=10))
    errors = []
    voice.speech_error.connect(errors.append)
    assert voice.speak("Bu yanıt sesli gelmeli.")
    assert _wait_voice(qapp, voice, lambda: not voice.is_speaking and bool(errors))
    assert "Ses motorunu açamadım" in errors[-1]
    assert voice.last_speech_error
    voice.close()


def test_wake_decoder_adds_turkish_nora_pronunciations_but_gate_stays_exact(qapp):
    pytest = __import__("pytest")
    pytest.importorskip("pocketsphinx")
    voice = NoraVoice(tts_enabled=False)
    decoder = voice._make_wake_decoder()
    assert decoder.get_kws("nora_wake") == "hey nora"
    assert decoder.lookup_word("nora(2)") == "N OW R AH"
    assert decoder.lookup_word("nora(3)") == "N AO R AA"
    assert not voice._is_wake_hypothesis("hey nova")
    assert not voice._is_wake_hypothesis("hey no ra")
    voice.close()


def test_recognizer_allows_turkish_pause_between_name_and_command(qapp):
    voice = NoraVoice(tts_enabled=False)
    recognizer = voice._recognizer()
    assert recognizer.pause_threshold >= 0.8
    assert recognizer.non_speaking_duration >= 0.5
    voice.close()


def test_google_capture_repairs_misheard_name_without_extra_request(qapp, monkeypatch):
    class Rec(_FakeRecognizer):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def recognize_google(
            self, audio, language="tr-TR", endpoint=None, show_all=False
        ):
            self.calls += 1
            assert show_all
            return {
                "results": [
                    {
                        "alternatives": [
                            {
                                "transcript": "hey nova ikinci monitöre geç",
                                "confidence": 0.91,
                            }
                        ]
                    }
                ]
            }

    rec = Rec()
    _install_fake_sr(monkeypatch, rec)
    voice = NoraVoice(tts_enabled=False)
    text, error = voice._capture(1, 2, 0.1, request_id=9)
    assert not error
    assert text == "Hey Nora, ikinci monitöre geç"
    assert rec.calls == 1
    assert voice.last_transcript.address_corrected
    assert voice.last_transcript.heard_name == "nova"
    assert voice.last_capture_info["address_corrected"] is True
    voice.close()


def test_local_capture_repairs_bare_misheard_name_only_for_safe_command(
    qapp, monkeypatch
):
    from types import SimpleNamespace

    _install_fake_sr(monkeypatch, _FakeRecognizer())
    local = SimpleNamespace(transcribe=lambda pcm, rate: "nova uyu")
    voice = NoraVoice(tts_enabled=False, stt_backend="local", local_speech=local)
    text, error = voice._capture(1, 2, 0.1, request_id=3)
    assert text == "uyu" and not error
    assert voice.last_transcript.address_corrected
    local = SimpleNamespace(transcribe=lambda pcm, rate: "nova nasılsın")
    voice.local_speech = local
    text, error = voice._capture(1, 2, 0.1, request_id=4)
    assert text == "nova nasılsın" and not error
    assert not voice.last_transcript.address_corrected
    voice.close()

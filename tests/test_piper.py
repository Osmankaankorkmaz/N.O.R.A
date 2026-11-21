import json
import threading
from pathlib import Path

import pytest

from nora.nora_local_ai import LocalModelMissing
from nora.nora_piper import PiperSpeech
from nora.nora_voice import NoraVoice


class Chunk:
    sample_rate = 22050
    sample_channels = 1
    audio_int16_bytes = b"\x00\x10" * 2048


class FakeVoice:
    def synthesize(self, text, syn_config=None):
        yield Chunk()


class Stream:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.writes = 0
        self.aborted = False
        self.on_write = None

    def start(self):
        pass

    def write(self, data):
        self.writes += 1
        if self.on_write:
            self.on_write()

    def stop(self):
        pass

    def close(self):
        pass

    def abort(self):
        self.aborted = True


class Audio:
    def __init__(self):
        self.streams = []

    def OutputStream(self, **kwargs):
        stream = Stream(**kwargs)
        self.streams.append(stream)
        return stream


def valid_piper_config():
    return {
        "num_symbols": 256,
        "num_speakers": 1,
        "audio": {"sample_rate": 22050},
        "espeak": {"voice": "tr"},
        "phoneme_id_map": {"a": [1]},
    }


def import_fake_model(tmp_path):
    source = tmp_path / "voice.onnx"
    source.write_bytes(b"onnx")
    Path(str(source) + ".json").write_text(
        json.dumps(valid_piper_config()), encoding="utf-8"
    )
    return source


def test_piper_import_requires_config_and_plays_locally(tmp_path):
    source = tmp_path / "voice.onnx"
    source.write_bytes(b"onnx")
    piper = PiperSpeech(
        tmp_path / "models",
        voice_loader=lambda *a, **k: FakeVoice(),
        audio_backend=Audio(),
        config_factory=lambda **kw: kw,
    )
    with pytest.raises(ValueError):
        piper.import_model(source)
    Path(str(source) + ".json").write_text(
        json.dumps(valid_piper_config()), encoding="utf-8"
    )
    piper.import_model(source)
    assert piper.cached()
    assert piper.speak("Merhaba", volume=0.8, rate=180)
    piper.close()


def test_piper_stop_aborts_playback_and_missing_model_is_explicit(tmp_path):
    audio = Audio()
    piper = PiperSpeech(
        tmp_path / "models",
        voice_loader=lambda *a, **k: FakeVoice(),
        audio_backend=audio,
        config_factory=lambda **kw: kw,
    )
    with pytest.raises(LocalModelMissing):
        piper.speak("Merhaba")
    source = import_fake_model(tmp_path)
    piper.import_model(source)
    stopped = threading.Event()
    original = audio.OutputStream

    def factory(**kwargs):
        stream = original(**kwargs)
        stream.on_write = stopped.set
        return stream

    audio.OutputStream = factory
    assert not piper.speak("Merhaba", should_stop=stopped.is_set)
    piper.close()


def test_voice_piper_failure_does_not_fallback_to_system(qapp):
    class Broken:
        def speak(self, *a, **k):
            raise ValueError("Piper bozuk")

        def stop(self):
            pass

    voice = NoraVoice(tts_enabled=True, tts_backend="piper", local_tts=Broken())
    errors = []
    voice.speech_error.connect(errors.append)
    voice._speak_chunks(voice._speech_generation, ["Merhaba"])
    assert errors and "gizlice" in errors[0]
    assert voice._engine is None
    voice.close()


def test_barge_in_stops_speech_only_after_exact_wake(qapp):
    voice = NoraVoice(tts_enabled=False, barge_in=True)
    detected = threading.Event()
    voice.wake_word_detected.connect(lambda _: detected.set())
    monkey = __import__("pytest").MonkeyPatch()
    monkey.setattr(voice, "_local_wake_session", lambda: True)
    with voice._speech_lock:
        voice._speech_pending = 1
    voice.start_wake_word_listener(callback=lambda _: detected.set())
    try:
        assert detected.wait(2)
        deadline = __import__("time").time() + 2
        while voice.is_speaking and __import__("time").time() < deadline:
            qapp.processEvents()
            __import__("time").sleep(0.02)
        assert not voice.is_speaking
        assert not voice._is_wake_hypothesis("nora")
        assert voice._is_wake_hypothesis("hey nora")
    finally:
        monkey.undo()
        voice.close()

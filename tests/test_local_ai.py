import base64
import io
from types import SimpleNamespace

import pytest

from nora.nora_local_ai import LocalModelMissing, LocalOCR, LocalSpeech


def test_local_speech_never_downloads_without_permission(tmp_path):
    speech = LocalSpeech(tmp_path)
    assert not speech.cached()
    with pytest.raises(LocalModelMissing):
        speech.ensure_model()
    with pytest.raises(ValueError):
        speech.transcribe(b"bad")
    speech.close()


def test_local_whisper_uses_turkish_and_in_memory_pcm(tmp_path, monkeypatch):
    pytest.importorskip("faster_whisper")
    calls = []

    class Model:
        def transcribe(self, samples, **kwargs):
            calls.append((len(samples), kwargs))
            return iter([SimpleNamespace(text=" hey nora uyu ")]), None

    speech = LocalSpeech(tmp_path)
    monkeypatch.setattr(speech, "cached", lambda: True)
    speech._model = Model()
    assert speech.transcribe(b"\x00\x00" * 1600) == "hey nora uyu"
    assert calls[0][0] == 1600 and calls[0][1]["language"] == "tr"
    speech.close()


def test_real_local_ocr_if_optional_package_installed():
    pytest.importorskip("rapidocr_onnxruntime")
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (600, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.text(
        (30, 50), "NORA TEST 123", fill="black", font=ImageFont.load_default(size=42)
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    result = LocalOCR().read(base64.b64encode(buffer.getvalue()).decode())
    assert "NORA" in result and "123" in result

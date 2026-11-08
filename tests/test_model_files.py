import struct
import threading
import time
from pathlib import Path

import pytest

from nora.nora_local_llm import LocalChatModel
from nora.nora_model_files import (
    staged_import,
    validate_gguf_header,
    validate_piper_config,
)
from nora.nora_piper import PiperSpeech


def gguf_file(path):
    path.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 0, 0))


def test_gguf_header_and_piper_config_reject_wrong_files(tmp_path):
    fake = tmp_path / "fake.gguf"
    fake.write_text("Bu bir model değil", encoding="utf-8")
    with pytest.raises(ValueError, match="GGUF"):
        validate_gguf_header(fake)
    gguf_file(fake)
    validate_gguf_header(fake)
    config = tmp_path / "voice.onnx.json"
    config.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        validate_piper_config(config)


def test_failed_pair_replacement_restores_previous_model(tmp_path, monkeypatch):
    directory = tmp_path / "models"
    directory.mkdir()
    (directory / "a").write_text("old-a", encoding="utf-8")
    (directory / "b").write_text("old-b", encoding="utf-8")
    source_a, source_b = tmp_path / "a", tmp_path / "b"
    source_a.write_text("new-a", encoding="utf-8")
    source_b.write_text("new-b", encoding="utf-8")
    import nora.nora_model_files as module

    original = module.os.replace

    def fail_second(src, dst):
        if Path(dst).name == "b":
            raise OSError("disk failure")
        return original(src, dst)

    monkeypatch.setattr(module.os, "replace", fail_second)
    with pytest.raises(ValueError, match="önceki dosyalar"):
        with staged_import(directory, {"a": source_a, "b": source_b}, overwrite=True):
            pass
    assert (directory / "a").read_text() == "old-a"
    assert (directory / "b").read_text() == "old-b"
    assert not list(directory.glob(".model-import-*"))


def test_invalid_import_does_not_replace_existing_model(tmp_path):
    source = tmp_path / "model.gguf"
    gguf_file(source)
    chat = LocalChatModel(tmp_path / "models")
    chat.import_model(source)
    target = chat.model_dir / "model.gguf"
    before = target.read_bytes()
    source.write_text("bozuk dosya", encoding="utf-8")
    with pytest.raises(ValueError):
        chat.import_model(source, overwrite=True)
    assert target.read_bytes() == before
    chat.close()


def test_piper_stop_does_not_wait_for_model_lock(tmp_path):
    piper = PiperSpeech(tmp_path)
    piper._lock.acquire()
    done = threading.Event()
    thread = threading.Thread(target=lambda: (piper.stop(), done.set()))
    thread.start()
    assert done.wait(0.5)
    thread.join()
    piper._lock.release()


def test_local_chat_shutdown_does_not_block_on_generation(tmp_path):
    entered, release = threading.Event(), threading.Event()
    closed = []

    class Model:
        def create_chat_completion(self, **kwargs):
            entered.set()
            assert release.wait(3)
            return {"choices": [{"message": {"content": "Bitti."}}]}

        def close(self):
            closed.append(True)

    source = tmp_path / "model.gguf"
    gguf_file(source)
    chat = LocalChatModel(tmp_path / "models", model_factory=lambda **kw: Model())
    chat.import_model(source)
    result = []
    worker = threading.Thread(
        target=lambda: result.append(chat.chat([{"role": "user", "content": "selam"}]))
    )
    worker.start()
    assert entered.wait(2)
    started = time.monotonic()
    chat.close()
    assert time.monotonic() - started < 0.3
    assert not closed
    release.set()
    worker.join(3)
    assert not worker.is_alive()
    assert result == ["Bitti."]
    assert closed == [True]

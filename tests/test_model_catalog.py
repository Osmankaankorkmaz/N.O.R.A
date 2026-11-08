import hashlib
import json
import struct

import pytest

from nora.nora_model_catalog import (
    ModelCancelled,
    ModelCatalog,
    safe_model_name,
    sha256_file,
)


def gguf(path):
    path.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 0, 0))


def test_catalog_hashes_verifies_annotates_and_deletes_without_touching_bytes(tmp_path):
    directory = tmp_path / "models"
    directory.mkdir()
    model = directory / "a.gguf"
    gguf(model)
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "a.gguf").write_bytes(model.read_bytes())
    catalog = ModelCatalog(directory, "chat")
    catalog.write_staged(
        stage,
        "a.gguf",
        source_name="kaynak.gguf",
        source_url="https://example.test/model",
        license_note="model kartına bak",
    )
    (directory / "a.gguf.nora.json").write_bytes(
        (stage / "a.gguf.nora.json").read_bytes()
    )
    before = model.read_bytes()
    info = catalog.info("a.gguf")
    assert info.has_record and info.sha256 == hashlib.sha256(before).hexdigest()
    assert "SHA-256" in catalog.verify("a.gguf")
    assert model.read_bytes() == before
    catalog.annotate("a.gguf", license_note="MIT")
    assert catalog.info("a.gguf").license_note == "MIT"
    assert model.read_bytes() == before
    assert "a.gguf" in catalog.listing("a.gguf")
    catalog.delete("a.gguf")
    assert not model.exists()
    assert not (directory / "a.gguf.nora.json").exists()


def test_catalog_detects_tampering_and_missing_record(tmp_path):
    directory = tmp_path / "models"
    directory.mkdir()
    model = directory / "a.gguf"
    gguf(model)
    catalog = ModelCatalog(directory, "chat")
    with pytest.raises(ValueError, match="kaydı yok"):
        catalog.verify("a.gguf")
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "a.gguf").write_bytes(model.read_bytes())
    catalog.write_staged(stage, "a.gguf", source_name="a.gguf")
    (directory / "a.gguf.nora.json").write_bytes(
        (stage / "a.gguf.nora.json").read_bytes()
    )
    model.write_bytes(model.read_bytes() + b"degisti")
    with pytest.raises(ValueError, match="değişmiş"):
        catalog.verify("a.gguf")


def test_hash_and_name_safety(tmp_path):
    path = tmp_path / "x.bin"
    path.write_bytes(b"abc" * 1024)
    assert sha256_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ModelCancelled):
        sha256_file(path, should_stop=lambda: True)
    assert safe_model_name("../güzel model.gguf", ".gguf") == "g_zel_model.gguf"
    with pytest.raises(ValueError):
        safe_model_name("../evil.gguf", ".onnx")
    with pytest.raises(ValueError):
        ModelCatalog(tmp_path, "chat").info("../evil.gguf")


def test_piper_catalog_requires_pair_and_sidecar(tmp_path):
    directory = tmp_path / "piper"
    directory.mkdir()
    (directory / "v.onnx").write_bytes(b"onnx")
    catalog = ModelCatalog(directory, "piper")
    with pytest.raises(ValueError, match="eksik"):
        catalog.info("v.onnx")
    (directory / "v.onnx.json").write_text("{}", encoding="utf-8")
    info = catalog.info("v.onnx")
    assert info.files == ("v.onnx", "v.onnx.json") and not info.has_record
    record = (
        json.loads((directory / "v.onnx.nora.json").read_text())
        if (directory / "v.onnx.nora.json").exists()
        else None
    )
    assert record is None

"""Small, dependency-free checks and staged imports for user-selected models.

These checks reject obviously wrong files before copying hundreds of megabytes.
They are not a sandbox or a guarantee that an arbitrary ONNX/GGUF file is safe;
only import models from sources you trust. No model is downloaded here.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .nora_model_catalog import ModelCancelled, check_cancelled


def validate_gguf_header(path: Path) -> None:
    try:
        with Path(path).open("rb") as handle:
            header = handle.read(24)
    except OSError as exc:
        raise ValueError("GGUF dosyası okunamadı.") from exc
    if len(header) != 24:
        raise ValueError("Dosya GGUF değil: başlık eksik.")
    magic, version, tensors, metadata = struct.unpack("<4sIQQ", header)
    if magic != b"GGUF" or version not in {1, 2, 3}:
        raise ValueError("Dosya GGUF değil veya desteklenmeyen bir GGUF sürümü.")
    if tensors > 1_000_000 or metadata > 1_000_000:
        raise ValueError("GGUF başlığındaki tablo sayıları makul sınırı aşıyor.")


def validate_piper_config(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("Piper .onnx.json dosyası geçerli UTF-8 JSON olmalı.") from exc
    if not isinstance(data, dict):
        raise ValueError("Piper yapılandırması bir JSON nesnesi olmalı.")
    try:
        symbols = data["num_symbols"]
        speakers = data["num_speakers"]
        rate = data["audio"]["sample_rate"]
        voice = data["espeak"]["voice"]
        phonemes = data["phoneme_id_map"]
    except (KeyError, TypeError) as exc:
        raise ValueError(
            "Piper yapılandırmasında audio/espeak/num_symbols/num_speakers/phoneme_id_map alanları gerekli."
        ) from exc
    if (
        type(symbols) is not int
        or symbols <= 0
        or type(speakers) is not int
        or speakers < 0
        or type(rate) is not int
        or not 8000 <= rate <= 192000
        or not isinstance(voice, str)
        or not voice.strip()
        or not isinstance(phonemes, dict)
        or not phonemes
    ):
        raise ValueError("Piper yapılandırmasındaki ses/fonem alanları geçersiz.")
    return data


def _copy_checked(
    source: Path, target: Path, should_stop: Callable[[], bool] | None
) -> None:
    with source.open("rb") as src, target.open("wb") as dst:
        while True:
            check_cancelled(should_stop)
            block = src.read(1024 * 1024)
            if not block:
                break
            dst.write(block)
    check_cancelled(should_stop)
    shutil.copystat(source, target)


@contextmanager
def staged_import(
    directory: Path,
    sources: dict[str, Path],
    *,
    overwrite: bool = False,
    should_stop: Callable[[], bool] | None = None,
) -> Iterator[Path]:
    """Copy beside the destination, validate in the caller, then replace.

    A failed copy never touches an existing model. If a multi-file replacement
    fails, previous files are restored. This is not a power-loss atomicity claim.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    targets = {name: directory / name for name in sources}
    for name, target in targets.items():
        if (
            not name
            or Path(name).name != name
            or name in {".", ".."}
            or target.is_symlink()
        ):
            raise ValueError("Model hedef adı güvenli değil.")
    if any(target.exists() for target in targets.values()) and not overwrite:
        raise ValueError("Bu model zaten var; üzerine yazmak için açık onay gerekir.")
    with tempfile.TemporaryDirectory(prefix=".model-import-", dir=directory) as tmp:
        root = Path(tmp)
        stage = root / "new"
        stage.mkdir()
        for name, source in sources.items():
            source = Path(source)
            if source.is_symlink() or not source.is_file():
                raise ValueError("Model kaynağı normal bir dosya olmalı.")
            _copy_checked(source, stage / name, should_stop)
        check_cancelled(should_stop)
        yield stage
        check_cancelled(should_stop)
        # Callers may generate sidecars inside the staging directory. Commit
        # those too, instead of leaving an import without integrity metadata.
        for path in stage.iterdir():
            if path.is_symlink() or not path.is_file():
                raise ValueError("Geçici model klasöründe beklenmeyen öğe var.")
            if path.name not in targets:
                if Path(path.name).name != path.name or path.name in {".", ".."}:
                    raise ValueError("Model hedef adı güvenli değil.")
                target = directory / path.name
                if target.is_symlink():
                    raise ValueError("Model hedef adı güvenli değil.")
                if target.exists() and not overwrite:
                    raise ValueError(
                        "Bu model zaten var; üzerine yazmak için açık onay gerekir."
                    )
                targets[path.name] = target
        backup = root / "previous"
        backup.mkdir()
        existed = set()
        for name, target in targets.items():
            if target.exists():
                existed.add(name)
                _copy_checked(target, backup / name, should_stop)
        replaced = set()
        try:
            for name, target in targets.items():
                check_cancelled(should_stop)
                os.replace(stage / name, target)
                replaced.add(name)
        except (OSError, ModelCancelled) as exc:
            for name in reversed(list(replaced)):
                target = targets[name]
                if name in existed:
                    os.replace(backup / name, target)
                else:
                    target.unlink(missing_ok=True)
            if isinstance(exc, ModelCancelled):
                raise
            raise ValueError(
                "Model dosyaları yerleştirilemedi; önceki dosyalar korundu."
            ) from exc

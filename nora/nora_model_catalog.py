"""Local inventory for user-imported GGUF/Piper models.

The catalog never downloads models or infer licenses. It records explicit user
imports, SHA-256 digests and optional source/license notes beside the files so
large models can be inspected and verified without loading them into RAM.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

SIDECAR_SUFFIX = ".nora.json"
_CHUNK = 1024 * 1024


class ModelCancelled(RuntimeError):
    """Raised when a long hash/copy operation is cancelled by the user."""


def check_cancelled(should_stop: Callable[[], bool] | None) -> None:
    if should_stop is not None and should_stop():
        raise ModelCancelled("İşlem iptal edildi.")


def sha256_file(path: Path, *, should_stop: Callable[[], bool] | None = None) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            check_cancelled(should_stop)
            block = handle.read(_CHUNK)
            if not block:
                break
            digest.update(block)
    check_cancelled(should_stop)
    return digest.hexdigest()


def safe_model_name(source_name: str, suffix: str) -> str:
    if suffix not in {".gguf", ".onnx"}:
        raise ValueError("Desteklenmeyen model türü.")
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(source_name).name)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}" + re.escape(suffix), name):
        raise ValueError("Model dosya adı geçersiz.")
    return name


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"


@dataclass(frozen=True)
class ModelInfo:
    name: str
    kind: str
    size: int
    files: tuple[str, ...]
    sha256: str
    source_name: str
    source_url: str
    license_note: str
    imported_at: str
    has_record: bool


class ModelCatalog:
    def __init__(self, directory: Path, kind: str) -> None:
        if kind not in {"chat", "piper"}:
            raise ValueError("Model katalog türü chat/piper olmalı.")
        self.directory = Path(directory)
        self.kind = kind
        self.suffix = ".gguf" if kind == "chat" else ".onnx"

    def _path(self, name: str) -> Path:
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}" + re.escape(self.suffix), str(name)
        ):
            raise ValueError("Model adı güvenli bir dosya adı olmalı.")
        path = (self.directory / name).resolve()
        if path.parent != self.directory.resolve() or path.is_symlink():
            raise ValueError("Model yolu güvenli değil.")
        return path

    def _files(self, name: str) -> tuple[str, ...]:
        return (name, name + ".json") if self.kind == "piper" else (name,)

    def names(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        return sorted(
            path.name
            for path in self.directory.glob("*" + self.suffix)
            if path.is_file() and not path.is_symlink()
        )

    def exists_for_source(self, source_name: str) -> bool:
        try:
            return self._path(safe_model_name(source_name, self.suffix)).exists()
        except ValueError:
            return False

    def write_staged(
        self,
        stage: Path,
        name: str,
        *,
        source_name: str,
        source_url: str = "",
        license_note: str = "",
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        """Write a sidecar into an already staged import directory."""
        files = {}
        for filename in self._files(name):
            path = Path(stage) / filename
            files[filename] = {
                "size": path.stat().st_size,
                "sha256": sha256_file(path, should_stop=should_stop),
            }
        record = {
            "schema": 1,
            "kind": self.kind,
            "name": name,
            "source_name": Path(source_name).name[:160],
            "source_url": str(source_url)[:500],
            "license_note": str(license_note)[:200],
            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "files": files,
        }
        (Path(stage) / (name + SIDECAR_SUFFIX)).write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _record(self, name: str) -> dict | None:
        path = self.directory / (name + SIDECAR_SUFFIX)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if (
            not isinstance(data, dict)
            or data.get("schema") != 1
            or data.get("kind") != self.kind
            or data.get("name") != name
            or not isinstance(data.get("files"), dict)
        ):
            return None
        return data

    def info(self, name: str) -> ModelInfo:
        path = self._path(name)
        if not path.is_file():
            raise ValueError("Model dosyası bulunamadı.")
        filenames = self._files(name)
        for filename in filenames:
            extra = self.directory / filename
            if extra.is_symlink() or not extra.is_file():
                raise ValueError("Model dosyaları eksik veya güvenli değil.")
        size = sum((self.directory / filename).stat().st_size for filename in filenames)
        record = self._record(name)
        if record is None:
            return ModelInfo(
                name, self.kind, size, filenames, "", Path(name).name, "", "", "", False
            )
        files = record["files"]
        digest = ""
        main = files.get(name)
        if isinstance(main, dict) and isinstance(main.get("sha256"), str):
            digest = main["sha256"]
        return ModelInfo(
            name,
            self.kind,
            size,
            filenames,
            digest,
            str(record.get("source_name", ""))[:160],
            str(record.get("source_url", ""))[:500],
            str(record.get("license_note", ""))[:200],
            str(record.get("imported_at", ""))[:40],
            True,
        )

    def verify(
        self, name: str, *, should_stop: Callable[[], bool] | None = None
    ) -> str:
        info = self.info(name)
        if not info.has_record:
            raise ValueError(
                "Bu model için içe aktarma bütünlük kaydı yok. Güvenli kaynaktan yeniden içe aktarabilirsin."
            )
        record = self._record(name) or {}
        files = record.get("files", {})
        for filename in info.files:
            expected = files.get(filename, {})
            digest = sha256_file(self.directory / filename, should_stop=should_stop)
            if not isinstance(expected, dict) or digest != expected.get("sha256"):
                raise ValueError(
                    f"Bütünlük doğrulanamadı: {filename} değişmiş veya bozulmuş. Modeli kullanmadan önce güvenli kaynaktan yeniden içe aktar."
                )
        return f"Bütünlük doğrulandı: {name} · SHA-256 eşleşti. Dosya içeriği değiştirilmedi. 🛡️"

    def delete(self, name: str) -> None:
        self._path(name)
        for filename in (*self._files(name), name + SIDECAR_SUFFIX):
            target = self.directory / filename
            if target.is_symlink():
                raise ValueError("Symlink model dosyası silinmedi.")
            if target.is_file():
                target.unlink()

    def describe(self, name: str) -> str:
        info = self.info(name)
        label = "GGUF" if self.kind == "chat" else "Piper"
        lines = [
            f"{label} modeli · {info.name}",
            f"Boyut: {human_size(info.size)}",
            f"Dosyalar: {', '.join(info.files)}",
            f"Kaynak dosya: {info.source_name or 'bilinmiyor'}",
            f"Kaynak URL: {info.source_url or 'belirtilmedi'}",
            f"Lisans notu: {info.license_note or 'belirtilmedi; model kartını kontrol et'}",
            f"İçe aktarma: {info.imported_at or 'eski kayıt yok'}",
            f"SHA-256: {info.sha256[:16] + '…' if info.sha256 else 'kayıt yok'}",
            "Not: SHA-256 değişmemiş dosyayı gösterir; modelin güvenli/lisanslı olduğunu kanıtlamaz.",
        ]
        return "\n".join(lines)

    def listing(self, selected: str = "") -> str:
        label = "GGUF sohbet" if self.kind == "chat" else "Piper ses"
        names = self.names()
        lines = [f"{label} modelleri · yerel, otomatik indirme yok"]
        if not names:
            lines.append("İçe aktarılmış model yok.")
        for name in names[:30]:
            try:
                info = self.info(name)
                mark = " · seçili" if name == selected else ""
                record = (
                    "bütünlük kaydı var" if info.has_record else "bütünlük kaydı yok"
                )
                license_note = info.license_note or "lisans belirtilmedi"
                lines.append(
                    f"• {name}{mark} · {human_size(info.size)} · {record} · {license_note}"
                )
            except ValueError as exc:
                lines.append(f"• {name} · okunamadı: {exc}")
        return "\n".join(lines)

    def annotate(
        self, name: str, *, source_url: str = "", license_note: str = ""
    ) -> None:
        """Let the user record source/license metadata without changing model bytes."""
        self._path(name)
        record = self._record(name)
        if record is None:
            raise ValueError("Önce modeli içe aktararak bütünlük kaydı oluştur.")
        record["source_url"] = str(source_url)[:500]
        record["license_note"] = str(license_note)[:200]
        target = self.directory / (name + SIDECAR_SUFFIX)
        fd, temporary = tempfile.mkstemp(prefix=".catalog-", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record, handle, ensure_ascii=False, indent=2)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

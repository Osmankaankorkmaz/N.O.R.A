"""Optional user-supplied GGUF chat model via llama.cpp. No model download.

The model file is imported explicitly into Nora's data directory and loaded on demand in a worker. Selecting local chat never falls back to Groq silently.
"""

from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path
from typing import Any

from .nora_local_ai import LocalModelMissing
from .nora_model_files import staged_import, validate_gguf_header

_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.gguf")
MAX_MODEL_BYTES = 8 * 1024 * 1024 * 1024


def strip_reasoning(text: str) -> str:
    value = re.sub(
        r"<think\b[^>]*>.*?</think>",
        "",
        str(text or ""),
        flags=re.IGNORECASE | re.DOTALL,
    )
    value = re.split(r"<think\b", value, maxsplit=1, flags=re.IGNORECASE)[0]
    return value.strip()[:12000]


class LocalChatModel:
    def __init__(self, model_dir: Path, *, model_factory: Any = None) -> None:
        self.model_dir = Path(model_dir)
        self.model_name = ""
        self._model: Any = None
        self._model_factory = model_factory
        self._lock = threading.RLock()
        self._inference_lock = threading.Lock()
        self._closed = False
        self._loading = False

    def configure(self, model_name: str) -> None:
        model_name = str(model_name or "").strip()
        if model_name and not _NAME_RE.fullmatch(model_name):
            raise ValueError("Yerel sohbet modeli güvenli bir .gguf dosya adı olmalı.")
        with self._lock:
            if self._closed:
                raise ValueError("Yerel sohbet motoru kapatıldı.")
            if model_name != self.model_name:
                self._model = None
            self.model_name = model_name

    def _path(self) -> Path:
        if not self.model_name:
            raise LocalModelMissing(
                "Yerel sohbet modeli seçilmedi. Menüden bir GGUF modeli içe aktar senpai. 🧠"
            )
        path = (self.model_dir / self.model_name).resolve()
        if path.parent != self.model_dir.resolve() or path.is_symlink():
            raise ValueError("Model yolu güvenli değil.")
        return path

    def cached(self) -> bool:
        try:
            path = self._path()
            return path.is_file() and path.stat().st_size > 0
        except (ValueError, LocalModelMissing):
            return False

    def import_model(self, source: Path, *, overwrite: bool = False) -> str:
        source = Path(source)
        if (
            source.is_symlink()
            or not source.is_file()
            or source.suffix.lower() != ".gguf"
        ):
            raise ValueError("Normal bir .gguf model dosyası seç senpai.")
        size = source.stat().st_size
        if not 0 < size <= MAX_MODEL_BYTES:
            raise ValueError("GGUF modeli 8 GB altında olmalı.")
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", source.name)
        if not _NAME_RE.fullmatch(name):
            raise ValueError("Model dosya adı geçersiz.")
        self.model_dir.mkdir(parents=True, exist_ok=True)
        target = self.model_dir / name
        if target.exists() and not overwrite:
            raise ValueError(
                "Bu model zaten var; üzerine yazmak için açık onay gerekir."
            )
        free = shutil.disk_usage(self.model_dir).free
        if free < size + 64 * 1024 * 1024:
            raise ValueError("Model için yeterli boş disk alanı yok.")
        validate_gguf_header(source)
        with staged_import(
            self.model_dir, {name: source}, overwrite=overwrite
        ) as stage:
            validate_gguf_header(stage / name)
        self.configure(name)
        return f"Yerel sohbet modeli içe aktarıldı: {name}. 'yerel sohbet modu' ile seçebilirsin. Buluta yüklenmedi. 🧠"

    def ensure_model(self) -> str:
        path = self._path()
        if not path.is_file():
            raise LocalModelMissing(
                "Yerel sohbet modeli bulunamadı. Menüden GGUF modelini içe aktar. 🧠"
            )
        retired = None
        with self._lock:
            if self._closed:
                raise ValueError("Yerel sohbet motoru kapatıldı.")
            if self._model is None:
                factory = self._model_factory
                if factory is None:
                    try:
                        from llama_cpp import Llama
                    except ImportError as exc:
                        raise ValueError(
                            "Yerel sohbet için llama-cpp-python kurulu olmalı. requirements-chat.txt dosyasını kur senpai. 🧠"
                        ) from exc
                    factory = Llama
                self._loading = True
                try:
                    self._model = factory(
                        model_path=str(path),
                        n_ctx=4096,
                        n_threads=4,
                        n_gpu_layers=0,
                        verbose=False,
                        use_mmap=True,
                        use_mlock=False,
                    )
                except Exception as exc:
                    raise ValueError(
                        "GGUF modeli yüklenemedi. Dosyayı, RAM'i ve llama-cpp-python kurulumunu kontrol et. Buluta geçilmedi."
                    ) from exc
                finally:
                    self._loading = False
                    if self._closed:
                        retired, self._model = self._model, None
            if self._closed:
                raise ValueError("Yerel sohbet motoru kapatıldı.")
            message = f"Yerel sohbet modeli hazır: {self.model_name}. Sohbet cihazında işlenir. 🧠"
        self._close_model(retired)
        return message

    def chat(self, messages: list[dict[str, str]]) -> str:
        if not isinstance(messages, list) or not 1 <= len(messages) <= 40:
            raise ValueError("Model mesajları geçersiz.")
        for message in messages:
            if (
                not isinstance(message, dict)
                or message.get("role") not in {"system", "user", "assistant"}
                or not isinstance(message.get("content"), str)
                or len(message["content"]) > 16000
            ):
                raise ValueError("Model mesaj biçimi geçersiz.")
        self.ensure_model()
        if not self._inference_lock.acquire(blocking=False):
            raise ValueError("Yerel model kapatılıyor; yeni sohbet başlatılmadı.")
        retired = None
        model = None
        try:
            with self._lock:
                if self._closed:
                    raise ValueError("Yerel sohbet motoru kapatıldı.")
                model = self._model
            # Never hold the state lock during generation: shutdown must remain
            # responsive even when a CPU-only model takes minutes to answer.
            response = model.create_chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=600,
                top_p=0.9,
            )
        finally:
            self._inference_lock.release()
            with self._lock:
                if self._closed and self._model is model:
                    retired, self._model = self._model, None
            self._close_model(retired)
        try:
            raw = response["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Yerel model yanıtı okunamadı.") from exc
        return strip_reasoning(raw)

    def status(self) -> str:
        return (
            f"Yerel sohbet: {self.model_name or 'model seçilmedi'} · {'dosya hazır' if self.cached() else 'dosya yok'}. "
            "GGUF kullanıcı tarafından seçilir; otomatik indirilmez. 🧠"
        )

    @staticmethod
    def _close_model(model: Any) -> None:
        if model is not None:
            try:
                close = getattr(model, "close", None)
                if callable(close):
                    close()
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            self._closed = True
            model = self._model
            if self._loading:
                model = None  # ensure_model cleans up after the load returns
        if model is not None and self._inference_lock.acquire(blocking=False):
            try:
                with self._lock:
                    model, self._model = self._model, None
            finally:
                self._inference_lock.release()
        else:
            model = None  # the generating worker owns the final reference
        self._close_model(model)

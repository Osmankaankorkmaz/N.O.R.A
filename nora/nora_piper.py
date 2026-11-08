"""Optional local Piper neural TTS with interruptible PCM playback.

Model files are imported explicitly by the user. Playback uses small blocks so
stop_speaking/barge-in can abort promptly instead of waiting for a long reply.
"""

from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path
from typing import Any, Callable

from .nora_local_ai import LocalModelMissing
from .nora_model_files import staged_import, validate_piper_config

_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.onnx")
MAX_MODEL_BYTES = 500 * 1024 * 1024


class PiperSpeech:
    def __init__(
        self,
        model_dir: Path,
        *,
        voice_loader: Any = None,
        audio_backend: Any = None,
        config_factory: Any = None,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.model_name = ""
        self._voice_loader = voice_loader
        self._audio = audio_backend
        self._config_factory = config_factory
        self._voice: Any = None
        self._stream: Any = None
        self._lock = threading.RLock()
        self._stream_lock = threading.RLock()
        self._stop = threading.Event()

    def configure(self, model_name: str) -> None:
        model_name = str(model_name or "").strip()
        if model_name and not _NAME_RE.fullmatch(model_name):
            raise ValueError("Piper modeli güvenli bir .onnx dosya adı olmalı.")
        with self._lock:
            if model_name != self.model_name:
                self._voice = None
            self.model_name = model_name

    def _path(self) -> Path:
        if not self.model_name:
            raise LocalModelMissing(
                "Piper modeli seçilmedi. Menüden .onnx ve .onnx.json dosyalarını içe aktar senpai. 🔊"
            )
        path = (self.model_dir / self.model_name).resolve()
        if path.parent != self.model_dir.resolve() or path.is_symlink():
            raise ValueError("Piper model yolu güvenli değil.")
        return path

    def cached(self) -> bool:
        try:
            path = self._path()
            return path.is_file() and Path(str(path) + ".json").is_file()
        except (ValueError, LocalModelMissing):
            return False

    def import_model(self, source: Path, *, overwrite: bool = False) -> str:
        source = Path(source)
        config = Path(str(source) + ".json")
        if (
            source.is_symlink()
            or config.is_symlink()
            or not source.is_file()
            or not config.is_file()
            or source.suffix.lower() != ".onnx"
        ):
            raise ValueError(
                "Piper için normal bir .onnx modeli ve yanındaki .onnx.json dosyası gerekli."
            )
        size = source.stat().st_size + config.stat().st_size
        if not 0 < size <= MAX_MODEL_BYTES:
            raise ValueError("Piper modeli 500 MB altında olmalı.")
        validate_piper_config(config)
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", source.name)
        if not _NAME_RE.fullmatch(name):
            raise ValueError("Piper model dosya adı geçersiz.")
        self.model_dir.mkdir(parents=True, exist_ok=True)
        target = self.model_dir / name
        target_config = Path(str(target) + ".json")
        if (target.exists() or target_config.exists()) and not overwrite:
            raise ValueError(
                "Bu Piper modeli zaten var; üzerine yazmak için açık onay gerekir."
            )
        free = shutil.disk_usage(self.model_dir).free
        if free < size + 32 * 1024 * 1024:
            raise ValueError("Piper modeli için yeterli boş disk alanı yok.")
        with staged_import(
            self.model_dir,
            {name: source, target_config.name: config},
            overwrite=overwrite,
        ) as stage:
            validate_piper_config(stage / target_config.name)
        self.configure(name)
        return (
            f"Piper modeli içe aktarıldı: {name}. 'piper ses modu' ile seçebilirsin. 🔊"
        )

    def ensure_model(self) -> str:
        path = self._path()
        config = Path(str(path) + ".json")
        if not path.is_file() or not config.is_file():
            raise LocalModelMissing(
                "Piper model dosyaları bulunamadı. .onnx ve .onnx.json dosyalarını içe aktar. 🔊"
            )
        with self._lock:
            if self._voice is None:
                loader = self._voice_loader
                if loader is None:
                    try:
                        from piper import PiperVoice
                    except ImportError as exc:
                        raise ValueError(
                            "Piper için piper-tts kurulu olmalı. requirements-piper.txt dosyasını kur senpai. 🔊"
                        ) from exc
                    loader = PiperVoice.load
                try:
                    self._voice = loader(
                        str(path),
                        config_path=str(config),
                        use_cuda=False,
                        download_dir=str(self.model_dir),
                    )
                except Exception as exc:
                    raise ValueError(
                        "Piper modeli yüklenemedi. Model/config dosyalarını ve onnxruntime kurulumunu kontrol et. Sistem sesine gizlice geçilmedi."
                    ) from exc
            return f"Piper hazır: {self.model_name}. Konuşma cihazında üretilir. 🔊"

    def _audio_backend(self) -> Any:
        if self._audio is not None:
            return self._audio
        try:
            import sounddevice as sd

            self._audio = sd
            return sd
        except ImportError as exc:
            raise ValueError(
                "Piper ses çıkışı için sounddevice kurulu olmalı. requirements-piper.txt dosyasını kur senpai. 🔊"
            ) from exc

    def speak(
        self,
        text: str,
        *,
        volume: float = 0.9,
        rate: int = 180,
        should_stop: Callable[[], bool] | None = None,
    ) -> bool:
        self.ensure_model()
        self._stop.clear()
        stopped = should_stop or (lambda: False)
        try:
            import numpy as np
        except ImportError as exc:
            raise ValueError(
                "Piper/numpy kurulumu eksik. requirements-piper.txt dosyasını kur senpai. 🔊"
            ) from exc
        config_factory = self._config_factory
        if config_factory is None:
            try:
                from piper import SynthesisConfig
            except ImportError as exc:
                raise ValueError(
                    "Piper kurulumu eksik. requirements-piper.txt dosyasını kur senpai. 🔊"
                ) from exc
            config_factory = SynthesisConfig
        config = config_factory(
            volume=max(0.0, min(float(volume), 1.0)),
            length_scale=max(0.6, min(180.0 / max(rate, 1), 1.8)),
        )
        audio = self._audio_backend()
        try:
            with self._lock:
                voice = self._voice
            for chunk in voice.synthesize(str(text)[:12000], syn_config=config):
                if self._stop.is_set() or stopped():
                    return False
                pcm = chunk.audio_int16_bytes
                if not pcm:
                    continue
                channels = max(1, int(chunk.sample_channels))
                samples = np.frombuffer(pcm, dtype="<i2").reshape(-1, channels)
                with self._stream_lock:
                    self._stream = audio.OutputStream(
                        samplerate=int(chunk.sample_rate),
                        channels=channels,
                        dtype="int16",
                        blocksize=1024,
                    )
                    stream = self._stream
                try:
                    stream.start()
                    for offset in range(0, len(samples), 1024):
                        if self._stop.is_set() or stopped():
                            return False
                        stream.write(samples[offset : offset + 1024])
                finally:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass
                    with self._stream_lock:
                        self._stream = None
            return not (self._stop.is_set() or stopped())
        except Exception as exc:
            if self._stop.is_set() or stopped():
                return False
            raise ValueError(
                "Piper ses çıkışı açılamadı. Ses cihazını ve sounddevice/PortAudio kurulumunu kontrol et. 🔊"
            ) from exc

    def stop(self) -> None:
        self._stop.set()
        # Do not wait for a model load/synthesis lock while aborting audio.
        with self._stream_lock:
            stream = self._stream
        if stream is not None:
            try:
                stream.abort()
            except Exception:
                pass

    def status(self) -> str:
        return f"Piper: {self.model_name or 'model seçilmedi'} · {'dosyalar hazır' if self.cached() else 'dosya yok'}. Model otomatik indirilmez. 🔊"

    def close(self) -> None:
        self.stop()
        with self._lock:
            self._voice = None

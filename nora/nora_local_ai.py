"""Optional on-device Whisper speech recognition and RapidOCR screen text.

Heavy packages/models are loaded only inside worker threads. Local STT never
falls back to a cloud service. Model downloads require an explicit user action;
captured audio is processed in memory and is not written to disk.
"""

from __future__ import annotations

import base64
import io
import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)
WHISPER_MODELS = {"tiny", "base", "small", "medium"}


class LocalModelMissing(RuntimeError):
    pass


class LocalSpeech:
    def __init__(
        self, model_dir: Path, *, model_name: str = "small", device: str = "auto"
    ) -> None:
        self.model_dir = Path(model_dir)
        self.model_name = model_name if model_name in WHISPER_MODELS else "small"
        self.device = device if device in {"auto", "cpu", "cuda"} else "cpu"
        self._model = None
        self._lock = threading.RLock()

    def configure(self, model_name: str, device: str) -> None:
        with self._lock:
            if model_name not in WHISPER_MODELS or device not in {
                "auto",
                "cpu",
                "cuda",
            }:
                raise ValueError("Geçersiz yerel ses modeli/cihazı.")
            if (model_name, device) != (self.model_name, self.device):
                self.model_name, self.device = model_name, device
                self._model = None

    def cached(self) -> bool:
        snapshots = (
            self.model_dir
            / f"models--Systran--faster-whisper-{self.model_name}"
            / "snapshots"
        )
        return snapshots.is_dir() and any(snapshots.glob("*/model.bin"))

    def ensure_model(self, *, download: bool = False) -> str:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise ValueError(
                "Yerel ses için requirements-local.txt bağımlılıklarını kur senpai (faster-whisper). 🎤"
            ) from exc
        with self._lock:
            if not download and not self.cached():
                raise LocalModelMissing(
                    "Yerel ses modeli henüz indirilmedi. Menüden 'Yerel ses modelini indir'i seç. Sesini buluta göndermedim. 🎤"
                )
            if self._model is None:
                device = self.device
                if device == "auto":
                    try:
                        import ctranslate2

                        device = (
                            "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
                        )
                    except Exception:
                        device = "cpu"
                try:
                    self._model = WhisperModel(
                        self.model_name,
                        device=device,
                        compute_type="float16" if device == "cuda" else "int8",
                        download_root=str(self.model_dir),
                        local_files_only=not download,
                        cpu_threads=4,
                    )
                except Exception as exc:
                    if device == "cuda":
                        raise ValueError(
                            "CUDA ses modeli açılamadı. Ayarlardan yerel ses cihazını CPU yap veya sürücüyü kontrol et. Buluta geçilmedi."
                        ) from exc
                    raise ValueError(
                        "Yerel ses modeli yüklenemedi. Depolama alanını ve model indirmesini kontrol et. Buluta ses gönderilmedi."
                    ) from exc
            return f"Yerel Whisper hazır: {self.model_name}. Komut sesi cihazında işlenir. 🎤"

    def transcribe(self, pcm: bytes, sample_rate: int = 16000) -> str:
        if not pcm or len(pcm) > 3_200_000 or sample_rate != 16000 or len(pcm) % 2:
            raise ValueError("Ses kaydı okunamadı; 16 kHz PCM bekleniyordu.")
        self.ensure_model()
        import numpy as np

        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        with self._lock:
            segments, _ = self._model.transcribe(
                samples,
                language="tr",
                beam_size=3,
                vad_filter=True,
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            text = " ".join(str(segment.text).strip() for segment in segments).strip()
        return text[:4000]

    def close(self) -> None:
        with self._lock:
            self._model = None


class LocalOCR:
    def __init__(self) -> None:
        self._engine = None
        self._lock = threading.RLock()

    def read(self, image_base64: str) -> str:
        try:
            from rapidocr_onnxruntime import RapidOCR
            import numpy as np
            from PIL import Image
        except ImportError as exc:
            raise ValueError(
                "Yerel ekran yazısı okuma için requirements-local.txt bağımlılıklarını kur senpai (rapidocr-onnxruntime). 📸"
            ) from exc
        try:
            data = base64.b64decode(image_base64, validate=True)
            if not data or len(data) > 4_000_000:
                raise ValueError("Görüntü boyutu geçersiz.")
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 12_000_000:
                    raise ValueError("Görüntü çok büyük.")
                pixels = np.asarray(image.convert("RGB"))
        except Exception as exc:
            raise ValueError("Ekran görüntüsü OCR için okunamadı.") from exc
        with self._lock:
            if self._engine is None:
                self._engine = RapidOCR()
            result, _ = self._engine(pixels)
        lines = []
        for row in result or []:
            try:
                if len(row) >= 3 and float(row[2]) >= 0.5 and str(row[1]).strip():
                    lines.append(str(row[1]).strip())
            except (TypeError, ValueError):
                continue
        text = "\n".join(lines)[:12000]
        return (
            text
            or "Ekranda güvenilir biçimde okunabilir yazı bulamadım senpai. Daha büyük metinle tekrar dene. 📸"
        )

    def close(self) -> None:
        with self._lock:
            self._engine = None

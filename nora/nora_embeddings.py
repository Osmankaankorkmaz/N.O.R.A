"""Optional local multilingual embeddings for Nora's explicit stored data.

The model is never downloaded at startup. Inference is CPU/on-device and vectors
are cached only in memory; notes/memories/tasks are not uploaded to a cloud API.
"""

from __future__ import annotations

import hashlib
import math
import threading
from pathlib import Path
from typing import Any

from .nora_local_ai import LocalModelMissing

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CACHE_REPO = "models--Qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
MODEL_FILE = "model_optimized.onnx"
DIMENSION = 384


class LocalEmbeddings:
    def __init__(self, model_dir: Path, *, model_factory: Any = None) -> None:
        self.model_dir = Path(model_dir)
        self._model_factory = model_factory
        self._model: Any = None
        self._lock = threading.RLock()
        self._cache: dict[str, list[float]] = {}

    def cached(self) -> bool:
        snapshots = self.model_dir / CACHE_REPO / "snapshots"
        return snapshots.is_dir() and any(snapshots.glob(f"*/{MODEL_FILE}"))

    def ensure_model(self, *, download: bool = False) -> str:
        with self._lock:
            if not download and not self.cached():
                raise LocalModelMissing(
                    "Embedding modeli indirilmedi. 'anlamsal arama modelini indir' de veya menüden onayla. Kelime araması kullanılabilir; buluta geçilmez. 🔎"
                )
            if self._model is None:
                factory = self._model_factory
                if factory is None:
                    try:
                        from fastembed import TextEmbedding
                    except ImportError as exc:
                        raise ValueError(
                            "Yerel anlam araması için fastembed kurulu olmalı. requirements-ai.txt dosyasını kur senpai. 🔎"
                        ) from exc
                    factory = TextEmbedding
                try:
                    self._model = factory(
                        model_name=MODEL_NAME,
                        cache_dir=str(self.model_dir),
                        threads=4,
                        providers=["CPUExecutionProvider"],
                        local_files_only=not download,
                    )
                except Exception as exc:
                    raise ValueError(
                        "Yerel embedding modeli yüklenemedi. Model indirmesini ve disk alanını kontrol et. Buluta geçilmedi."
                    ) from exc
            return "Yerel embedding modeli hazır: çok dilli MiniLM. Not/hafıza/görev araması cihazında çalışır. 🔎"

    @staticmethod
    def _vector(raw: Any) -> list[float]:
        vector = [float(value) for value in raw]
        if len(vector) != DIMENSION or not all(
            math.isfinite(value) for value in vector
        ):
            raise ValueError("Embedding çıktısı geçersiz.")
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            raise ValueError("Embedding çıktısı sıfır vektör.")
        return [value / norm for value in vector]

    def embed_query(self, query: str) -> list[float]:
        self.ensure_model()
        with self._lock:
            raw = next(iter(self._model.query_embed([str(query)[:2000]])))
            return self._vector(raw)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.ensure_model()
        results: list[list[float] | None] = [None] * len(texts)
        missing: list[tuple[int, str, str]] = []
        with self._lock:
            for index, text in enumerate(texts):
                text = str(text)[:2000]
                key = hashlib.sha256(text.encode("utf-8")).hexdigest()
                cached = self._cache.get(key)
                if cached is not None:
                    results[index] = cached
                else:
                    missing.append((index, text, key))
            if missing:
                raw_vectors = list(
                    self._model.passage_embed(
                        [text for _index, text, _key in missing], batch_size=32
                    )
                )
                if len(raw_vectors) != len(missing):
                    raise ValueError("Embedding modeli eksik çıktı döndürdü.")
                for (index, _text, key), raw in zip(missing, raw_vectors):
                    vector = self._vector(raw)
                    self._cache[key] = vector
                    results[index] = vector
                while len(self._cache) > 600:
                    self._cache.pop(next(iter(self._cache)))
        return [vector for vector in results if vector is not None]

    def status(self) -> str:
        return (
            f"Embedding modeli: {'indirilmiş' if self.cached() else 'indirilmedi'} · {MODEL_NAME}. "
            "İndirme yaklaşık 220 MB olabilir; arama yereldir. 🔎"
        )

    def close(self) -> None:
        with self._lock:
            self._model = None
            self._cache.clear()

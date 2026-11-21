"""Small, dependency-free local semantic-ish search over explicit Nora data.

This is intentionally local and bounded: it searches only notes, explicitly
saved memories and tasks. It does not index arbitrary files or the clipboard.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from .nora_store import NoraStore

_STOPWORDS = {
    "bir",
    "ve",
    "ile",
    "için",
    "bu",
    "şu",
    "o",
    "da",
    "de",
    "mi",
    "mı",
    "mu",
    "mü",
    "ne",
    "nasıl",
    "olan",
    "gibi",
    "daha",
    "çok",
    "ben",
    "sen",
    "nora",
}


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = value.translate(str.maketrans("Iİ", "ıi")).lower()
    return re.sub(r"[^\w\s]", " ", value)


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in _normalize(text).split()
        if len(token) > 1 and token not in _STOPWORDS
    }


def _score(query: str, text: str) -> float:
    qnorm, tnorm = _normalize(query), _normalize(text)
    if not qnorm or not tnorm:
        return 0.0
    if qnorm in tnorm:
        return 1.0
    qtokens, ttokens = _tokens(query), _tokens(text)
    if not qtokens:
        return 0.0
    overlap = len(qtokens & ttokens) / len(qtokens)
    fuzzy = max(
        (
            SequenceMatcher(None, token, target).ratio()
            for token in qtokens
            for target in ttokens
        ),
        default=0.0,
    )
    return round(0.7 * overlap + 0.3 * fuzzy, 3)


def _items(store: NoraStore, scope: str) -> list[tuple[str, str, str]]:
    items: list[tuple[str, str, str]] = []
    if scope in {"all", "notes"}:
        items.extend(("not", note["id"], note["text"]) for note in store.notes)
    if scope in {"all", "memories"}:
        items.extend(
            ("hafıza", key, f"{key}: {item['value']}")
            for key, item in store.memories.items()
        )
    if scope in {"all", "tasks"}:
        items.extend(("görev", task["id"], task["text"]) for task in store.tasks)
    return items


def _cosine(left: list[float], right: list[float]) -> float:
    return max(0.0, min(1.0, sum(a * b for a, b in zip(left, right))))


def search_store(
    store: NoraStore,
    query: str,
    *,
    scope: str = "all",
    limit: int = 8,
    embedder: Any = None,
) -> list[dict[str, str | float]]:
    query = str(query or "").strip()[:200]
    if not query:
        return []
    if scope not in {"all", "notes", "memories", "tasks"}:
        raise ValueError("Arama kapsamı all/notes/memories/tasks olmalı.")
    items = _items(store, scope)[:500]
    semantic_vectors = None
    query_vector = None
    if embedder is not None and items:
        query_vector = embedder.embed_query(query)
        semantic_vectors = embedder.embed_documents(
            [text for _kind, _id, text in items]
        )
        if len(semantic_vectors) != len(items):
            raise ValueError("Yerel arama vektörleri eksik.")
    results = []
    for index, (kind, identifier, text) in enumerate(items):
        lexical = _score(query, text)
        semantic = (
            _cosine(query_vector, semantic_vectors[index])
            if semantic_vectors is not None
            else 0.0
        )
        if semantic_vectors is None:
            score, method = lexical, "kelime"
        else:
            score = round(max(lexical, 0.35 * lexical + 0.65 * semantic), 3)
            method = (
                "hibrit"
                if lexical >= 0.25 and semantic >= 0.55
                else "anlam"
                if semantic >= 0.55
                else "kelime"
            )
        if lexical >= 0.25 or semantic >= 0.55:
            results.append(
                {
                    "kind": kind,
                    "id": identifier,
                    "text": text[:300],
                    "score": score,
                    "method": method,
                }
            )
    results.sort(key=lambda item: float(item["score"]), reverse=True)
    return results[: max(1, min(int(limit), 20))]


def format_results(query: str, results: list[dict[str, str | float]]) -> str:
    if not results:
        return f"“{query}” için yerel not/hafıza/görevlerde güçlü bir eşleşme bulamadım senpai."
    semantic = any(item.get("method") in {"anlam", "hibrit"} for item in results)
    lines = [
        f"{'Yerel anlamsal/hibrit' if semantic else 'Yerel kelime'} arama: “{query}” 🔎"
    ]
    for index, item in enumerate(results, 1):
        lines.append(
            f"{index}. [{item['kind']}:{item['id']}] {item['text']} (Skor: {item['score']})"
        )
    return "\n".join(lines)

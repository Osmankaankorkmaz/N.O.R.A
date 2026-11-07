"""Small, dependency-free local semantic-ish search over explicit Nora data.

This is intentionally local and bounded: it searches only notes, explicitly
saved memories and tasks. It does not index arbitrary files or the clipboard.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

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


def search_store(
    store: NoraStore, query: str, *, scope: str = "all", limit: int = 8
) -> list[dict[str, str | float]]:
    query = str(query or "").strip()[:200]
    if not query:
        return []
    if scope not in {"all", "notes", "memories", "tasks"}:
        raise ValueError("Arama kapsamı all/notes/memories/tasks olmalı.")
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
    results = []
    for kind, identifier, text in items:
        score = _score(query, text)
        if score >= 0.25:
            results.append(
                {"kind": kind, "id": identifier, "text": text[:300], "score": score}
            )
    results.sort(key=lambda item: float(item["score"]), reverse=True)
    return results[: max(1, min(int(limit), 20))]


def format_results(query: str, results: list[dict[str, str | float]]) -> str:
    if not results:
        return f"“{query}” için yerel not/hafıza/görevlerde güçlü bir eşleşme bulamadım senpai."
    lines = [f"Yerel anlamsal arama: “{query}” 🔎"]
    for index, item in enumerate(results, 1):
        lines.append(
            f"{index}. [{item['kind']}:{item['id']}] {item['text']} (Skor: {item['score']})"
        )
    return "\n".join(lines)

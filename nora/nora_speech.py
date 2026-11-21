"""Conservative Turkish spoken-transcript repair.

This module never listens to audio and never loosens the local wake gate.  It
only repairs text that was already captured after an explicit wake/button press.
Name aliases are accepted in vocative position ("Hey Nova, …") or, without a
greeting, only when the remaining words are an exact bounded direct command.
Free-form sentences such as "Nova hakkında konuşalım" are left untouched.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

# Deliberately small, explicit list. No fuzzy edit-distance matching is used:
# that would rewrite ordinary words and could change note/reminder content.
NAME_ALIASES = (
    "no ra",
    "no  ra",
    "nora",
    "norah",
    "noura",
    "nöra",
    "nova",
    "nola",
    "nara",
    "noro",
)
_GREETINGS = ("hey", "hei", "ey")
_ALIAS_PATTERN = "|".join(
    re.escape(alias) for alias in sorted(NAME_ALIASES, key=len, reverse=True)
)
_GREETED_NAME_RE = re.compile(
    rf"^(?P<greeting>{'|'.join(_GREETINGS)})\s+(?P<name>{_ALIAS_PATTERN})\b[,:.!-]?\s*(?P<body>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_LEADING_NAME_RE = re.compile(
    rf"^(?P<name>{_ALIAS_PATTERN})\s*[,!:;-]\s*(?P<body>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_TRAILING_NAME_RE = re.compile(
    rf"^(?P<body>.+?)\s*,\s*(?P<name>{_ALIAS_PATTERN})$",
    re.IGNORECASE | re.DOTALL,
)
_BARE_NAME_RE = re.compile(
    rf"^(?P<name>{_ALIAS_PATTERN})\s+(?P<body>.+)$",
    re.IGNORECASE | re.DOTALL,
)
# Only low-risk, bounded commands may be used to disambiguate STT alternatives
# or a bare misheard name. Privacy/desktop/file actions are deliberately absent.
SAFE_RERANK_COMMANDS = {"pet_action", "move_monitor", "game", "speech_test", "stt_test"}
SAFE_BARE_NAME_COMMANDS = SAFE_RERANK_COMMANDS | {"mode"}


def _tidy(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    value = "".join(char for char in value if ord(char) >= 32 or char in "\n\t")
    return re.sub(r"\s+", " ", value).strip()


def _turkish_lower(text: str) -> str:
    return text.translate(str.maketrans("Iİ", "ıi")).lower()


@dataclass(frozen=True)
class TranscriptRepair:
    original: str
    text: str
    heard_name: str = ""
    address_corrected: bool = False
    selected_alternative: int = 0
    confidence: float | None = None
    request_id: int | None = None

    @property
    def changed(self) -> bool:
        return self.text != self.original

    def notice(self) -> str:
        if self.address_corrected and self.heard_name:
            return (
                f"🎙️ Adımı “{self.heard_name}” diye duydum; “Nora” olarak anladım. "
                f"Şöyle işledim: “{self.text}”"
            )
        if self.selected_alternative:
            return f"🎙️ Ses tanıma alternatiflerinden şunu seçtim: “{self.text}”"
        return ""


@dataclass(frozen=True)
class SttCandidate:
    text: str
    confidence: float | None = None


def normalize_spoken_address(text: str) -> str:
    """Repair explicit vocative address forms, preserving the spoken payload."""
    value = _tidy(text)
    match = _GREETED_NAME_RE.match(value)
    if match:
        body = match.group("body").strip()
        greeting = match.group("greeting").capitalize()
        return f"{greeting} Nora, {body}".strip() if body else f"{greeting} Nora"
    match = _LEADING_NAME_RE.match(value)
    if match:
        return f"Hey Nora, {match.group('body').strip()}"
    match = _TRAILING_NAME_RE.match(value)
    if match:
        return f"Hey Nora, {match.group('body').strip()}"
    return value


def repair_transcript(
    text: str,
    *,
    command_parser: Callable[[str], Any] | None = None,
    request_id: int | None = None,
    confidence: float | None = None,
) -> TranscriptRepair:
    original = _tidy(text)
    normalized = normalize_spoken_address(original)
    heard_name = ""
    address_corrected = False
    if normalized != original:
        for pattern in (_GREETED_NAME_RE, _LEADING_NAME_RE, _TRAILING_NAME_RE):
            match = pattern.match(original)
            if match:
                heard_name = match.group("name").strip()
                address_corrected = _turkish_lower(heard_name) != "nora"
                break
    else:
        # A bare "Nova uyu" is common after the wake word, but only accept it
        # when the rest is an exact direct command. Never rewrite chat content.
        match = _BARE_NAME_RE.match(original)
        if match and command_parser is not None:
            body = match.group("body").strip()
            try:
                command = command_parser(body)
            except Exception:
                command = None
            command_name = getattr(command, "command", None)
            command_name = (
                command_name.get("command") if isinstance(command_name, dict) else None
            )
            if command is not None and command_name in SAFE_BARE_NAME_COMMANDS:
                normalized = body
                heard_name = match.group("name").strip()
                address_corrected = _turkish_lower(heard_name) != "nora"
    return TranscriptRepair(
        original=original,
        text=normalized,
        heard_name=heard_name,
        address_corrected=address_corrected,
        confidence=confidence,
        request_id=request_id,
    )


def google_candidates(raw: Any) -> list[SttCandidate]:
    """Extract the provider's existing alternatives; never make another request."""
    if isinstance(raw, str):
        return [SttCandidate(raw)] if raw.strip() else []
    if not isinstance(raw, dict):
        return []
    candidates: list[SttCandidate] = []
    for result in raw.get("results", [])[:3]:
        alternatives = (
            result.get("alternatives", []) if isinstance(result, dict) else []
        )
        for alternative in alternatives[:5]:
            if not isinstance(alternative, dict):
                continue
            text = _tidy(alternative.get("transcript", ""))
            if not text:
                continue
            confidence = alternative.get("confidence")
            try:
                confidence = float(confidence) if confidence is not None else None
            except (TypeError, ValueError):
                confidence = None
            if confidence is not None and not 0 <= confidence <= 1:
                confidence = None
            candidates.append(SttCandidate(text[:4000], confidence))
    return candidates


def choose_transcript(
    candidates: list[SttCandidate],
    *,
    command_parser: Callable[[str], Any] | None = None,
    request_id: int | None = None,
) -> TranscriptRepair:
    if not candidates:
        return repair_transcript("", request_id=request_id)
    repaired = [
        repair_transcript(
            candidate.text,
            command_parser=command_parser,
            request_id=request_id,
            confidence=candidate.confidence,
        )
        for candidate in candidates[:5]
    ]
    selected = repaired[0]
    if command_parser is not None:

        def safe_command(item: TranscriptRepair) -> bool:
            try:
                direct = command_parser(item.text)
            except Exception:
                return False
            command = getattr(direct, "command", None)
            return (
                isinstance(command, dict)
                and command.get("command") in SAFE_RERANK_COMMANDS
            )

        def has_command(item: TranscriptRepair) -> bool:
            try:
                return command_parser(item.text) is not None
            except Exception:
                return False

        # Never override a command the provider already ranked first, especially
        # a sensitive one. Only rescue an otherwise unparsed first result with a
        # confident, low-risk alternative.
        if not has_command(selected):
            for index, candidate in enumerate(repaired[1:], start=1):
                if candidate.confidence is not None and candidate.confidence < 0.75:
                    continue
                if (
                    candidate.confidence is not None
                    and selected.confidence is not None
                    and candidate.confidence < selected.confidence
                ):
                    continue
                if safe_command(candidate):
                    selected = TranscriptRepair(
                        original=candidate.original,
                        text=candidate.text,
                        heard_name=candidate.heard_name,
                        address_corrected=candidate.address_corrected,
                        selected_alternative=index,
                        confidence=candidate.confidence,
                        request_id=request_id,
                    )
                    break
    return selected

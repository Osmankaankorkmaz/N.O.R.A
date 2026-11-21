"""Groq API key storage that never touches ``state.json``.

Priority order:

1. ``GROQ_API_KEY`` environment variable (explicit, per-shell override)
2. OS keyring entry ``nora / groq_api_key`` (Windows Credential Manager,
   macOS Keychain, Secret Service)
3. in-memory session value entered in the settings dialog

The key is never written to the JSON preferences file, never logged and never
echoed back in full.  If no keyring backend exists the entered key is kept only
for the current process and the caller is told so.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

SERVICE = "nora"
ACCOUNT = "groq_api_key"

_lock = threading.Lock()
_session_key = ""
_last_error = ""


def _keyring() -> Any | None:
    try:
        import keyring  # noqa: PLC0415 - optional dependency
        from keyring.errors import KeyringError  # noqa: F401

        return keyring
    except Exception:  # pragma: no cover - optional dependency
        return None


def _redact(value: str) -> str:
    value = str(value or "")
    if len(value) <= 8:
        return "…"
    return value[:4] + "…" + value[-4:]


def save_groq_key(value: str) -> str:
    """Store the key in the OS keyring; return a short human status message."""
    global _session_key, _last_error
    value = str(value or "").strip()
    if not value:
        return "Anahtar boş; kaydetmedim."
    if not value.startswith("gsk_") or len(value) < 20:
        return "Anahtar 'gsk_' ile başlamalı ve en az 20 karakter olmalı. Kaydetmedim."
    with _lock:
        _session_key = value
        module = _keyring()
        if module is None:
            _last_error = "keyring paketi yok"
            return (
                "Anahtarı yalnızca bu oturum için bellekte tuttum: "
                "`keyring` paketi kurulu değil, diske yazmadım."
            )
        try:
            module.set_password(SERVICE, ACCOUNT, value)
        except Exception as exc:
            _last_error = type(exc).__name__
            logger.warning("Groq anahtarı kasaya yazılamadı: %s", type(exc).__name__)
            return (
                "Anahtarı bu oturum için bellekte tuttum; sistem anahtar kasasına "
                "yazamadım. Nora kapanınca unutulur."
            )
        _last_error = ""
        return f"Anahtar sistem anahtar kasasına kaydedildi ({_redact(value)})."


def clear_groq_key() -> str:
    global _session_key, _last_error
    with _lock:
        _session_key = ""
        module = _keyring()
        if module is None:
            return "Anahtarı bellekten sildim; `keyring` paketi kurulu değil."
        try:
            module.delete_password(SERVICE, ACCOUNT)
        except Exception:
            return "Anahtarı bellekten sildim; kasada kayıt yoktu veya silinemedi."
        return "Kayıtlı Groq anahtarı sistem kasasından silindi."


def stored_groq_key() -> str:
    """Return the key from the keyring (or the in-memory session), never env."""
    global _session_key
    with _lock:
        if _session_key:
            return _session_key
        module = _keyring()
        if module is None:
            return ""
        try:
            value = module.get_password(SERVICE, ACCOUNT) or ""
        except Exception as exc:
            logger.debug("Anahtar kasası okunamadı: %s", type(exc).__name__)
            return ""
        _session_key = str(value).strip()
        return _session_key


def resolve_groq_key() -> str:
    """Environment first, then keyring; empty string when nothing is set."""
    env = os.getenv("GROQ_API_KEY", "").strip()
    if env:
        return env
    return stored_groq_key()


def groq_key_present() -> bool:
    return bool(resolve_groq_key())


def groq_key_source() -> str:
    if os.getenv("GROQ_API_KEY", "").strip():
        return "ortam değişkeni"
    if stored_groq_key():
        return "sistem anahtar kasası"
    return ""


def mask_groq_key() -> str:
    key = resolve_groq_key()
    return _redact(key) if key else ""


def last_error() -> str:
    return _last_error

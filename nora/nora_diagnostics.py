"""Headless, read-only setup diagnostics. Never opens devices or the network.

Package checks use importlib metadata/spec discovery, not heavy imports. A green
result means files are present, not that a microphone, GUI, OAuth account or
model inference has been exercised. Those require the explicit in-app tests.
"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .nora_embeddings import LocalEmbeddings
from .nora_local_ai import LocalSpeech
from .nora_local_llm import LocalChatModel
from .nora_piper import PiperSpeech
from .nora_store import default_data_dir

FEATURES = ("local", "embeddings", "chat", "piper")
BASE_PACKAGES = {
    "PyQt5": "PyQt5",
    "groq": "groq",
    "pyttsx3": "pyttsx3",
    "SpeechRecognition": "speech_recognition",
    "pocketsphinx": "pocketsphinx",
    "PyAudio": "pyaudio",
    "opencv-python": "cv2",
    "pyautogui": "pyautogui",
    "psutil": "psutil",
    "screen-brightness-control": "screen_brightness_control",
    "pyperclip": "pyperclip",
    "Pillow": "PIL",
    "requests": "requests",
    "keyring": "keyring",
}
FEATURE_PACKAGES = {
    "local": {
        "faster-whisper": "faster_whisper",
        "rapidocr-onnxruntime": "rapidocr_onnxruntime",
        "icalendar": "icalendar",
        "keyboard": "keyboard",
    },
    "embeddings": {"fastembed": "fastembed"},
    "chat": {"llama-cpp-python": "llama_cpp"},
    "piper": {
        "piper-tts": "piper",
        "sounddevice": "sounddevice",
        "numpy": "numpy",
    },
}
INSTALL_FILES = {
    "local": "requirements-local.txt",
    "embeddings": "requirements-embeddings.txt",
    "chat": "requirements-chat.txt",
    "piper": "requirements-piper.txt",
}


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # ok | info | warn | fail
    detail: str


def package_found(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _preferences(data_dir: Path) -> tuple[dict, Check]:
    path = data_dir / "state.json"
    if not path.exists():
        return {}, Check(
            "Veri dosyası", "info", "Henüz oluşturulmadı; ilk açılışta oluşturulur."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(
            data.get("preferences", {}), dict
        ):
            raise ValueError("schema")
    except (OSError, ValueError):
        return {}, Check(
            "Veri dosyası",
            "fail",
            "state.json okunamadı veya biçimi bozuk; içerik gösterilmedi.",
        )
    return data["preferences"], Check(
        "Veri dosyası", "ok", "JSON okunabilir; kişisel içerik raporlanmadı."
    )


def run_diagnostics(
    data_dir: str | Path | None = None, features: Iterable[str] = ()
) -> list[Check]:
    selected = tuple(dict.fromkeys(features))
    invalid = set(selected) - set(FEATURES)
    if invalid:
        raise ValueError(f"Bilinmeyen özellik: {', '.join(sorted(invalid))}")
    checks = []
    version = platform.python_version()
    supported = (3, 10) <= sys.version_info[:2] <= (3, 12)
    checks.append(
        Check(
            "Python",
            "ok" if supported else ("fail" if "local" in selected else "warn"),
            f"{version} · önerilen aralık 3.10–3.12 (özellikle yerel ses/OCR).",
        )
    )
    checks.append(
        Check("Platform", "info", f"{platform.system()} · {platform.machine()}")
    )
    missing = [
        name for name, module in BASE_PACKAGES.items() if not package_found(module)
    ]
    checks.append(
        Check(
            "Temel paketler",
            "fail" if missing else "ok",
            "Eksik: "
            + ", ".join(missing)
            + " · python -m pip install -r requirements.txt"
            if missing
            else f"{len(BASE_PACKAGES)} paket bulunabildi; GUI/ses cihazları import edilmedi.",
        )
    )
    directory = (
        Path(data_dir).expanduser() if data_dir is not None else default_data_dir()
    )
    directory = directory.resolve()
    checks.append(Check("Veri klasörü", "info", str(directory)))
    probe = directory if directory.exists() else directory.parent
    writable = probe.is_dir() and os.access(probe, os.W_OK)
    checks.append(
        Check(
            "Veri yazma izni",
            "ok" if writable else "fail",
            "Klasör yazılabilir görünüyor."
            if writable
            else "Klasör yok veya yazma izni yok.",
        )
    )
    prefs, state_check = _preferences(directory)
    checks.append(state_check)
    checks.append(
        Check(
            "Groq anahtarı",
            "info",
            "GROQ_API_KEY tanımlı (değer okunmadı)."
            if "GROQ_API_KEY" in os.environ
            else "GROQ_API_KEY tanımsız; yerel komutlar çalışabilir, bulut sohbeti için anahtarı ortam değişkeni olarak tanımla.",
        )
    )
    models = directory / "models"
    for feature in selected:
        absent = [
            name
            for name, module in FEATURE_PACKAGES[feature].items()
            if not package_found(module)
        ]
        checks.append(
            Check(
                f"{feature} paketleri",
                "fail" if absent else "ok",
                "Eksik: "
                + ", ".join(absent)
                + f" · python -m pip install -r {INSTALL_FILES[feature]}"
                if absent
                else "Paket dosyaları bulunabildi; model/cihaz çalıştırılmadı.",
            )
        )
    if "local" in selected:
        name = str(prefs.get("whisper_model", "small"))
        try:
            ready = LocalSpeech(models, model_name=name).cached()
        except Exception:
            ready = False
        checks.append(
            Check(
                "Whisper modeli",
                "ok" if ready else "warn",
                "Dosya önbelleği var."
                if ready
                else "Model yok; Nora içinden 'Yerel ses modelini indir' adımını onayla.",
            )
        )
    if "embeddings" in selected:
        ready = LocalEmbeddings(models).cached()
        checks.append(
            Check(
                "Embedding modeli",
                "ok" if ready else "warn",
                "Dosya önbelleği var."
                if ready
                else "Model yok; 'anlamsal arama modelini indir' komutunu kullan.",
            )
        )
    if "chat" in selected:
        chat = LocalChatModel(models)
        try:
            chat.configure(str(prefs.get("local_chat_model", "")))
            ready = chat.cached()
        except ValueError:
            ready = False
        checks.append(
            Check(
                "GGUF modeli",
                "ok" if ready else "warn",
                "Seçili dosya var."
                if ready
                else "Model seçilmedi/yok; Özellikler menüsünden GGUF içe aktar.",
            )
        )
    if "piper" in selected:
        piper = PiperSpeech(models)
        try:
            piper.configure(str(prefs.get("piper_model", "")))
            ready = piper.cached()
        except ValueError:
            ready = False
        checks.append(
            Check(
                "Piper modeli",
                "ok" if ready else "warn",
                "ONNX + JSON dosyaları var."
                if ready
                else "Model seçilmedi/yok; .onnx ve .onnx.json dosyalarını içe aktar.",
            )
        )
    checks.append(
        Check(
            "Kapsam",
            "info",
            "Bu rapor ağ isteği, mikrofon/hoparlör testi, model yüklemesi veya Spotify token okuması yapmaz. İşlev testleri için uygulama içindeki test komutlarını kullan.",
        )
    )
    return checks


def format_report(checks: list[Check], *, as_json: bool = False) -> str:
    if as_json:
        return json.dumps(
            [asdict(check) for check in checks], ensure_ascii=False, indent=2
        )
    symbols = {"ok": "✓", "info": "•", "warn": "!", "fail": "✗"}
    lines = ["Nora kurulum teşhisi · cihaz/ağ açılmadı", ""]
    lines.extend(
        f"{symbols[check.status]} {check.name}: {check.detail}" for check in checks
    )
    failed = sum(check.status == "fail" for check in checks)
    warnings = sum(check.status == "warn" for check in checks)
    lines.extend(["", f"Sonuç: {failed} engel, {warnings} uyarı."])
    return "\n".join(lines)

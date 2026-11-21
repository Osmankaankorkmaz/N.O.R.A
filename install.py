#!/usr/bin/env python3
"""Nora one-file installer — every dependency, one command, no manual steps.

Why this exists
---------------
The old flow needed several ``pip install -r requirements-*.txt`` commands, a
PowerShell wrapper, then a separate ``--doctor`` call.  This script does all of
it from a single file on Windows, macOS and Linux:

```bash
python install.py                 # base + recommended extras + doctor
python install.py --full          # every optional feature (models still opt-in)
python install.py --base          # smallest working install
python install.py --no-venv       # install into the current interpreter
python install.py --doctor-only   # just run the environment check
```

Guarantees
----------
* Never downloads model files. GGUF/Piper/Whisper/embedding models stay opt-in
  through the menus.
* Never requests administrator rights (except Linux system libs, which are
  printed as a copy-paste command rather than run silently).
* Optional features fail independently: a broken C++ build for
  ``llama-cpp-python`` does not abort the rest of the install.
* Prints exactly what succeeded, what was skipped and why.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MIN_PYTHON = (3, 10)
MAX_PYTHON = (3, 13)

BASE = ["-r", "requirements.txt"]
DEV = ["-r", "requirements-dev.txt"]
FEATURES: dict[str, dict[str, object]] = {
    "local": {
        "label": "Yerel STT/OCR/takvim/kısayol",
        "requirements": "requirements-local.txt",
        "packages": [],
    },
    "embeddings": {
        "label": "Yerel anlam araması (fastembed)",
        "requirements": "requirements-embeddings.txt",
        "packages": [],
    },
    "chat": {
        "label": "Yerel GGUF sohbet (llama-cpp-python, derleme gerekebilir)",
        "requirements": "requirements-chat.txt",
        "packages": [],
    },
    "piper": {
        "label": "Piper yerel ses (piper-tts + sounddevice)",
        "requirements": "requirements-piper.txt",
        "packages": [],
    },
}
DEFAULT_EXTRAS = ("piper",)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"


def _supports_colour() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    return sys.stdout.isatty() and platform.system() != "Windows"


def paint(text: str, colour: str) -> str:
    if not _supports_colour():
        return text
    return f"{colour}{text}{RESET}"


def say(message: str = "") -> None:
    print(message, flush=True)


def ok(message: str) -> None:
    say(f"  {paint('✓', GREEN)} {message}")


def warn(message: str) -> None:
    say(f"  {paint('!', YELLOW)} {message}")


def fail(message: str) -> None:
    say(f"  {paint('✗', RED)} {message}")


def header(title: str) -> None:
    say()
    say(paint(f"── {title} " + "─" * max(0, 58 - len(title)), DIM))


def check_python() -> bool:
    version = sys.version_info[:2]
    if version < MIN_PYTHON:
        fail(
            f"Python {version[0]}.{version[1]} çok eski. Nora en az "
            f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]} ister."
        )
        return False
    if version >= MAX_PYTHON:
        warn(
            f"Python {version[0]}.{version[1]} test edilmedi; 3.10-3.12 önerilir "
            "(RapidOCR/kimi paketleri üst sürüm istemez)."
        )
    else:
        ok(f"Python {version[0]}.{version[1]}")
    return True


def in_virtualenv() -> bool:
    return (
        hasattr(sys, "real_prefix")
        or getattr(sys, "base_prefix", sys.prefix) != sys.prefix
    )


def venv_python(root: Path) -> Path | None:
    if platform.system() == "Windows":
        candidate = root / ".venv" / "Scripts" / "python.exe"
    else:
        candidate = root / ".venv" / "bin" / "python"
    return candidate if candidate.exists() else None


def _pick_base_python() -> str | None:
    """Find a 3.10-3.12 interpreter before creating a venv."""
    candidates = []
    for name in ("python3.12", "python3.11", "python3.10"):
        found = shutil.which(name)
        if found:
            candidates.append(found)
    if platform.system() == "Windows":
        py = shutil.which("py")
        if py:
            candidates.append(f"{py} -3.11")
    for candidate in ("python3", "python"):
        found = shutil.which(candidate)
        if found:
            candidates.append(found)
    for candidate in candidates:
        parts = candidate.split()
        try:
            result = subprocess.run(  # noqa: S603 - fixed candidate list
                [*parts, "-c", "import sys;print('%d.%d' % sys.version_info[:2])"],
                capture_output=True,
                text=True,
                timeout=25,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode != 0:
            continue
        try:
            major, minor = (int(part) for part in result.stdout.strip().split("."))
        except ValueError:
            continue
        if MIN_PYTHON <= (major, minor) < MAX_PYTHON:
            return candidate
    return None


def ensure_venv(root: Path, *, create: bool) -> Path:
    """Return the interpreter to install into, creating .venv when asked."""
    if not create:
        ok(f"Mevcut yorumlayıcı kullanılıyor: {sys.executable}")
        return Path(sys.executable)
    existing = venv_python(root)
    if existing is not None:
        ok(f"Mevcut sanal ortam bulundu: {existing}")
        return existing
    base = _pick_base_python()
    if base is None:
        fail(
            "3.10-3.12 arası bir Python bulunamadı. python.org'dan Python 3.11 "
            "kurup bu betiği tekrar çalıştır."
        )
        raise SystemExit(2)
    say(f"  Sanal ortam oluşturuluyor (.venv) · {base}")
    result = subprocess.run(  # noqa: S603 - fixed candidate list
        [*base.split(), "-m", "venv", str(root / ".venv")],
        check=False,
    )
    if result.returncode != 0:
        fail("Sanal ortam oluşturulamadı. Disk iznini/antivirüsü kontrol et.")
        raise SystemExit(2)
    created = venv_python(root)
    if created is None:
        fail("Sanal ortam oluştu ama yorumlayıcı bulunamadı.")
        raise SystemExit(2)
    ok(f"Sanal ortam hazır: {created}")
    return created


def pip_install(python: Path, args: list[str], *, label: str) -> tuple[bool, str]:
    say(f"  {DIM}pip install {' '.join(args)}{RESET}")
    try:
        result = subprocess.run(  # noqa: S603 - args come from this file
            [str(python), "-m", "pip", "install", *args],
            cwd=ROOT,
            check=False,
        )
    except OSError as exc:
        return False, f"{label}: {type(exc).__name__}"
    if result.returncode == 0:
        return True, ""
    return False, label


def pip_upgrade(python: Path) -> bool:
    try:
        result = subprocess.run(  # noqa: S603
            [str(python), "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
            cwd=ROOT,
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def linux_hint() -> None:
    """Print (never run) the system packages Qt/PyAudio need on Linux."""
    if platform.system() != "Linux":
        return
    hint = (
        "sudo apt-get install -y portaudio19-dev espeak-ng libgl1 libegl1 "
        "libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 "
        "libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 "
        "libxcb-xinerama0 libxcb-xfixes0"
    )
    header("Linux sistem paketleri (elle çalıştır)")
    say(f"  {hint}")
    say(f"  {DIM}Bu satır otomatik çalıştırılmadı; sudo istemez.{RESET}")


def run_doctor(python: Path, checks: list[str], *, quiet: bool = False) -> int:
    args = [str(python), "main.py", "--doctor"]
    for name in checks:
        args.extend(["--check", name])
    try:
        result = subprocess.run(args, cwd=ROOT, check=False)  # noqa: S603
    except OSError as exc:
        fail(f"Teşhis çalıştırılamadı: {type(exc).__name__}")
        return 1
    if result.returncode == 0 and not quiet:
        ok("Teşhis: kurulum sağlıklı görünüyor.")
    return result.returncode


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Nora kurulumu: tüm paketler tek komutla.",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Tüm isteğe bağlı özellikleri dene (model dosyaları indirilmez).",
    )
    parser.add_argument(
        "--base",
        action="store_true",
        help="Yalnızca zorunlu paketler (en küçük kurulum).",
    )
    parser.add_argument(
        "--features",
        default="",
        help="Virgülle ayrılmış özellik listesi: local,embeddings,chat,piper",
    )
    parser.add_argument(
        "--no-venv",
        action="store_true",
        help="Sanal ortam oluşturma; mevcut Python'a kur.",
    )
    parser.add_argument(
        "--doctor-only",
        action="store_true",
        help="Hiçbir şey kurma, sadece teşhisi çalıştır.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Geliştirici/test paketlerini de kur (pytest, ruff).",
    )
    return parser.parse_args(argv)


def selected_features(args: argparse.Namespace) -> list[str]:
    if args.base:
        return []
    if args.full:
        return list(FEATURES)
    if args.features:
        wanted = [
            part.strip().lower() for part in args.features.split(",") if part.strip()
        ]
        unknown = [name for name in wanted if name not in FEATURES]
        if unknown:
            fail(f"Bilinmeyen özellik: {', '.join(unknown)}")
            say(f"  Geçerli seçenekler: {', '.join(FEATURES)}")
            raise SystemExit(2)
        return wanted
    return list(DEFAULT_EXTRAS)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    say()
    say(paint("  Nora kurulumu", "\033[1m") + " · tek dosya, tek komut")
    say(f"  {DIM}{platform.system()} · {platform.release()} · {sys.executable}{RESET}")

    header("Python")
    if not check_python():
        return 2

    if args.doctor_only:
        features = selected_features(args)
        header("Teşhis")
        return run_doctor(Path(sys.executable), features or [])

    header("Ortam")
    python = ensure_venv(ROOT, create=not args.no_venv and not in_virtualenv())
    if in_virtualenv() and not args.no_venv:
        ok("Zaten bir sanal ortamdayız.")

    header("pip")
    if pip_upgrade(python):
        ok("pip güncel.")
    else:
        warn("pip güncellenemedi; devam ediliyor.")

    header("Zorunlu paketler")
    ok_base, failed = pip_install(python, BASE, label="zorunlu paketler")
    if ok_base:
        ok("Zorunlu paketler kurulu (requirements.txt).")
    else:
        fail(
            "Zorunlu paketler kurulamadı. İnternet/proxy ve derleme araçlarını kontrol et."
        )
        say(
            f"  {DIM}Tekrar denemek için: {python} -m pip install -r requirements.txt{RESET}"
        )

    if args.dev:
        header("Geliştirici paketleri")
        if pip_install(python, DEV, label="dev paketleri")[0]:
            ok("pytest + ruff kurulu.")
        else:
            warn("Geliştirici paketleri kurulamadı.")

    features = selected_features(args)
    installed: list[str] = []
    skipped: list[str] = []
    for name in features:
        spec = FEATURES[name]
        header(f"Özellik · {name}")
        say(f"  {spec['label']}")
        success, _ = pip_install(python, ["-r", str(spec["requirements"])], label=name)
        if success:
            ok(f"{name} kuruldu.")
            installed.append(name)
        else:
            warn(
                f"{name} atlandı. Bu özellik olmadan Nora çalışır; "
                "derleme aracı veya wheel eksik olabilir."
            )
            skipped.append(name)

    linux_hint()

    header("Teşhis")
    checks = [name for name in installed]
    code = run_doctor(python, checks)

    header("Özet")
    ok("Temel kurulum tamam." if ok_base else "Temel kurulum eksik.")
    if installed:
        ok("Kurulan özellikler: " + ", ".join(installed))
    if skipped:
        warn("Atlanan özellikler: " + ", ".join(skipped))
    say()
    say("  Başlatmak için:")
    if python != Path(sys.executable):
        say(f"    {paint(str(python) + ' main.py', GREEN)}")
    else:
        say(f"    {paint('python main.py', GREEN)}")
    say()
    say(f"  {DIM}Hiçbir model dosyası indirilmedi. GGUF/Piper/Whisper modelleri")
    say(f"  Özellikler menüsünden elle içe aktarılır.{RESET}")
    say(f"  {DIM}Groq anahtarı: uygulamada sağ tık → 🔑 Groq Anahtarı Gir{RESET}")
    say()
    if not ok_base:
        return 1
    return 0 if code in (0, 1) else code


if __name__ == "__main__":
    raise SystemExit(main())

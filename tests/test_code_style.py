"""CI'nin biçim kapısını yerelde de görünür kıl.

`Ruff lint` ve `Ruff format` iki **ayrı** adımdır. Bir dosya `ruff check`'ten
temiz geçip `ruff format --check`'ten geçmeyebilir; o zaman CI kırmızıya döner
ve sonraki adımların hepsi (testler dahil) atlanır. Bu dosya o durumu test
koşumunda yakalar, böylece hata push'tan sonra değil burada görünür.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ("nora", "tests", "tools", "main.py")


def _ruff() -> str:
    """The ruff that belongs to the interpreter running the tests."""
    beside = Path(sys.executable).with_name("ruff")
    if beside.exists():
        return str(beside)
    found = shutil.which("ruff")
    if found is None:
        pytest.skip("ruff kurulu değil; biçim kapısı burada atlanıyor")
    return found


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_ruff(), *args, *TARGETS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_tree_is_ruff_format_clean() -> None:
    """`ruff format --check` CI'da ayrı bir kapı: burada da geçmeli."""
    result = _run("format", "--check")
    assert result.returncode == 0, (
        "Biçim kapısı düşük — `ruff format nora tests tools main.py` çalıştır.\n"
        + (result.stdout or result.stderr)
    )


def test_tree_is_ruff_lint_clean() -> None:
    result = _run("check")
    assert result.returncode == 0, result.stdout or result.stderr

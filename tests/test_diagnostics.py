import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nora.nora_diagnostics import format_report, run_diagnostics


def test_doctor_is_read_only_and_never_prints_secrets(tmp_path, monkeypatch):
    secret = "gsk_SUPER_SECRET_VALUE_123"
    monkeypatch.setenv("GROQ_API_KEY", secret)
    (tmp_path / "state.json").write_text(
        json.dumps(
            {
                "preferences": {"address": "gizli-hitap"},
                "notes": [{"text": "gizli-not"}],
            }
        ),
        encoding="utf-8",
    )
    before = (tmp_path / "state.json").read_bytes()
    checks = run_diagnostics(tmp_path, ("piper", "chat", "embeddings", "local"))
    report = format_report(checks)
    assert secret not in report
    assert "gizli-hitap" not in report and "gizli-not" not in report
    assert (tmp_path / "state.json").read_bytes() == before
    assert not (tmp_path / "models").exists()
    assert any(c.name == "Kapsam" and "ağ isteği" in c.detail for c in checks)


def test_doctor_missing_base_package_is_actionable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "nora.nora_diagnostics.package_found",
        lambda module: module != "pyaudio",
    )
    checks = run_diagnostics(tmp_path)
    failure = next(c for c in checks if c.name == "Temel paketler")
    assert failure.status == "fail"
    assert "PyAudio" in failure.detail and "requirements.txt" in failure.detail


def test_doctor_selected_feature_checks_without_importing_models(tmp_path, monkeypatch):
    imported = []
    monkeypatch.setattr("nora.nora_diagnostics.package_found", lambda module: True)
    import importlib.util

    original = importlib.util.find_spec

    def track(name, *args, **kwargs):
        imported.append(name)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", track)
    checks = run_diagnostics(tmp_path, ("chat", "piper"))
    assert any(c.name == "GGUF modeli" and c.status == "warn" for c in checks)
    assert any(c.name == "Piper modeli" and c.status == "warn" for c in checks)
    assert not any(
        name in imported for name in ("llama_cpp", "piper", "fastembed", "PyQt5")
    )


def test_doctor_rejects_unknown_feature(tmp_path):
    with pytest.raises(ValueError, match="Bilinmeyen özellik"):
        run_diagnostics(tmp_path, ("unknown",))


def test_cli_doctor_works_without_qt_or_network(tmp_path):
    code = """
import socket
import sys
sys.modules['PyQt5'] = None
sys.modules['PyQt5.QtWidgets'] = None
def blocked(*a, **k):
    raise AssertionError('doctor must not use network')
socket.socket.connect = blocked
from nora.main import main
result = main(['--doctor', '--json', '--data-dir', sys.argv[1]])
assert 'PyQt5.QtCore' not in sys.modules
raise SystemExit(result)
"""
    env = dict(os.environ)
    env.pop("GROQ_API_KEY", None)
    env["NORA_DATA_DIR"] = str(tmp_path)
    env["PYTHONIOENCODING"] = "cp1252"
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode in {0, 1}, result.stderr
    report = json.loads(result.stdout)
    assert isinstance(report, list)
    assert any(item["name"] == "Temel paketler" for item in report)
    assert any("ö" in item["name"] or "ü" in item["name"] for item in report)
    assert not list(tmp_path.iterdir())


def test_setup_script_uses_modular_requirements_and_no_model_download():
    root = Path(__file__).resolve().parents[1]
    script = (root / "tools/setup_windows.ps1").read_text(encoding="utf-8")
    assert "Invoke-Expression" not in script
    assert "Set-ExecutionPolicy" not in script
    assert "--doctor" in script
    assert "py -3.11" in script
    assert script.index("Get-Command python") < script.index(
        "Get-Command py -ErrorAction"
    )
    for feature in ("embeddings", "chat", "piper"):
        requirements = (root / f"requirements-{feature}.txt").read_text(
            encoding="utf-8"
        )
        assert "-r requirements.txt" in requirements
        assert feature in script

import base64
import io
import sys
import time
from types import SimpleNamespace

import pytest

from nora.nora_tools import NoraTools


def test_notes_are_in_memory_and_formatted(qapp):
    tools = NoraTools()
    assert "Henüz notun yok" in tools.list_notes()
    tools.add_note("yarın toplantı")
    tools.add_note("kahve al")
    listing = tools.list_notes()
    assert "yarın toplantı" in listing and "kahve al" in listing
    assert len(tools.notes) == 2
    tools.notes.clear()  # returned copy must not mutate internal state
    assert len(tools.notes) == 2
    tools.close()


def test_timer_fires_signal_and_cancel(qapp):
    tools = NoraTools()
    received = []
    tools.timer_finished.connect(received.append)
    result = tools.set_timer(1, "çay hazır")
    assert "çay hazır" in result
    assert len(tools.active_timers) == 1
    deadline = time.time() + 2
    while not received and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    assert received == ["çay hazır"]
    assert not tools.active_timers
    tools.set_timer(60, "iptal")
    timer_id = tools.active_timers[0]
    tools.cancel_timer(timer_id)
    assert not tools.active_timers
    tools.close()


def test_close_cancels_timers(qapp):
    tools = NoraTools()
    tools.set_timer(60, "bekleme")
    tools.close()
    assert not tools.active_timers


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "https://user:pass@example.com",
        "http://",
        "https://exa mple.com",
    ],
)
def test_unsafe_urls_rejected(qapp, url):
    tools = NoraTools()
    assert "güvenli" in tools.open_url(url) or "adres" in tools.open_url(url)
    tools.close()


def test_search_and_music_use_encoded_urls(qapp, monkeypatch):
    tools = NoraTools()
    opened = []
    monkeypatch.setattr(
        "nora.nora_tools.webbrowser.open", lambda url, new=2: opened.append(url) or True
    )
    tools.search("Türkçe kod & kediler")
    tools.play_music("lofi hip hop")
    assert (
        opened[0] == "https://www.google.com/search?q=T%C3%BCrk%C3%A7e+kod+%26+kediler"
    )
    assert "youtube.com/results?search_query=lofi+hip+hop" in opened[1]
    tools.close()


def test_unknown_app_shell_injection_rejected(qapp):
    tools = NoraTools()
    assert "güvenli" in tools.open_app("chrome; rm -rf /")
    assert "güvenli" in tools.open_app("../evil")
    assert "güvenli" in tools.open_app("--flag")
    tools.close()


def test_known_app_uses_popen_without_shell(qapp, monkeypatch):
    tools = NoraTools()
    calls = []
    monkeypatch.setattr(
        "nora.nora_tools.shutil.which",
        lambda name: "/usr/bin/" + name if name in {"gedit", "notepad.exe"} else None,
    )
    monkeypatch.setattr(
        "nora.nora_tools.subprocess.Popen",
        lambda args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(pid=1),
    )
    monkeypatch.setattr("nora.nora_tools.platform.system", lambda: "Linux")
    result = tools.open_app("not defteri")
    assert calls and calls[0][1]["shell"] is False
    assert calls[0][0][0] == "/usr/bin/gedit"
    assert "başlattım" in result
    tools.close()


def test_weather_parses_wttr_json(qapp, monkeypatch):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "current_condition": [
                    {
                        "temp_C": "21",
                        "FeelsLikeC": "20",
                        "humidity": "60",
                        "windspeedKmph": "10",
                        "lang_tr": [{"value": "Parçalı bulutlu"}],
                    }
                ]
            }

    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr("requests.get", fake_get)
    tools = NoraTools()
    text = tools.weather("Bursa")
    assert "21°C" in text and "Parçalı bulutlu" in text and "Bursa" in text
    assert calls[0][1]["timeout"] == 5
    assert "Bursa" in calls[0][0]
    tools.close()


def test_system_health_thresholds(qapp, monkeypatch):
    import psutil

    tools = NoraTools()
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 95)
    assert tools.check_system_health()["kind"] == "cpu"
    monkeypatch.setattr(psutil, "cpu_percent", lambda interval=None: 10)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(percent=92))
    assert tools.check_system_health()["kind"] == "ram"
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(percent=50))
    monkeypatch.setattr(
        psutil,
        "sensors_battery",
        lambda: SimpleNamespace(percent=10, power_plugged=False),
    )
    assert tools.check_system_health()["kind"] == "battery"
    monkeypatch.setattr(
        psutil,
        "sensors_battery",
        lambda: SimpleNamespace(percent=10, power_plugged=True),
    )
    assert tools.check_system_health() is None
    tools.close()


def test_screenshot_resizes_and_encodes(qapp, monkeypatch):
    from PIL import Image

    fake = SimpleNamespace(screenshot=lambda: Image.new("RGB", (1920, 1080), "purple"))
    monkeypatch.setitem(sys.modules, "pyautogui", fake)
    tools = NoraTools()
    payload = tools.screenshot()
    assert payload
    image = Image.open(io.BytesIO(base64.b64decode(payload)))
    assert image.format == "JPEG"
    assert image.width <= 1024 and image.height <= 576
    tools.close()


def test_run_code_requires_opt_in_and_executes_python(qapp):
    tools = NoraTools(allow_code=False)
    assert "kapalı" in tools.run_code("print(1)")
    tools.close()
    tools = NoraTools(allow_code=True)
    result = tools.run_code("print(2 + 2)")
    assert "4" in result and "çıkış kodu 0" in result
    tools.close()


def test_volume_clamps_and_uses_linux_backend(qapp, monkeypatch):
    tools = NoraTools()
    calls = []
    monkeypatch.setattr("nora.nora_tools.sys.platform", "linux")
    monkeypatch.setattr(
        "nora.nora_tools.shutil.which",
        lambda name: "/usr/bin/pactl" if name == "pactl" else None,
    )
    monkeypatch.setattr(
        "nora.nora_tools.subprocess.run",
        lambda args, **kwargs: calls.append(args) or SimpleNamespace(returncode=0),
    )
    assert "%100" in tools.set_volume(150)
    assert calls[-1][-1] == "100%"
    tools.close()

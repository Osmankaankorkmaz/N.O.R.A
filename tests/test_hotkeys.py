import sys
import time
from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt5.QtCore")

from nora.nora_hotkeys import PushToTalkHotkey, normalize_ptt_key


def test_normalize_ptt_key():
    assert normalize_ptt_key(" Ctrl + Alt + Space ") == "ctrl+alt+space"
    assert normalize_ptt_key("f8") == "f8"
    with pytest.raises(ValueError):
        normalize_ptt_key("   ")


def test_push_to_talk_hotkey_emits_press_and_release(qapp, monkeypatch):
    state = {"down": False}
    fake = SimpleNamespace(is_pressed=lambda key: state["down"])
    monkeypatch.setitem(sys.modules, "keyboard", fake)
    hotkey = PushToTalkHotkey()
    pressed, released, errors = [], [], []
    hotkey.pressed.connect(lambda: pressed.append(True))
    hotkey.released.connect(lambda: released.append(True))
    hotkey.error.connect(errors.append)
    assert hotkey.start("ctrl+alt+space")
    state["down"] = True
    deadline = time.time() + 2
    while not pressed and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    state["down"] = False
    deadline = time.time() + 2
    while not released and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    hotkey.stop()
    assert pressed and released and not errors


def test_missing_keyboard_package_is_visible(qapp, monkeypatch):
    monkeypatch.setitem(sys.modules, "keyboard", None)
    hotkey = PushToTalkHotkey()
    errors = []
    hotkey.error.connect(errors.append)
    assert not hotkey.start("f8")
    assert errors and "keyboard" in errors[0]

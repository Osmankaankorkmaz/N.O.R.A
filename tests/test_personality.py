import json
from datetime import datetime

import pytest

from nora.nora_personality import (
    CommandError,
    EMOTIONS,
    PROACTIVE_LINES,
    extract_command,
    extract_emotion,
    get_time_category,
    is_quiet_hours,
    normalize_command,
    parse_response,
    random_line,
    startup_greeting,
)


@pytest.mark.parametrize(
    "hour,expected",
    [
        (0, "night"),
        (5, "night"),
        (6, "morning"),
        (11, "morning"),
        (12, "afternoon"),
        (17, "afternoon"),
        (18, "evening"),
        (22, "evening"),
        (23, "night"),
    ],
)
def test_time_categories(hour, expected):
    assert get_time_category(datetime(2026, 1, 1, hour)) == expected


def test_quiet_hours():
    assert is_quiet_hours(datetime(2026, 1, 1, 2))
    assert not is_quiet_hours(datetime(2026, 1, 1, 6))


def test_proactive_categories_have_variety():
    for category in (
        "morning",
        "afternoon",
        "evening",
        "night",
        "idle",
        "system_alert",
        "random",
    ):
        assert len(PROACTIVE_LINES[category]) >= 4
        assert random_line(category) in PROACTIVE_LINES[category]
    assert startup_greeting(datetime(2026, 1, 1, 9))


def test_emotion_extraction():
    assert extract_emotion("Merhaba [EMO:love]") == ("Merhaba", "love")
    assert extract_emotion("Merhaba [EMO:unknown]") == ("Merhaba", "happy")
    assert extract_emotion("Kod: `[EMO:love]`") == ("Kod: `[EMO:love]`", "happy")


def test_command_extraction_handles_nested_json_and_brackets():
    command = {
        "command": "note",
        "action": "add",
        "text": "köşeli ] ve {brace} içeren not",
    }
    raw = f"Notu aldım [CMD:{json.dumps(command, ensure_ascii=False)}] [EMO:happy]"
    text, emotion, parsed = parse_response(raw)
    assert text == "Notu aldım"
    assert emotion == "happy"
    assert parsed == command
    remaining, parsed2 = extract_command(raw)
    assert parsed2 == command
    assert "[EMO:happy]" in remaining
    assert "[CMD:" not in remaining


def test_command_before_or_after_emotion():
    raw = 'Heh [EMO:smug] [CMD:{"command":"system_info"}]'
    assert parse_response(raw) == ("Heh", "smug", {"command": "system_info"})


def test_malformed_or_non_trailing_command_is_not_executed():
    raw = 'Örnek [CMD:{"command":"shutdown"}] sonra yazı [EMO:happy]'
    text, emotion, command = parse_response(raw)
    assert command is None
    assert "[CMD:" in text
    assert emotion == "happy"
    assert parse_response("Kod bloğu: ```[CMD:{}]```")[2] is None


@pytest.mark.parametrize(
    "command",
    [
        {"command": "open_app", "app": "chrome"},
        {"command": "search", "query": "kediler"},
        {"command": "open_url", "url": "https://example.com"},
        {"command": "volume", "level": 50},
        {"command": "brightness", "level": 0},
        {"command": "type_text", "text": "şğüöç İI"},
        {"command": "clipboard_copy", "text": "x"},
        {"command": "system_info"},
        {"command": "screenshot"},
        {"command": "camera", "prompt": "ne var?"},
        {"command": "shutdown"},
        {"command": "cancel_shutdown"},
        {"command": "lock_screen"},
        {"command": "set_timer", "seconds": 300, "message": "çay"},
        {"command": "play_music", "query": "lofi"},
        {"command": "weather", "city": "Bursa"},
        {"command": "note", "action": "add", "text": "toplantı"},
        {"command": "note", "action": "list"},
        {"command": "run_code", "language": "python", "code": "print(1)"},
    ],
)
def test_normalize_supported_commands(command):
    assert normalize_command(command)["command"] == command["command"]


@pytest.mark.parametrize(
    "command",
    [
        {"command": "volume", "level": 101},
        {"command": "volume", "level": True},
        {"command": "brightness", "level": float("nan")},
        {"command": "set_timer", "seconds": 0},
        {"command": "set_timer", "seconds": 86401},
        {"command": "open_app", "app": "chrome; rm -rf /"},
        {"command": "open_url", "url": "file:///etc/passwd"},
        {"command": "run_code", "language": "bash", "code": "echo hi"},
        {"command": "note", "action": "delete"},
        {"command": "unknown"},
        {"command": "weather", "city": ""},
        None,
    ],
)
def test_invalid_commands_rejected(command):
    with pytest.raises(CommandError):
        normalize_command(command)


def test_emotions_have_metadata():
    assert set(EMOTIONS) == {
        "happy",
        "thinking",
        "surprised",
        "love",
        "angry",
        "sad",
        "sleepy",
        "smug",
    }
    for data in EMOTIONS.values():
        assert {"emoji", "color", "energy"} <= data.keys()

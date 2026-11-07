from datetime import datetime, timedelta, timezone

import pytest

from nora.nora_commands import parse_direct_command, parse_direct_sequence, parse_due
from nora.nora_personality import CommandError, normalize_command

NOW = datetime(2026, 11, 7, 9, 0, tzinfo=timezone(timedelta(hours=3)))


@pytest.mark.parametrize(
    "text,target",
    [
        ("Hey Nora, ikinci monitöre geç!", 2),
        ("2. ekrana git", 2),
        ("monitör 2'ye geç", 2),
        ("üçüncü monitöre taşın", 3),
        ("ana ekrana dön", "primary"),
        ("önceki ekrana geç", "previous"),
        ("monitöre geç", "next"),
        ("ikinci monitöre geçer misin", 2),
    ],
)
def test_monitor_commands_are_deterministic(text, target):
    direct = parse_direct_command(text)
    assert normalize_command(direct.command) == {
        "command": "move_monitor",
        "target": target,
    }


@pytest.mark.parametrize(
    "text,action",
    [
        ("uyu", "sleep"),
        ("uyan", "wake"),
        ("dolaş", "walk"),
        ("dur", "stop"),
        ("zıpla", "jump"),
        ("dans et", "dance"),
        ("otur", "sit"),
        ("zıplar mısın", "jump"),
        ("dolaşır mısın", "walk"),
    ],
)
def test_pet_commands_work_without_model(text, action):
    direct = parse_direct_command(text)
    assert direct.command == {"command": "pet_action", "action": action}


def test_explicit_sequence_and_no_free_text_execution():
    commands = parse_direct_sequence("Hey Nora, ikinci monitöre geç ve uyu")
    assert [item.command["command"] for item in commands] == [
        "move_monitor",
        "pet_action",
    ]
    assert parse_direct_sequence("kahve ve çay severim") == []
    assert parse_direct_command("bugün çok yorgunum") is None
    assert parse_direct_command("masalardaki ikinci monitör hakkında konuşalım") is None


def test_reminder_date_and_time_not_confused():
    due, recurrence = parse_due("08.11.2026 10:00 toplantıyı hatırlat", NOW)
    assert (due.day, due.month, due.hour, due.minute) == (8, 11, 10, 0)
    assert recurrence == "none"
    direct = parse_direct_command("yarın 10:00'da toplantıyı hatırlat", NOW)
    assert direct.command["text"] == "toplantıyı"
    assert direct.command["due_at"].startswith("2026-11-08T10:00")


def test_recurring_reminder_text():
    direct = parse_direct_command("her cuma 18:00'de haftayı özetlememi hatırlat", NOW)
    assert direct.command["recurrence"] == "weekly"
    assert direct.command["text"] == "haftayı özetlememi"
    due, recurrence = parse_due("her gün 09:00 su içmeyi hatırlat", NOW)
    assert recurrence == "daily" and due.hour == 9


def test_feature_command_examples():
    examples = {
        "çalışma modu": "mode",
        "gözlük tak": "settings",
        "bunu hatırla: kahvem = şekersiz": "memory",
        "görev ekle: raporu bitir": "task",
        "görevler": "task",
        "kelime oyunu başlat": "game",
        "panoyu özetle": "clipboard_help",
        "ekrandaki yazıları oku": "screen_text",
        "bugünkü program": "calendar",
        "dosya taşımayı geri al": "undo_files",
    }
    for text, name in examples.items():
        direct = parse_direct_command(text)
        assert direct is not None, text
        assert normalize_command(direct.command)["command"] == name


def test_file_move_and_routine_name():
    direct = parse_direct_command("1 numaralı dosyayı Belgeler'e taşı")
    assert direct.command["selection"] == [1]
    assert direct.command["destination"] == "documents"
    assert parse_direct_command("sabah rutinini çalıştır").command["name"] == "sabah"


@pytest.mark.parametrize(
    "command",
    [
        {"command": "move_monitor", "target": 0},
        {"command": "move_monitor", "target": True},
        {"command": "pet_action", "action": "delete_files"},
        {
            "command": "routine",
            "action": "add",
            "name": "bad",
            "steps": [{"command": "shutdown"}],
        },
        {
            "command": "routine",
            "action": "add",
            "name": "bad",
            "steps": [{"command": "run_code", "code": "print(1)"}],
        },
        {"command": "move_files", "selection": [0], "destination": "documents"},
        {"command": "find_files", "query": "../secret", "directory": "home"},
        {"command": "settings", "action": "set", "key": "allow_code", "value": True},
    ],
)
def test_new_command_schemas_reject_unsafe_values(command):
    with pytest.raises(CommandError):
        normalize_command(command)

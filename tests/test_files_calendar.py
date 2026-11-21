from datetime import datetime, timezone

import pytest

from nora.nora_calendar import format_events, read_ics
from nora.nora_files import NoraFiles
from nora.nora_store import NoraStore


def test_file_preview_move_no_overwrite_and_undo(tmp_path, monkeypatch):
    roots = {
        name: tmp_path / name
        for name in (
            "downloads",
            "documents",
            "desktop",
            "pictures",
            "music",
            "videos",
            "home",
        )
    }
    roots["downloads"].mkdir(parents=True)
    roots["documents"].mkdir(parents=True)
    source = roots["downloads"] / "rapor.pdf"
    source.write_bytes(b"pdf")
    files = NoraFiles()
    monkeypatch.setattr(files, "root", lambda name: roots[name])
    assert "rapor.pdf" in files.find("rapor")
    moves, conflicts = files.preview_move([1], "documents")
    assert moves[0][0] == source and not conflicts
    assert "1 dosya" in files.move([1], "documents")
    assert not source.exists()
    target = roots["documents"] / "Nora Düzenli" / "rapor.pdf"
    assert target.read_bytes() == b"pdf"
    source.write_bytes(b"new")
    assert "üzerine yazmadım" in files.undo()
    assert source.read_bytes() == b"new" and target.exists()


def test_file_selection_requires_prior_search(tmp_path, monkeypatch):
    files = NoraFiles()
    monkeypatch.setattr(files, "root", lambda name: tmp_path)
    with pytest.raises(ValueError):
        files.preview_move([1], "documents")


def test_ics_import_and_recurrence(tmp_path):
    pytest.importorskip("icalendar")
    path = tmp_path / "test.ics"
    path.write_text(
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\nUID:test-1\nDTSTART:20261108T100000Z\nDTEND:20261108T110000Z\nRRULE:FREQ=DAILY;COUNT=3\nSUMMARY:Toplantı\nLOCATION:Ofis\nEND:VEVENT\nEND:VCALENDAR\n",
        encoding="utf-8",
    )
    now = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
    events = read_ics(path, now=now)
    assert len(events) == 3
    assert "Toplantı" in format_events(events)
    store = NoraStore(tmp_path / "state.json")
    assert store.import_events(events) == 3
    assert store.import_events(events) == 0
    assert len(store.upcoming_events(now, days=7)) == 3


def test_calendar_free_slots_merge_busy_intervals():
    from datetime import datetime, timezone
    from nora.nora_calendar import format_free_slots

    now = datetime(2026, 11, 7, 9, 0, tzinfo=timezone.utc)
    events = [
        {
            "start": "2026-11-07T10:00:00+00:00",
            "end": "2026-11-07T11:00:00+00:00",
            "summary": "A",
        },
        {
            "start": "2026-11-07T10:30:00+00:00",
            "end": "2026-11-07T11:30:00+00:00",
            "summary": "B",
        },
    ]
    result = format_free_slots(events, now, duration_minutes=30)
    assert "09:00-10:00" in result and "11:30-18:00" in result


def test_desktop_layout_snapshot_and_restore_are_bounded(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace
    from nora.nora_desktop import DesktopLayouts
    from nora.nora_store import NoraStore

    class Window:
        def __init__(self, title):
            self.title = title
            self.visible = True
            self.isMinimized = False
            self.isMaximized = False
            self.left = 10
            self.top = 20
            self.width = 800
            self.height = 600
            self.calls = []

        def restore(self):
            self.calls.append("restore")

        def moveTo(self, x, y):
            self.calls.append((x, y))

        def resizeTo(self, w, h):
            self.calls.append((w, h))

    window = Window("Editor")
    monkeypatch.setattr("nora.nora_desktop.sys.platform", "win32")
    monkeypatch.setitem(
        sys.modules,
        "pygetwindow",
        SimpleNamespace(getAllWindows=lambda: [window, Window("Nora · Sohbet")]),
    )
    desktop = DesktopLayouts()
    entries = desktop.snapshot()
    assert len(entries) == 1 and entries[0]["title"] == "Editor"
    store = NoraStore(tmp_path / "state.json")
    store.save_layout("çalışma", entries)
    assert store.layout("çalışma") == entries
    assert NoraStore(tmp_path / "state.json").layout("çalışma") == entries
    window.left = 500
    assert "1 pencere" in desktop.restore(store.layout("çalışma"))
    assert (10, 20) in window.calls and (800, 600) in window.calls


def test_desktop_layout_unsupported_platform_is_honest(monkeypatch):
    from nora.nora_desktop import DesktopLayouts

    monkeypatch.setattr("nora.nora_desktop.sys.platform", "linux")
    with pytest.raises(ValueError, match="Windows"):
        DesktopLayouts().snapshot()

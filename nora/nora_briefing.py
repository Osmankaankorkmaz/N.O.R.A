"""Deterministic daily/weekly assistant briefings from local Nora data only."""

from __future__ import annotations

from datetime import datetime, timedelta

from .nora_store import NoraStore, now_local, parse_datetime


def _same_day(value: str, day: datetime) -> bool:
    try:
        return parse_datetime(value).date() == day.date()
    except (ValueError, TypeError):
        return False


def _event_line(event: dict) -> str:
    start = event.get("_start")
    when = start.strftime("%H:%M") if isinstance(start, datetime) else "bugün"
    return f"• {when} {event.get('summary', 'etkinlik')}"


def morning_briefing(store: NoraStore, now: datetime | None = None) -> str:
    now = now or now_local()
    events = store.upcoming_events(now, days=1)
    tasks = [task for task in store.tasks if not task.get("done")]
    reminders = []
    for item in store.reminders:
        try:
            due = parse_datetime(item["due_at"])
        except (ValueError, TypeError, KeyError):
            continue
        if due.date() == now.date():
            reminders.append(f"• {due:%H:%M} {item['text']}")
    lines = [f"Günaydın {store.preference('address', 'senpai')}~ Bugünkü brifingin ☀️"]
    if events:
        lines.append("Takvim:")
        lines.extend(_event_line(event) for event in events[:5])
    else:
        lines.append("Takvim: bugün boş görünüyor.")
    lines.append(
        f"Açık görev: {len(tasks)}" + ("" if tasks else " · liste temiz, aferin.")
    )
    lines.extend(f"• {task['text']}" for task in tasks[:5])
    if reminders:
        lines.append("Bugünkü hatırlatıcılar:")
        lines.extend(reminders[:5])
    if tasks:
        lines.append(f"Öneri: önce '{tasks[0]['text']}' işine küçük bir adım at.")
    else:
        lines.append("Öneri: bugün kendine küçük bir hedef seçebilirsin.")
    return "\n".join(lines)


def daily_summary(store: NoraStore, now: datetime | None = None) -> str:
    now = now or now_local()
    tasks = store.tasks
    done_today = [
        task
        for task in tasks
        if task.get("done") and _same_day(str(task.get("completed_at", "")), now)
    ]
    open_tasks = [task for task in tasks if not task.get("done")]
    notes_today = [
        note for note in store.notes if _same_day(str(note.get("created_at", "")), now)
    ]
    lines = [f"Gün sonu özeti 🌙 ({now:%d.%m.%Y})"]
    lines.append(f"Bugün tamamlanan görev: {len(done_today)}")
    lines.extend(f"✓ {task['text']}" for task in done_today[:8])
    lines.append(f"Yarına kalan açık görev: {len(open_tasks)}")
    lines.extend(f"• {task['text']}" for task in open_tasks[:8])
    lines.append(f"Bugün eklenen not: {len(notes_today)}")
    if open_tasks:
        lines.append("Yarın için ilk aday: " + open_tasks[0]["text"])
    else:
        lines.append("Liste temiz. Bugün kendinle gurur duyabilirsin senpai.")
    return "\n".join(lines)


def weekly_plan(store: NoraStore, now: datetime | None = None) -> str:
    now = now or now_local()
    events = store.upcoming_events(now, days=7)
    tasks = [task for task in store.tasks if not task.get("done")]
    lines = ["Haftalık odak planı 📅"]
    lines.append(f"Önümüzdeki 7 günde etkinlik: {len(events)}")
    lines.extend(_event_line(event) for event in events[:8])
    lines.append(f"Açık görev: {len(tasks)}")
    for index, task in enumerate(tasks[:3], 1):
        lines.append(f"{index}. öncelik: {task['text']}")
    if not tasks:
        lines.append("Görev yoksa haftaya sakin bir bakım/öğrenme hedefi koyabilirsin.")
    lines.append(f"Hafta aralığı: {now:%d.%m} - {(now + timedelta(days=6)):%d.%m}")
    return "\n".join(lines)

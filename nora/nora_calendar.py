"""Read-only .ics calendar import; no account credentials or cloud sync."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from .nora_store import now_local


def read_ics(path: str | Path, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Import today's and the next 31 days' events, including bounded RRULE expansion."""
    try:
        from icalendar import Calendar
        from dateutil.rrule import rrulestr
    except ImportError as exc:
        raise ValueError(
            "Takvim için requirements-local.txt içindeki icalendar paketini kur senpai."
        ) from exc
    source = Path(path).expanduser()
    if not source.is_file() or source.is_symlink() or source.stat().st_size > 2_000_000:
        raise ValueError(
            "Takvim dosyası okunabilir bir .ics dosyası olmalı (en fazla 2 MB)."
        )
    now = now or now_local()
    calendar = Calendar.from_ical(source.read_bytes())
    events = []
    window_start = now - timedelta(days=1)
    window_end = now + timedelta(days=31)
    for component in calendar.walk("VEVENT"):
        if len(events) >= 200:
            break
        start_value = component.decoded("DTSTART", None)
        if start_value is None:
            continue
        all_day = isinstance(start_value, date) and not isinstance(
            start_value, datetime
        )
        start = (
            datetime.combine(start_value, time.min, tzinfo=now.tzinfo)
            if all_day
            else start_value
        )
        if start.tzinfo is None:
            start = start.replace(tzinfo=now.tzinfo)
        start = start.astimezone()
        end_value = component.decoded("DTEND", None)
        if end_value is not None:
            end = (
                datetime.combine(end_value, time.min, tzinfo=now.tzinfo)
                if all_day
                else end_value
            )
            if end.tzinfo is None:
                end = end.replace(tzinfo=now.tzinfo)
            end = end.astimezone()
        else:
            end = start + (timedelta(days=1) if all_day else timedelta(hours=1))
        duration = max(timedelta(minutes=1), end - start)
        uid = str(
            component.get("UID")
            or f"{start.isoformat()}-{component.get('SUMMARY', 'etkinlik')}"
        )
        summary = str(component.get("SUMMARY", "Etkinlik"))[:300]
        location = str(component.get("LOCATION", ""))[:300]
        rule = component.get("RRULE")
        starts = [start]
        if rule:
            try:
                parsed = rrulestr(rule.to_ical().decode("utf-8"), dtstart=start)
                starts = list(parsed.between(window_start, window_end, inc=True)[:100])
            except (ValueError, TypeError):
                starts = [start] if window_start <= start <= window_end else []
        for occurrence in starts:
            if occurrence < window_start or occurrence > window_end:
                continue
            events.append(
                {
                    "uid": uid + ("@" + occurrence.isoformat() if rule else ""),
                    "summary": summary,
                    "location": location,
                    "start": occurrence.isoformat(),
                    "end": (occurrence + duration).isoformat(),
                    "all_day": all_day,
                }
            )
            if len(events) >= 200:
                break
    return events


def format_events(events: list[dict[str, Any]]) -> str:
    if not events:
        return "Bu zaman aralığında etkinliğin yok senpai. Bir .ics dosyasını Takvim İçe Aktar menüsünden yükleyebilirsin. 📅"
    lines = ["Yaklaşan etkinliklerin 📅"]
    for event in events[:30]:
        start = datetime.fromisoformat(event["start"]).astimezone()
        label = (
            f"{start:%d.%m %H:%M}"
            if not event.get("all_day")
            else f"{start:%d.%m} · tüm gün"
        )
        location = f" · {event['location']}" if event.get("location") else ""
        lines.append(f"{label} — {event['summary']}{location}")
    return "\n".join(lines)


def format_free_slots(
    events: list[dict[str, Any]],
    now: datetime | None = None,
    duration_minutes: int = 30,
    work_start: int = 9,
    work_end: int = 18,
) -> str:
    """Find gaps in imported events during local working hours; never invents events."""
    now = now or now_local()
    day_start = datetime.combine(now.date(), time(work_start), tzinfo=now.tzinfo)
    day_end = datetime.combine(now.date(), time(work_end), tzinfo=now.tzinfo)
    cursor = max(day_start, now)
    busy = []
    for event in events:
        try:
            start = datetime.fromisoformat(event["start"]).astimezone()
            end = datetime.fromisoformat(event["end"]).astimezone()
            if event.get("all_day"):
                start, end = day_start, day_end
            if end > cursor and start < day_end:
                busy.append((max(start, cursor), min(end, day_end)))
        except (ValueError, KeyError, TypeError):
            continue
    merged = []
    for start, end in sorted(busy):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    gaps = []
    for start, end in merged:
        if start - cursor >= timedelta(minutes=duration_minutes):
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if day_end - cursor >= timedelta(minutes=duration_minutes):
        gaps.append((cursor, day_end))
    if not gaps:
        return f"Bugün {work_start:02d}:00-{work_end:02d}:00 arasında {duration_minutes} dakikalık boşluk bulamadım senpai. Yalnızca içe aktarılan takvimine baktım. 📅"
    lines = [f"Bugün en az {duration_minutes} dakikalık boşluklar 📅"]
    for start, end in gaps[:5]:
        lines.append(f"{start:%H:%M}-{end:%H:%M}")
    return "\n".join(lines)

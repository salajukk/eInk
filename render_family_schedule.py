"""Chronological family schedule panels for the roomy 13.3inch layout.

Calendar events and school schedules come from separate data sources. This
module merges them at render time and presents both as one clean chronological
list without exposing the source calendar name.
"""

from datetime import date, datetime

from PIL import ImageDraw

from render import (
    GRAY,
    PAD,
    FONT_SMALL,
    _date_str,
    _text,
)
from render_family import (
    _dedupe_future_events,
    _fit_text,
    _next_school_group,
    _school_today_rows,
    _section_label,
)


def _entry_sort_key(entry: dict) -> tuple[str, str, str]:
    """Sort schedule rows by date, start time and title."""
    return (
        str(entry.get("date") or "9999-12-31"),
        str(entry.get("start") or "00:00")[:5],
        str(entry.get("title") or "").casefold(),
    )


def _end_hhmm(value: str | None) -> str | None:
    """Convert calendar end_time ISO value to HH:MM for display."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).strftime("%H:%M")
    except (TypeError, ValueError):
        return None


def _calendar_entry(ev: dict) -> dict:
    return {
        "date": ev.get("date"),
        "start": ev.get("time"),
        "end": _end_hhmm(ev.get("end_time")),
        "title": str(ev.get("title", "")).strip(),
        "all_day": bool(ev.get("all_day")),
    }


def _school_entries(day: str, rows: list[dict]) -> list[dict]:
    entries = []
    for child in rows:
        start = str(child.get("start") or "").strip()
        end = str(child.get("end") or "").strip()
        if not start or not end:
            continue
        entries.append({
            "date": day,
            "start": start,
            "end": end,
            "title": f"{child.get('name', 'Lapsi')} koulu",
            "all_day": False,
        })
    return entries


def _format_time_range(entry: dict) -> str:
    if entry.get("all_day"):
        return ""

    start = str(entry.get("start") or "").strip()
    end = str(entry.get("end") or "").strip()
    if not start:
        return ""
    if end and end != start:
        return f"{start} - {end}"
    return start


def _format_entry(draw: ImageDraw.Draw, entry: dict, max_width: int) -> str:
    """Return one compact schedule line.

    Examples:
      Su 6.9. Neven ja Seran uimahyppy treenit 16:45 - 17:30
      Ma 7.9. Neve koulu 09:00 - 14:00
      Ma 14.9. Neve sirkus 17:00 - 17:45
    """
    day = _date_str(str(entry.get("date") or ""), weekday=True).capitalize()
    title = str(entry.get("title") or "").strip()
    time_range = _format_time_range(entry)
    line = " ".join(part for part in (day, title, time_range) if part)
    return _fit_text(draw, line, FONT_SMALL, max_width)


def _draw_panel(draw: ImageDraw.Draw, label: str, entries: list[dict],
                x: int, y: int, w: int, h: int,
                empty_text: str, stale: bool = False):
    _section_label(draw, x, y, label, stale=stale)
    cy = y + PAD + 20
    bottom = y + h - 6

    if not entries:
        _text(draw, (x + PAD, cy + 2), empty_text, FONT_SMALL, fill=GRAY)
        return

    entries.sort(key=_entry_sort_key)
    row_h = 30
    for entry in entries:
        if cy + row_h > bottom:
            break
        line = _format_entry(draw, entry, w - 2 * PAD)
        _text(draw, (x + PAD, cy), line, FONT_SMALL)
        cy += row_h


def _draw_today_panel(draw: ImageDraw.Draw, calendar: dict | None,
                      school: dict | None, x: int, y: int, w: int, h: int):
    """Show the whole current day, including calendar events already ended."""
    stale = bool((calendar and calendar.get("_stale")) or
                 (school and school.get("_stale")))
    today_iso = date.today().isoformat()

    events = [
        _calendar_entry(ev)
        for ev in (calendar or {}).get("events", [])
        if ev.get("date") == today_iso
    ]
    events.extend(_school_entries(today_iso, _school_today_rows(school)))

    _draw_panel(
        draw, "TÄNÄÄN", events, x, y, w, h,
        empty_text="Ei menoja tänään", stale=stale,
    )


def _draw_upcoming_panel(draw: ImageDraw.Draw, calendar: dict | None,
                         school: dict | None, x: int, y: int, w: int, h: int):
    """Merge future calendar events and the next school day chronologically."""
    stale = bool((calendar and calendar.get("_stale")) or
                 (school and school.get("_stale")))
    today_iso = date.today().isoformat()

    calendar_events = [
        ev for ev in (calendar or {}).get("events", [])
        if ev.get("date", "") > today_iso
    ]
    calendar_events.sort(key=lambda ev: (
        str(ev.get("date") or ""),
        str(ev.get("time") or "00:00"),
        str(ev.get("title") or "").casefold(),
    ))
    calendar_events = _dedupe_future_events(calendar_events)
    entries = [_calendar_entry(ev) for ev in calendar_events]

    next_date, school_rows = _next_school_group(school)
    if next_date and school_rows:
        entries.extend(_school_entries(next_date, school_rows))

    _draw_panel(
        draw, "TULEVAT", entries, x, y, w, h,
        empty_text="Ei tulevia tapahtumia", stale=stale,
    )

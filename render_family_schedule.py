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
    _next_school_group,
    _school_today_rows,
    _section_label,
)


UPCOMING_LIMIT = 6


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


def _entry_text(entry: dict) -> str:
    """Return the complete display text for one schedule occurrence."""
    day = _date_str(str(entry.get("date") or ""), weekday=True).capitalize()
    title = str(entry.get("title") or "").strip()
    time_range = _format_time_range(entry)
    return " ".join(part for part in (day, title, time_range) if part)


def _wrap_text(draw: ImageDraw.Draw, text: str, max_width: int) -> list[str]:
    """Wrap text by words without ellipsising any part of the event."""
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if draw.textlength(candidate, font=FONT_SMALL) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_panel(draw: ImageDraw.Draw, label: str, entries: list[dict],
                x: int, y: int, w: int, h: int,
                empty_text: str, stale: bool = False,
                max_entries: int | None = None):
    _section_label(draw, x, y, label, stale=stale)
    cy = y + PAD + 20
    bottom = y + h - 6

    if not entries:
        _text(draw, (x + PAD, cy + 2), empty_text, FONT_SMALL, fill=GRAY)
        return

    entries = sorted(entries, key=_entry_sort_key)
    if max_entries is not None:
        entries = entries[:max_entries]

    max_width = w - 2 * PAD
    line_h = 21
    row_gap = 5

    for entry in entries:
        lines = _wrap_text(draw, _entry_text(entry), max_width)
        row_h = len(lines) * line_h + row_gap
        if cy + row_h > bottom:
            break
        for line in lines:
            _text(draw, (x + PAD, cy), line, FONT_SMALL)
            cy += line_h
        cy += row_gap


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
    """Show the next six future occurrences, including repeated event titles."""
    stale = bool((calendar and calendar.get("_stale")) or
                 (school and school.get("_stale")))
    today_iso = date.today().isoformat()

    calendar_events = [
        ev for ev in (calendar or {}).get("events", [])
        if ev.get("date", "") > today_iso
    ]
    entries = [_calendar_entry(ev) for ev in calendar_events]

    next_date, school_rows = _next_school_group(school)
    if next_date and school_rows:
        entries.extend(_school_entries(next_date, school_rows))

    _draw_panel(
        draw, "TULEVAT", entries, x, y, w, h,
        empty_text="Ei tulevia tapahtumia", stale=stale,
        max_entries=UPCOMING_LIMIT,
    )

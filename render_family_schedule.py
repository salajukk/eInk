"""Family schedule panels for the roomy 13.3inch layout.

Calendar events and school schedules come from separate data sources. This
module merges them at render time. Today's panel remains chronological, while
the upcoming panel groups future entries under weekday/date headings. Wilma
message reminders can enrich matching calendar events with short remember-items
without creating duplicate schedule rows.
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
    _school_today_rows,
    _section_label,
)


UPCOMING_DAY_LIMIT = 3


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


def _calendar_remember_items(ev: dict, school_reminders: dict | None) -> list[str]:
    """Return remember-items attached to this exact reconciled calendar event."""
    result: list[str] = []
    for enrichment in (school_reminders or {}).get("enrichments") or []:
        if not isinstance(enrichment, dict) or enrichment.get("event") != ev:
            continue
        reminder = enrichment.get("reminder") or {}
        for item in reminder.get("remember") or []:
            text = str(item).strip()
            if text and text not in result:
                result.append(text)
    return result


def _calendar_entry(ev: dict, school_reminders: dict | None = None) -> dict:
    return {
        "date": ev.get("date"),
        "start": ev.get("time"),
        "end": _end_hhmm(ev.get("end_time")),
        "title": str(ev.get("title", "")).strip(),
        "all_day": bool(ev.get("all_day")),
        "remember": _calendar_remember_items(ev, school_reminders),
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
            "remember": [],
        })
    return entries


def _future_school_entries(school: dict | None) -> list[dict]:
    """Return compact school-day entries for all available future summaries.

    New school caches contain `upcoming_school_days`. Fall back to the older
    `next_school_day` shape so an older cache does not make the panel empty.
    """
    entries = []
    for child in (school or {}).get("children", [])[:2]:
        days = child.get("upcoming_school_days")
        if not isinstance(days, list):
            nxt = child.get("next_school_day")
            days = [nxt] if isinstance(nxt, dict) else []

        for day in days:
            if not isinstance(day, dict):
                continue
            day_iso = str(day.get("date") or "").strip()
            start = str(day.get("start") or "").strip()
            end = str(day.get("end") or "").strip()
            if not day_iso or not start or not end:
                continue
            entries.append({
                "date": day_iso,
                "start": start,
                "end": end,
                "title": f"{child.get('name', 'Lapsi')} koulu",
                "all_day": False,
                "remember": [],
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


def _entry_text(entry: dict, include_day: bool = True) -> str:
    """Return complete event text plus optional school remember-items."""
    day = (
        _date_str(str(entry.get("date") or ""), weekday=True).capitalize()
        if include_day
        else ""
    )
    title = str(entry.get("title") or "").strip()
    time_range = _format_time_range(entry)
    base = " ".join(part for part in (day, title, time_range) if part)

    remember = [str(item).strip() for item in entry.get("remember") or [] if str(item).strip()]
    if remember:
        details = " · ".join(remember)
        return f"{base} · {details}" if base else details
    return base


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
                empty_text: str, stale: bool = False):
    _section_label(draw, x, y, label, stale=stale)
    cy = y + PAD + 20
    bottom = y + h - 6

    if not entries:
        _text(draw, (x + PAD, cy + 2), empty_text, FONT_SMALL, fill=GRAY)
        return

    entries = sorted(entries, key=_entry_sort_key)
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


def _draw_grouped_upcoming_panel(draw: ImageDraw.Draw, entries: list[dict],
                                 x: int, y: int, w: int, h: int,
                                 stale: bool = False):
    """Draw the next three dates that have content, grouped under day headings."""
    _section_label(draw, x, y, "TULEVAT", stale=stale)
    cy = y + PAD + 20
    bottom = y + h - 6

    entries = sorted(entries, key=_entry_sort_key)
    if not entries:
        _text(draw, (x + PAD, cy + 2), "Ei tulevia tapahtumia", FONT_SMALL, fill=GRAY)
        return

    groups: dict[str, list[dict]] = {}
    for entry in entries:
        day = str(entry.get("date") or "").strip()
        if not day:
            continue
        groups.setdefault(day, []).append(entry)

    dates = list(groups.keys())[:UPCOMING_DAY_LIMIT]
    event_x = x + PAD + 14
    max_event_width = w - (event_x - x) - PAD
    line_h = 21
    row_gap = 3
    header_gap = 4
    group_gap = 7

    for day in dates:
        header = _date_str(day, weekday=True).upper()
        if cy + line_h > bottom:
            break
        _text(draw, (x + PAD, cy), header, FONT_SMALL)
        cy += line_h + header_gap

        for entry in groups[day]:
            lines = _wrap_text(
                draw,
                _entry_text(entry, include_day=False),
                max_event_width,
            )
            row_h = len(lines) * line_h + row_gap
            if cy + row_h > bottom:
                return
            for line in lines:
                _text(draw, (event_x, cy), line, FONT_SMALL)
                cy += line_h
            cy += row_gap

        cy += group_gap


def _draw_today_panel(draw: ImageDraw.Draw, calendar: dict | None,
                      school: dict | None, x: int, y: int, w: int, h: int,
                      school_reminders: dict | None = None):
    """Show the whole current day, including calendar events already ended."""
    stale = bool((calendar and calendar.get("_stale")) or
                 (school and school.get("_stale")))
    today_iso = date.today().isoformat()

    events = [
        _calendar_entry(ev, school_reminders)
        for ev in (calendar or {}).get("events", [])
        if ev.get("date") == today_iso
    ]
    events.extend(_school_entries(today_iso, _school_today_rows(school)))

    _draw_panel(
        draw, "TÄNÄÄN", events, x, y, w, h,
        empty_text="Ei menoja tänään", stale=stale,
    )


def _draw_upcoming_panel(draw: ImageDraw.Draw, calendar: dict | None,
                         school: dict | None, x: int, y: int, w: int, h: int,
                         school_reminders: dict | None = None):
    """Group the next three future dates that contain calendar/school entries."""
    stale = bool((calendar and calendar.get("_stale")) or
                 (school and school.get("_stale")))
    today_iso = date.today().isoformat()

    calendar_entries = [
        _calendar_entry(ev, school_reminders)
        for ev in (calendar or {}).get("events", [])
        if ev.get("date", "") > today_iso
    ]
    school_entries = [
        entry for entry in _future_school_entries(school)
        if entry.get("date", "") > today_iso
    ]

    _draw_grouped_upcoming_panel(
        draw,
        calendar_entries + school_entries,
        x, y, w, h,
        stale=stale,
    )

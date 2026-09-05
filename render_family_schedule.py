"""Chronological family schedule panels for the roomy 13.3inch layout.

Calendar events and the next school block come from separate data sources. This
module merges them at render time so TÄNÄÄN and TULEVAT are shown in true date /
time order instead of always placing school first.
"""

from datetime import date

from PIL import ImageDraw

from render import (
    GRAY,
    PAD,
    FONT_LABEL,
    FONT_MED,
    FONT_SMALL,
    FONT_TINY,
    FONT_TINY_R,
    _date_str,
    _text,
)
from render_family import (
    _dedupe_future_events,
    _event_meta,
    _fit_text,
    _next_school_group,
    _school_today_rows,
    _section_label,
)


def _event_sort_key(ev: dict) -> tuple[str, str, str]:
    """Sort calendar entries by date, start time and title.

    All-day events intentionally sort before timed entries on the same date.
    """
    event_date = str(ev.get("date") or "9999-12-31")
    event_time = str(ev.get("time") or "00:00")[:5]
    title = str(ev.get("title") or "").casefold()
    return event_date, event_time, title


def _school_sort_key(day: str, rows: list[dict]) -> tuple[str, str, str]:
    starts = [str(row.get("start"))[:5] for row in rows if row.get("start")]
    first_start = min(starts) if starts else "00:00"
    return day, first_start, "koulu"


def _draw_school_block(draw: ImageDraw.Draw, rows: list[dict], x: int, cy: int,
                       bottom: int, date_label: str | None = None) -> int:
    label = "KOULU"
    if date_label:
        label += f" · {_date_str(date_label, weekday=True)}"
    if cy + 18 > bottom:
        return bottom

    _text(draw, (x + PAD, cy), label, FONT_LABEL, fill=GRAY)
    cy += 18
    for child in rows:
        if cy + 22 > bottom:
            return bottom
        _text(draw, (x + PAD, cy), str(child.get("name", "Lapsi")), FONT_SMALL)
        _text(draw, (x + 105, cy),
              f"{child.get('start', '')}–{child.get('end', '')}",
              FONT_SMALL, fill=GRAY)
        cy += 24
    return cy + 3


def _draw_calendar_event(draw: ImageDraw.Draw, ev: dict, x: int, cy: int,
                         w: int, bottom: int, today: bool) -> int:
    if cy + 36 > bottom:
        return bottom
    meta = _event_meta(ev, today=today)
    title = _fit_text(draw, str(ev.get("title", "")), FONT_MED, w - 2 * PAD)
    _text(draw, (x + PAD, cy), meta, FONT_TINY_R, fill=GRAY)
    _text(draw, (x + PAD, cy + 17), title, FONT_MED)
    return cy + 39


def _draw_today_panel(draw: ImageDraw.Draw, calendar: dict | None,
                      school: dict | None, x: int, y: int, w: int, h: int):
    """Draw today's school and calendar entries in chronological order."""
    stale = bool((calendar and calendar.get("_stale")) or
                 (school and school.get("_stale")))
    _section_label(draw, x, y, "TÄNÄÄN", stale=stale)
    cy = y + PAD + 20
    bottom = y + h - 6
    today_iso = date.today().isoformat()

    events = [
        ev for ev in (calendar or {}).get("events", [])
        if ev.get("date") == today_iso
    ]
    events.sort(key=_event_sort_key)
    school_rows = _school_today_rows(school)

    items = []
    if school_rows:
        items.append((_school_sort_key(today_iso, school_rows), "school", school_rows))
    for ev in events:
        items.append((_event_sort_key(ev), "event", ev))
    items.sort(key=lambda item: item[0])

    if not items:
        _text(draw, (x + PAD, cy + 2), "Ei menoja tänään", FONT_SMALL, fill=GRAY)
        return

    for _, kind, payload in items:
        if cy >= bottom:
            break
        if kind == "school":
            cy = _draw_school_block(draw, payload, x, cy, bottom)
        else:
            cy = _draw_calendar_event(draw, payload, x, cy, w, bottom, today=True)

    if school_rows and not events and cy + 18 <= bottom:
        _text(draw, (x + PAD, cy), "Ei muita menoja tänään", FONT_TINY, fill=GRAY)


def _draw_upcoming_panel(draw: ImageDraw.Draw, calendar: dict | None,
                         school: dict | None, x: int, y: int, w: int, h: int):
    """Merge next school day and calendar events into one chronological list."""
    stale = bool((calendar and calendar.get("_stale")) or
                 (school and school.get("_stale")))
    _section_label(draw, x, y, "TULEVAT", stale=stale)
    cy = y + PAD + 20
    bottom = y + h - 6
    today_iso = date.today().isoformat()

    events = [
        ev for ev in (calendar or {}).get("events", [])
        if ev.get("date", "") > today_iso
    ]
    events.sort(key=_event_sort_key)
    events = _dedupe_future_events(events)
    events.sort(key=_event_sort_key)

    next_date, school_rows = _next_school_group(school)

    items = []
    if next_date and school_rows:
        items.append((_school_sort_key(next_date, school_rows), "school", (next_date, school_rows)))
    for ev in events:
        items.append((_event_sort_key(ev), "event", ev))
    items.sort(key=lambda item: item[0])

    if not items:
        _text(draw, (x + PAD, cy + 2), "Ei tulevia tapahtumia", FONT_SMALL, fill=GRAY)
        return

    for _, kind, payload in items:
        if cy >= bottom:
            break
        if kind == "school":
            school_date, rows = payload
            cy = _draw_school_block(draw, rows, x, cy, bottom, date_label=school_date)
        else:
            cy = _draw_calendar_event(draw, payload, x, cy, w, bottom, today=False)

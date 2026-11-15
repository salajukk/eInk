"""School schedule from one or more Wilma iCalendar feeds.

The module reduces a full lesson timetable to the information most useful on a
family dashboard: today's first/last lesson plus compact summaries for upcoming
school days within the coming week.

Expected config:

school_schedules:
  - name: "Lapsi 1"
    ical_url: "https://...secret Wilma iCal URL..."
  - name: "Lapsi 2"
    ical_url: "https://...secret Wilma iCal URL..."
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

CACHE_FILE = Path("cache/school.json")


class DataFetchError(Exception):
    pass


def _load_cache() -> dict | None:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(data: dict):
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_is_fresh(ttl_minutes: int) -> bool:
    if not CACHE_FILE.exists():
        return False
    cached = _load_cache()
    if not cached or cached.get("date") != date.today().isoformat():
        return False
    age = datetime.now().timestamp() - CACHE_FILE.stat().st_mtime
    return age < ttl_minutes * 60


def _local_datetime(value) -> datetime | None:
    """Convert an iCalendar DTSTART/DTEND value to local datetime.

    All-day entries are dates rather than datetimes and are ignored by the
    school-day calculation.
    """
    if not isinstance(value, datetime):
        return None
    return value.astimezone()


def _parse_range(content: bytes, start_date: date, days: int = 8) -> list[dict]:
    try:
        from icalendar import Calendar
        import recurring_ical_events
    except ImportError as e:
        raise DataFetchError(
            "icalendar / recurring-ical-events is not installed. "
            "Install the project requirements first."
        ) from e

    try:
        cal = Calendar.from_ical(content)
    except Exception as e:
        raise DataFetchError(f"Wilma iCal parsing failed: {e}") from e

    end_date = start_date + timedelta(days=days)
    try:
        occurrences = recurring_ical_events.of(cal).between(start_date, end_date)
    except Exception as e:
        raise DataFetchError(f"Wilma recurring event expansion failed: {e}") from e

    lessons = []
    for component in occurrences:
        dtstart_prop = component.get("DTSTART")
        if not dtstart_prop:
            continue

        start = _local_datetime(dtstart_prop.dt)
        if start is None or not (start_date <= start.date() < end_date):
            continue

        end = None
        dtend_prop = component.get("DTEND")
        if dtend_prop:
            end = _local_datetime(dtend_prop.dt)

        title = str(component.get("SUMMARY", "Oppitunti"))
        lessons.append({
            "title": title,
            "date": start.date().isoformat(),
            "start": start.strftime("%H:%M"),
            "end": end.strftime("%H:%M") if end else None,
            "_start_dt": start,
            "_end_dt": end,
        })

    lessons.sort(key=lambda item: item["_start_dt"])
    return lessons


def _summarize_day(lessons: list[dict], target_date: date) -> dict:
    day_lessons = [lesson for lesson in lessons if lesson["date"] == target_date.isoformat()]
    start = day_lessons[0]["start"] if day_lessons else None
    lesson_ends = [lesson["_end_dt"] for lesson in day_lessons if lesson["_end_dt"]]
    end = max(lesson_ends).strftime("%H:%M") if lesson_ends else None
    clean_lessons = [
        {
            "title": lesson["title"],
            "start": lesson["start"],
            "end": lesson["end"],
        }
        for lesson in day_lessons
    ]
    return {
        "date": target_date.isoformat(),
        "start": start,
        "end": end,
        "lesson_count": len(day_lessons),
        "lessons": clean_lessons,
    }


def fetch(config: dict, use_cache: bool = True) -> dict:
    cache_cfg = config.get("cache", {})
    ttl = int(cache_cfg.get("school_ttl_minutes", cache_cfg.get("ttl_minutes", 55)))

    if use_cache and _cache_is_fresh(ttl):
        return _load_cache()

    schedules = config.get("school_schedules", [])
    if not schedules:
        raise DataFetchError(
            "No school schedules configured. Add a 'school_schedules:' list "
            "with each child's Wilma iCal link to config.yaml."
        )

    today = date.today()
    children = []
    try:
        for schedule in schedules:
            name = str(schedule.get("name", "Lapsi"))
            url = str(schedule.get("ical_url", "")).strip()
            if not url:
                continue

            response = requests.get(url, timeout=15)
            response.raise_for_status()
            lessons = _parse_range(response.content, today, days=8)

            today_summary = _summarize_day(lessons, today)

            upcoming_school_days = []
            for offset in range(1, 8):
                candidate = _summarize_day(lessons, today + timedelta(days=offset))
                if candidate["lesson_count"] > 0:
                    upcoming_school_days.append(candidate)

            # Keep the old single-value field for the 7.5inch renderer and
            # existing caches/configurations. The 13.3inch renderer can use the
            # full list to group several future days correctly.
            next_school_day = upcoming_school_days[0] if upcoming_school_days else None

            children.append({
                "name": name,
                "start": today_summary["start"],
                "end": today_summary["end"],
                "lesson_count": today_summary["lesson_count"],
                "lessons": today_summary["lessons"],
                "next_school_day": next_school_day,
                "upcoming_school_days": upcoming_school_days,
            })

    except (requests.RequestException, DataFetchError) as e:
        cached = _load_cache()
        if cached and cached.get("date") == today.isoformat():
            cached["_stale"] = True
            return cached
        if isinstance(e, DataFetchError):
            raise
        raise DataFetchError(f"Wilma school schedule fetch failed: {e}") from e

    if not children:
        raise DataFetchError("School schedules are configured but no usable iCal URLs were found.")

    data = {
        "date": today.isoformat(),
        "children": children,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_cache(data)
    return data

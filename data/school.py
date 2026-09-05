"""School schedule from one or more Wilma iCalendar feeds.

The module intentionally reduces a full lesson timetable to the information
most useful on a family dashboard: first lesson start, last lesson end and the
number of lessons for each child today.

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


def _parse_today(content: bytes) -> list[dict]:
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

    today = date.today()
    tomorrow = today + timedelta(days=1)

    try:
        occurrences = recurring_ical_events.of(cal).between(today, tomorrow)
    except Exception as e:
        raise DataFetchError(f"Wilma recurring event expansion failed: {e}") from e

    lessons = []
    for component in occurrences:
        dtstart_prop = component.get("DTSTART")
        if not dtstart_prop:
            continue

        start = _local_datetime(dtstart_prop.dt)
        if start is None or start.date() != today:
            continue

        end = None
        dtend_prop = component.get("DTEND")
        if dtend_prop:
            end = _local_datetime(dtend_prop.dt)

        # Wilma lesson events normally contain DTEND. If an entry lacks it,
        # keep the lesson but don't let it distort the school-day end time.
        title = str(component.get("SUMMARY", "Oppitunti"))
        lessons.append({
            "title": title,
            "start": start.strftime("%H:%M"),
            "end": end.strftime("%H:%M") if end else None,
            "_start_dt": start,
            "_end_dt": end,
        })

    lessons.sort(key=lambda item: item["_start_dt"])
    return lessons


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

    children = []
    try:
        for schedule in schedules:
            name = str(schedule.get("name", "Lapsi"))
            url = str(schedule.get("ical_url", "")).strip()
            if not url:
                continue

            response = requests.get(url, timeout=15)
            response.raise_for_status()
            lessons = _parse_today(response.content)

            start = lessons[0]["start"] if lessons else None
            lesson_ends = [lesson["_end_dt"] for lesson in lessons if lesson["_end_dt"]]
            end = max(lesson_ends).strftime("%H:%M") if lesson_ends else None

            clean_lessons = [
                {"title": lesson["title"], "start": lesson["start"], "end": lesson["end"]}
                for lesson in lessons
            ]
            children.append({
                "name": name,
                "start": start,
                "end": end,
                "lesson_count": len(lessons),
                "lessons": clean_lessons,
            })

    except (requests.RequestException, DataFetchError) as e:
        cached = _load_cache()
        if cached and cached.get("date") == date.today().isoformat():
            cached["_stale"] = True
            return cached
        if isinstance(e, DataFetchError):
            raise
        raise DataFetchError(f"Wilma school schedule fetch failed: {e}") from e

    if not children:
        raise DataFetchError("School schedules are configured but no usable iCal URLs were found.")

    data = {
        "date": date.today().isoformat(),
        "children": children,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_cache(data)
    return data

"""Full-month calendar data for the interactive tablet view.

The normal dashboard keeps using data/calendar.py and its small upcoming-event
cache. This module is intentionally separate so the tablet can request every
occurrence in a selected month without changing the e-paper data path.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from data.calendar import DataFetchError, _parse_ical

CACHE_DIR = Path("cache/calendar_months")


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    if month < 1 or month > 12:
        raise ValueError("month must be between 1 and 12")
    start = date(year, month, 1)
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    return start, next_month - timedelta(days=1)


def _cache_path(year: int, month: int) -> Path:
    return CACHE_DIR / f"{year:04d}-{month:02d}.json"


def _load_cache(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _save_cache(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _cache_is_fresh(path: Path, ttl_minutes: int) -> bool:
    if not path.exists():
        return False
    age = datetime.now().timestamp() - path.stat().st_mtime
    return age < ttl_minutes * 60


def fetch_month(
    config: dict,
    year: int,
    month: int,
    use_cache: bool = True,
) -> dict:
    """Return all configured iCal events for one complete calendar month."""
    start, end = _month_bounds(int(year), int(month))
    cache_cfg = config.get("cache") or {}
    try:
        ttl = int(cache_cfg.get("ttl_minutes", 55))
    except (TypeError, ValueError):
        ttl = 55
    ttl = max(1, ttl)

    path = _cache_path(start.year, start.month)
    if use_cache and _cache_is_fresh(path, ttl):
        cached = _load_cache(path)
        if cached:
            return cached

    calendars = config.get("calendars") or []
    configured = [
        cal for cal in calendars
        if isinstance(cal, dict) and str(cal.get("ical_url") or "").strip()
    ]
    if not configured:
        raise DataFetchError(
            "No calendars in configuration. Add a 'calendars:' list with iCal links."
        )

    calendar_names = [str(cal.get("name") or "Kalenteri") for cal in configured]
    events: list[dict] = []

    for cal_cfg in configured:
        name = str(cal_cfg.get("name") or "Kalenteri")
        url = str(cal_cfg.get("ical_url") or "").strip()
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            events.extend(_parse_ical(response.content, name, start, end))
        except DataFetchError:
            raise
        except requests.RequestException as exc:
            # Keep the previous complete month visible if one feed is temporarily
            # unavailable. This mirrors the resilience of the normal dashboard.
            cached = _load_cache(path)
            if cached:
                cached["_stale"] = True
                return cached
            raise DataFetchError(f"iCal fetch failed ({name}): {exc}") from exc

    events.sort(key=lambda event: event.get("_sort") or "")
    for event in events:
        event.pop("_sort", None)

    data = {
        "year": start.year,
        "month": start.month,
        "calendar_names": calendar_names,
        "events": events,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_cache(path, data)
    return data

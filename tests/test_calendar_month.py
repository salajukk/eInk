import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from data import calendar_month


class CalendarMonthTests(unittest.TestCase):
    def test_month_bounds_cover_complete_month(self):
        start, end = calendar_month._month_bounds(2026, 9)
        self.assertEqual(start.isoformat(), "2026-09-01")
        self.assertEqual(end.isoformat(), "2026-09-30")

        start, end = calendar_month._month_bounds(2026, 12)
        self.assertEqual(start.isoformat(), "2026-12-01")
        self.assertEqual(end.isoformat(), "2026-12-31")

    def test_fetch_month_keeps_all_calendars_and_events(self):
        config = {
            "calendars": [
                {"name": "Perhe", "ical_url": "https://example.test/family.ics"},
                {"name": "Neve", "ical_url": "https://example.test/neve.ics"},
            ],
            "cache": {"ttl_minutes": 5},
        }

        response = Mock()
        response.content = b"BEGIN:VCALENDAR\nEND:VCALENDAR"
        response.raise_for_status.return_value = None

        def fake_parse(_content, name, _start, _end):
            return [
                {
                    "title": f"{name} tapahtuma",
                    "date": "2026-09-10",
                    "time": "18:00",
                    "all_day": False,
                    "end_time": "2026-09-10T19:00",
                    "calendar": name,
                    "_sort": f"2026-09-10{name}",
                }
            ]

        with tempfile.TemporaryDirectory() as tmp, patch.object(
            calendar_month, "CACHE_DIR", Path(tmp)
        ), patch.object(
            calendar_month.requests, "get", return_value=response
        ), patch.object(
            calendar_month, "_parse_ical", side_effect=fake_parse
        ):
            data = calendar_month.fetch_month(config, 2026, 9, use_cache=False)

        self.assertEqual(data["calendar_names"], ["Perhe", "Neve"])
        self.assertEqual(len(data["events"]), 2)
        self.assertEqual(
            {event["calendar"] for event in data["events"]},
            {"Perhe", "Neve"},
        )
        self.assertTrue(all("_sort" not in event for event in data["events"]))


if __name__ == "__main__":
    unittest.main()

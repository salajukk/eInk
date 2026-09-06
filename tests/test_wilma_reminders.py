import unittest
from datetime import date
from pathlib import Path

from analysis.wilma_reminders import analyze_message
from data.school_reminders import reconcile_with_calendar, remove_expired
from integrations.wilma_messages import load_fixture_messages

FIXTURE = Path(__file__).parent / "fixtures" / "wilma_messages.json"


class WilmaReminderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.messages = {item["id"]: item for item in load_fixture_messages(FIXTURE)}

    def test_trip_message_becomes_one_event_with_remember_items(self):
        reminders = analyze_message(self.messages["retki-1"], date(2026, 9, 13))
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["title"], "Retki")
        self.assertEqual(reminders[0]["date"], "2026-09-16")
        self.assertEqual(reminders[0]["remember"], ["Eväät mukaan", "Säänmukainen vaatetus"])
        self.assertGreaterEqual(reminders[0]["confidence"], 0.9)

    def test_two_dated_actions_create_two_reminders(self):
        reminders = analyze_message(self.messages["math-1"], date(2026, 9, 14))
        self.assertEqual(
            [(item["date"], item["title"]) for item in reminders],
            [
                ("2026-09-17", "Geometriset välineet mukaan"),
                ("2026-09-18", "Matematiikan koe"),
            ],
        )

    def test_informational_message_is_ignored(self):
        reminders = analyze_message(self.messages["info-1"], date(2026, 9, 14))
        self.assertEqual(reminders, [])

    def test_expired_items_are_removed_but_today_stays(self):
        reminders = [
            {"title": "Old", "date": "2026-09-13", "end_date": None},
            {"title": "Today", "date": "2026-09-14", "end_date": None},
        ]
        active = remove_expired(reminders, date(2026, 9, 14))
        self.assertEqual([item["title"] for item in active], ["Today"])

    def test_same_day_calendar_event_becomes_enrichment(self):
        reminder = {
            "title": "Retki",
            "date": "2026-09-16",
            "remember": ["Eväät mukaan"],
        }
        calendar = {
            "events": [
                {"title": "Luokan retki", "date": "2026-09-16", "time": "08:15"}
            ]
        }
        result = reconcile_with_calendar([reminder], calendar)
        self.assertEqual(result["standalone"], [])
        self.assertEqual(len(result["enrichments"]), 1)
        self.assertEqual(result["enrichments"][0]["reminder"]["remember"], ["Eväät mukaan"])

    def test_same_title_on_different_day_is_not_duplicate(self):
        reminder = {"title": "Retki", "date": "2026-09-16", "remember": []}
        calendar = {"events": [{"title": "Retki", "date": "2026-09-17"}]}
        result = reconcile_with_calendar([reminder], calendar)
        self.assertEqual(result["standalone"], [reminder])
        self.assertEqual(result["enrichments"], [])


if __name__ == "__main__":
    unittest.main()

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from analysis.wilma_reminders import analyze_message
from data import school_reminders
from data.school_reminders import reconcile_with_calendar, remove_expired
from integrations.wilma_messages import (
    WilmaMessageSourceError,
    _extract_children,
    _extract_message_body,
    _extract_session_id,
    fetch_live_messages,
    load_fixture_messages,
)

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

    def test_message_subject_can_supply_exam_subject_context(self):
        message = {
            "id": "exam-subject",
            "subject": "Matematiikka",
            "body": "Tiistaina pidämme pienen kokeen.",
        }
        reminders = analyze_message(message, date(2026, 9, 14))
        self.assertEqual(len(reminders), 1)
        self.assertEqual(reminders[0]["date"], "2026-09-15")
        self.assertEqual(reminders[0]["title"], "Matematiikan koe")
        self.assertGreaterEqual(reminders[0]["confidence"], 0.9)

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

    def test_html_helpers_parse_login_children_and_message_body(self):
        self.assertEqual(
            _extract_session_id('<form><input name="SESSIONID" value="abc123"></form>'),
            "abc123",
        )
        children = _extract_children(
            '<a href="/!101/"><span>Neve</span></a><a href="/!202/">Sera</a>'
        )
        self.assertEqual(
            children,
            [{"id": "101", "name": "Neve"}, {"id": "202", "name": "Sera"}],
        )
        body = _extract_message_body(
            '<div class="ckeditor"><p>Retki keskiviikkona.</p><p>Eväät mukaan.</p></div>'
        )
        self.assertIn("Retki keskiviikkona.", body)
        self.assertIn("Eväät mukaan.", body)

    def test_live_provider_requires_credentials_without_echoing_them(self):
        with self.assertRaises(WilmaMessageSourceError) as ctx:
            fetch_live_messages({"base_url": "https://school.inschool.fi"})
        self.assertIn("username", str(ctx.exception))
        self.assertIn("password", str(ctx.exception))

    def test_state_does_not_persist_raw_message_body(self):
        message = {
            "id": "child:message-1",
            "sent_at": "2026-09-13T12:00:00",
            "sender": "Teacher",
            "subject": "Retki",
            "body": "Ensi viikon keskiviikkona lähdemme retkelle. SALAINEN VIESTITESTI.",
            "student_id": "child",
        }
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with patch.object(school_reminders, "STATE_FILE", state_path), patch.object(
                school_reminders, "fetch_messages", return_value=[message]
            ):
                data = school_reminders.build({}, reference_date=date(2026, 9, 13))

            persisted = state_path.read_text(encoding="utf-8")
            self.assertNotIn("SALAINEN VIESTITESTI", persisted)
            self.assertEqual(data["items"][0]["title"], "Retki")

    def test_future_reminder_survives_when_message_falls_out_of_fetch_window(self):
        stored = {
            "messages": {
                "child:old": {
                    "hash": "abc",
                    "last_seen": "2026-09-01T10:00:00",
                    "reminders": [
                        {
                            "title": "Retki",
                            "date": "2026-09-20",
                            "end_date": None,
                            "remember": [],
                            "source": "wilma_message",
                        }
                    ],
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps(stored), encoding="utf-8")
            with patch.object(school_reminders, "STATE_FILE", state_path), patch.object(
                school_reminders, "fetch_messages", return_value=[]
            ):
                data = school_reminders.build({}, reference_date=date(2026, 9, 14))

        self.assertEqual(
            [(item["date"], item["title"]) for item in data["items"]],
            [("2026-09-20", "Retki")],
        )


if __name__ == "__main__":
    unittest.main()

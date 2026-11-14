import json
import unittest
from datetime import date
from unittest.mock import Mock, patch

from analysis.wilma_ai import analyze
from data.school_reminders import _message_hash, remove_expired
from integrations.wilma_messages import WilmaMessageSourceError


class WilmaAITests(unittest.TestCase):
    def setUp(self):
        self.message = {"id": "1:2", "student": "Neve", "student_id": "1",
                        "body": "Huomenna retki. Eväät mukaan."}
        self.cfg = {"api_key": "test-secret", "model": "test-model"}
        self.item = {"title": "Retki", "date": "2026-11-09", "end_date": None,
                     "remember": ["Eväät mukaan"], "evidence": "Huomenna retki.",
                     "needs_review": False}

    def response(self, items):
        return Mock(json=lambda: {"status": "completed", "output": [{"type": "message",
            "content": [{"type": "output_text", "text": json.dumps({"items": items})}]}]})

    @patch("analysis.wilma_ai.requests.post")
    def test_identity_is_local_and_secrets_are_not_sent_in_input(self, post):
        post.return_value = self.response([self.item])
        result = analyze(self.message, date(2026, 11, 8), self.cfg)
        self.assertEqual(result[0]["student"], "Neve")
        self.assertEqual(result[0]["source_message_id"], "1:2")
        payload = post.call_args.kwargs["json"]
        self.assertFalse(payload["store"])
        self.assertNotIn("Neve", payload["input"])
        self.assertNotIn("test-secret", payload["input"])

    @patch("analysis.wilma_ai.requests.post")
    def test_invented_evidence_rejected(self, post):
        post.return_value = self.response([{**self.item, "evidence": "Keksitty"}])
        with self.assertRaises(WilmaMessageSourceError):
            analyze(self.message, date(2026, 11, 8), self.cfg)

    @patch("analysis.wilma_ai.requests.post")
    def test_undated_action_stays_visible_for_review(self, post):
        post.return_value = self.response([{**self.item, "date": None}])
        result = analyze(self.message, date(2026, 10, 1), self.cfg)
        active = remove_expired(result, date(2026, 11, 8))
        self.assertEqual(active[0]["date"], "2026-11-08")
        self.assertTrue(active[0]["title"].startswith("Tarkista:"))

    @patch("analysis.wilma_ai.requests.post")
    def test_incomplete_response_is_failure_not_empty_success(self, post):
        post.return_value = Mock(json=lambda: {"status": "incomplete"})
        with self.assertRaises(WilmaMessageSourceError):
            analyze(self.message, date(2026, 11, 8), self.cfg)

    def test_model_change_invalidates_analysis_cache(self):
        self.assertNotEqual(_message_hash(self.message, "ai:model1"),
                            _message_hash(self.message, "ai:model2"))

    @patch("analysis.wilma_ai.requests.post")
    def test_missing_key_does_not_call_api(self, post):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(WilmaMessageSourceError):
                analyze(self.message, date(2026, 11, 8), {"model": "test"})
        post.assert_not_called()

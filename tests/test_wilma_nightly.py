import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import wilma_nightly as job
from data.school_reminders import fetch

class NightlyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'cache').mkdir()
        (self.root / 'config.yaml').write_text('{}')
        self.messages = [{'id': '1:2', 'subject': 'Retki', 'body': 'Huomenna retki.',
                          'student': 'Neve', 'student_id': '1'}]

    def run_job(self, summary):
        with patch.object(job, 'ROOT', self.root), patch.object(job, 'CACHE', self.root / 'cache'), patch.object(job, 'fetch_messages', return_value=self.messages), patch.object(job, 'summarize', side_effect=summary) as ai:
            job.run()
            return ai

    def test_failed_ai_preserves_previous_summary(self):
        target = self.root / 'cache/wilma_codex_summary.json'
        target.write_text('{"items": ["old"]}')
        with self.assertRaises(RuntimeError):
            self.run_job(RuntimeError('failed'))
        self.assertEqual(target.read_text(), '{"items": ["old"]}')
        self.assertFalse((self.root / 'cache/wilma_codex_state.json').exists())

    def test_unchanged_messages_do_not_call_codex(self):
        self.run_job([[]])
        ai = self.run_job(RuntimeError('must not call'))
        ai.assert_not_called()

    def test_student_identity_and_evidence(self):
        item = {'title': 'Retki', 'date': None, 'end_date': None, 'remember': [], 'needs_review': True, 'evidence': 'Huomenna retki.', 'source_message_id': '1:2'}
        out = job.validate({'items': [item]}, self.messages, date(2026, 11, 7))
        self.assertEqual(out[0]['student'], 'Neve')
        self.assertTrue(out[0]['date_unknown'])
        item['evidence'] = 'Invented'
        with self.assertRaises(ValueError):
            job.validate({'items': [item]}, self.messages, date(2026, 11, 7))

    @patch('data.school_reminders.fetch_messages', side_effect=AssertionError('no live calls'))
    def test_display_reads_summary_only(self, live):
        with patch('data.school_reminders._load_json', return_value={'items': [], 'fetched_at': '2020-01-01T03:15:00'}):
            data = fetch({'wilma_ai': {'provider': 'codex_file'}})
        self.assertTrue(data['_stale'])
        live.assert_not_called()

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import urlopen
from urllib.error import HTTPError

import web_dashboard
from school_summary_page import school_payload


class SchoolPageTests(unittest.TestCase):
    def test_payload_keeps_all_reminders_without_raw_student_metadata(self):
        items = [{'student': 'Neve Sukunimi Koulu 4C', 'student_id': 'secret-id',
                  'source_message_id': 'internal', 'title': f'Muistutus {i}',
                  'remember': ['Eväät mukaan'], 'date_unknown': i % 2 == 0}
                 for i in range(13)]
        with patch('school_summary_page._load_json', return_value=None), patch('school_summary_page.fetch', return_value={
                'items': items, 'fetched_at': '2026-11-07T03:15:00', '_stale': True}) as read:
            payload = school_payload()
        self.assertEqual(len(payload['items']), 13)
        self.assertEqual({x['student'] for x in payload['items']}, {'Neve'})
        self.assertNotIn('student_id', payload['items'][0])
        self.assertNotIn('source_message_id', payload['items'][0])
        self.assertTrue(payload['stale'])
        read.assert_called_once_with({'wilma_ai': {'provider': 'codex_file'}})

    def test_http_routes_serve_page_and_summary_and_handle_failure(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), web_dashboard.make_handler(
            SimpleNamespace(last_error=None), 30, 'unused-config.yaml', True))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with urlopen(base + '/school') as response:
                self.assertIn('id="school-page"', response.read().decode())
                self.assertIn('no-store', response.headers['Cache-Control'])
            sample = {'items': [], 'stale': False, 'fetched_at': None}
            with patch('web_dashboard.school_payload', return_value=sample):
                with urlopen(base + '/school-reminders.json') as response:
                    self.assertEqual(json.load(response), sample)
            with patch('web_dashboard.school_payload', side_effect=ValueError('broken')):
                with self.assertLogs('dashboard.web', level='ERROR'):
                    with self.assertRaises(HTTPError) as error:
                        urlopen(base + '/school-reminders.json')
                self.assertEqual(error.exception.code, 503)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

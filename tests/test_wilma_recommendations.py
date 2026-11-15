import json
from pathlib import Path
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from analysis import wilma_recommendations as advice
import web_dashboard


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 11, 7)
        self.records = [{'id': '0', 'student': 'Neve', 'title': 'Englannin läksy'},
                        {'id': '1', 'student': 'Sera', 'title': 'Matematiikan koe'}]
        self.raw = {'children': [{'student': name, 'sentences': [
            {'text': sentence, 'record_ids': [key]} for sentence in
            ['Tarkista tehtävät Wilmasta.', 'Tee tarvittaessa annetut tehtävät.',
             'Varaa rauhallinen hetki harjoitteluun.']]} for name, key in [('Neve', '0'), ('Sera', '1')]]}

    def test_exactly_three_sentences_and_local_child_sources(self):
        result = advice.validate(self.raw, self.records)
        self.assertEqual([len(c['sentences']) for c in result], [3, 3])
        self.raw['children'][0]['sentences'][0]['record_ids'] = ['1']
        with self.assertRaises(ValueError):
            advice.validate(self.raw, self.records)

    def test_multiple_sentences_in_one_field_are_rejected(self):
        self.raw['children'][0]['sentences'][0]['text'] = 'Tee tehtävät. Lue kirjaa.'
        with self.assertRaises(ValueError):
            advice.validate(self.raw, self.records)

    def test_old_notes_are_not_current_tasks(self):
        details = {'items': [{'student': 'Sera Testi', 'kind': 'note', 'date': '2026-10-01', 'title': 'Vanha'},
                             {'student': 'Sera Testi', 'kind': 'note', 'date': '2026-11-06', 'title': 'Uusi'}]}
        prepared = advice.prepare(details, {'items': []}, self.today)
        self.assertEqual([r['title'] for r in prepared], ['Uusi'])
        self.assertEqual(prepared[0]['student'], 'Sera')

    def test_cache_reused_but_date_change_refreshes_advice(self):
        self.assertNotEqual(advice.fingerprint(self.records, self.today),
                            advice.fingerprint(self.records, self.today + timedelta(days=1)))
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            for filename in ['wilma_schoolwork.json', 'wilma_codex_summary.json']:
                (cache / filename).write_text(json.dumps({'fetched_at': '2026-11-07T12:00:00', 'items': []}))
            expected = advice.validate(self.raw, self.records)
            with patch.object(advice, 'generate', return_value=expected) as model:
                advice.update(cache, self.today)
                advice.update(cache, self.today)
                model.assert_called_once()
                stored = json.loads((cache / 'wilma_recommendations.json').read_text())
                self.assertEqual(stored['period_start'], '2026-11-08')
                self.assertEqual(stored['period_end'], '2026-11-09')
            old = (cache / 'wilma_recommendations.json').read_text()
            with patch.object(advice, 'generate', side_effect=RuntimeError('unavailable')):
                with self.assertRaises(RuntimeError):
                    advice.update(cache, self.today + timedelta(days=1))
            self.assertEqual((cache / 'wilma_recommendations.json').read_text(), old)

    def test_recommendations_are_rendered_before_other_sections(self):
        html = web_dashboard._page(30).decode()
        self.assertLess(html.index('Suositukset seuraaville kahdelle päivälle'), html.index('Läksyt ja kokeet'))

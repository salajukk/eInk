import unittest
from datetime import date
from integrations.wilma_schoolwork import parse_homework, parse_exams, parse_attendance
from integrations.wilma_messages import WilmaMessageSourceError
from school_summary_page import category

TODAY = date(2026, 11, 7)


class SchoolworkParserTests(unittest.TestCase):
    def test_homework_keeps_numbers_and_given_date_without_guessing_deadline(self):
        html = '''<main id="main-content"><h3>Kotitehtävät</h3><table>
        <thead><tr><th>Pvm</th><th>Kotitehtävät</th></tr></thead><tbody>
        <tr><td>06.11.2026</td><td>S. 53: tehtävät 5, 6 ja 7. <br>Kirjoita vihkoon.</td></tr>
        <tr><td>01.10.2026</td><td>Vanha tehtävä</td></tr></tbody></table></main>'''
        items = parse_homework(html, 'Englanti', TODAY)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['date'], '2026-11-06')
        self.assertEqual(items[0]['date_label'], 'Annettu')
        self.assertEqual(items[0]['remember'], ['S. 53: tehtävät 5, 6 ja 7. Kirjoita vihkoon.'])
        self.assertNotIn('due_date', items[0])

    def test_exams_keep_scope_and_remove_past_exams(self):
        html = '''<main id="main-content"><table class="table-grey">
        <tr><td><strong>Ti 10.11.2026</strong></td><td>Matematiikan koe</td></tr>
        <tr><th>Kokeen lisätiedot</th><td>Kappaleet 6–10. Ei s. 24.</td></tr></table>
        <table class="table-grey"><tr><td>Ma 2.11.2026</td><td>Vanha koe</td></tr></table></main>'''
        items = parse_exams(html, TODAY)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['remember'], ['Kappaleet 6–10. Ei s. 24.'])

    def test_attendance_continuation_rows_keep_date_and_deduplicate_identical_events(self):
        html = '''<main id="main-content"><table class="attendance-single"><tbody>
        <tr><td rowspan="2">Pe</td><td rowspan="2">6.11.2026</td>
        <td class="event" title="MA; Hyvä!; Hienoa työtä /Opettaja">Opettaja</td></tr>
        <tr><td class="event" title="MA; Hyvä!; Hienoa työtä /Opettaja">Opettaja</td>
        <td class="event" title="Myöhässä /Opettaja">Opettaja</td></tr>
        <tr><td>Ma</td><td>1.9.2026</td><td class="event" title="Vanha">Opettaja</td></tr>
        </tbody></table></main>'''
        items = parse_attendance(html, TODAY)
        self.assertEqual(len(items), 2)
        self.assertTrue(all(i['date'] == '2026-11-06' for i in items))
        self.assertEqual(items[1]['title'], 'Myöhässä /Opettaja')

    def test_missing_layout_is_failure_not_empty_success(self):
        for parser in [lambda x: parse_homework(x, 'Matematiikka', TODAY),
                       lambda x: parse_exams(x, TODAY), lambda x: parse_attendance(x, TODAY)]:
            with self.assertRaises(WilmaMessageSourceError):
                parser('<form><input name="Login"></form>')

    def test_messages_are_grouped_by_concrete_subject(self):
        self.assertEqual(category({'title': 'Matematiikan koe'}), 'schoolwork')
        self.assertEqual(category({'title': 'Lukuläksyn palautus'}), 'schoolwork')
        self.assertEqual(category({'title': 'Retki'}), 'other')
        self.assertEqual(category({'title': 'Hyvä!', 'category': 'notes'}), 'notes')

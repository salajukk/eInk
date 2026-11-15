"""Read-only homework, upcoming exams and recent attendance from Wilma HTML."""
import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup
import requests

from integrations.wilma_messages import _WilmaWebClient, _require_live_config, WilmaMessageSourceError


def text(node):
    return node.get_text(' ', strip=True) if node else ''


def parse_date(value):
    match = re.search(r'\b(\d{1,2})\.(\d{1,2})\.(\d{4})\b', value)
    if not match:
        raise WilmaMessageSourceError('Wilma date missing or changed')
    return date(*map(int, (match[3], match[2], match[1])))


def main_content(html):
    soup = BeautifulSoup(html, 'html.parser')
    main = soup.select_one('main#main-content')
    if main is None or soup.select_one('input[name="Login"]'):
        raise WilmaMessageSourceError('Wilma content missing or login expired')
    return main


def parse_homework(html, subject, today):
    main = main_content(html)
    if not any(text(h) == 'Kotitehtävät' for h in main.select('h3')):
        raise WilmaMessageSourceError('Wilma homework layout changed')
    items = []
    for table in main.select('table'):
        headers = [text(h) for h in table.select('thead th')]
        if headers != ['Pvm', 'Kotitehtävät']:
            continue
        for row in table.select('tbody tr'):
            cells = row.find_all('td', recursive=False)
            if len(cells) < 2:
                raise WilmaMessageSourceError('Wilma homework row changed')
            when, body = parse_date(text(cells[0])), text(cells[1])
            if body and today - timedelta(days=14) <= when <= today:
                items.append({'kind': 'homework', 'category': 'schoolwork', 'title': subject,
                              'date': when.isoformat(), 'date_label': 'Annettu',
                              'remember': [body], 'date_unknown': False})
    return items


def parse_exams(html, today):
    main = main_content(html)
    items = []
    for table in main.select('table.table-grey'):
        cells = table.select_one('tr').find_all('td', recursive=False)
        if len(cells) != 2:
            raise WilmaMessageSourceError('Wilma exam layout changed')
        when = parse_date(text(cells[0]))
        extra = []
        for row in table.select('tr')[1:]:
            heading = row.find('th')
            if heading and text(heading) == 'Kokeen lisätiedot':
                extra.append(text(row.find('td')))
        if when >= today:
            items.append({'kind': 'exam', 'category': 'schoolwork', 'title': text(cells[1]),
                          'date': when.isoformat(), 'date_label': 'Koe', 'remember': extra,
                          'date_unknown': False})
    if not items and not main.select('table.table-grey') and 'koe' not in text(main).lower():
        raise WilmaMessageSourceError('Wilma exam content missing')
    return items


def parse_attendance(html, today):
    main = main_content(html)
    table = main.select_one('table.attendance-single')
    if table is None:
        raise WilmaMessageSourceError('Wilma attendance layout changed')
    items, seen, current_date = [], set(), None
    for row in table.select('tbody tr'):
        cells = row.find_all('td', recursive=False)
        # Dates can span several rows. Keep the current date for continuation rows.
        for cell in cells[:2]:
            if re.search(r'\b\d{1,2}\.\d{1,2}\.\d{4}\b', text(cell)):
                current_date = parse_date(text(cell))
                break
        for cell in row.select('td.event'):
            body = str(cell.get('title') or '').strip()
            if not body or current_date is None:
                raise WilmaMessageSourceError('Wilma attendance details missing')
            key = (current_date, body)
            if key in seen or not today - timedelta(days=28) <= current_date <= today:
                continue
            seen.add(key)
            items.append({'kind': 'note', 'category': 'notes', 'title': body,
                          'date': current_date.isoformat(), 'date_label': 'Merkintä',
                          'remember': [], 'date_unknown': False})
    return items


def fetch_schoolwork(config, today=None):
    today = today or date.today()
    cfg = config.get('wilma_messages') or {}
    base, username, password = _require_live_config(cfg)
    client = _WilmaWebClient(base, username, password)
    requested = {str(x) for x in cfg.get('child_ids') or []}
    try:
        client.login()
        children = client.children()
        if requested:
            children = [c for c in children if c['id'] in requested]
            if {c['id'] for c in children} != requested:
                raise WilmaMessageSourceError('Configured Wilma children missing')
        if not children:
            raise WilmaMessageSourceError('No Wilma children found')
        items = []
        for child in children:
            prefix = '/!' + child['id'] + '/'
            def get(path):
                response = client.session.get(base.rstrip('/') + prefix + path, timeout=20)
                response.raise_for_status()
                return response.text
            home = BeautifulSoup(get(''), 'html.parser')
            groups = {}
            for link in home.select('a[href]'):
                path = link['href']
                if re.fullmatch(re.escape(prefix) + r'groups/\d+', path):
                    label = text(link)
                    groups[path[len(prefix):]] = label.split(':', 1)[-1].strip() or label
            if not groups:
                raise WilmaMessageSourceError('Wilma teaching groups missing')
            child_items = []
            for path, subject in groups.items():
                child_items.extend(parse_homework(get(path), subject, today))
            child_items.extend(parse_exams(get('exams/calendar'), today))
            child_items.extend(parse_attendance(get('attendance/view?range=0'), today))
            for item in child_items:
                items.append({**item, 'student': child['name'], 'student_id': child['id'],
                              'source': 'wilma_schoolwork'})
        return {'items': items, 'fetched_at': datetime.now().isoformat(timespec='seconds'),
                'homework_days': 14, 'notes_days': 28}
    except requests.RequestException:
        raise WilmaMessageSourceError('Wilma schoolwork network request failed') from None
    finally:
        client.session.close()

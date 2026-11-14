"""Read-only school page payload from local Wilma snapshots. No remote calls."""
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from data.school_reminders import fetch, _load_json


def category(item):
    if item.get('category') in {'schoolwork', 'notes', 'other'}:
        return item['category']
    title = str(item.get('title') or '')
    return 'schoolwork' if re.search(r'läks|kotiteht|\bkoe\b|koke[ei]|kertotaulutest', title, re.I) else 'other'


def school_payload():
    summary = fetch({'wilma_ai': {'provider': 'codex_file'}})
    details = _load_json(Path('cache/wilma_schoolwork.json')) or {}
    status = _load_json(Path('cache/wilma_schoolwork_status.json')) or {}
    today = date.today()
    detail_items = []
    for item in details.get('items') or []:
        try:
            when = date.fromisoformat(item['date'])
        except (ValueError, KeyError, TypeError):
            continue
        kind = item.get('kind')
        if kind == 'exam' and when < today:
            continue
        if kind in {'homework', 'note'} and when < today - timedelta(days=14 if kind == 'homework' else 28):
            continue
        detail_items.append(item)
    items = []
    for item in detail_items + (summary.get('items') or []):
        name = str(item.get('student') or 'Koulu').split()
        items.append({
            'student': name[0] if name else 'Koulu',
            'title': item.get('title') or '', 'date': item.get('date'),
            'end_date': item.get('end_date'), 'date_unknown': bool(item.get('date_unknown')),
            'needs_review': bool(item.get('needs_review')), 'remember': item.get('remember') or [],
            'evidence': item.get('evidence') or '', 'category': category(item),
            'kind': item.get('kind') or 'reminder', 'date_label': item.get('date_label') or '',
        })
    details_stale = status.get('ok') is False
    try:
        details_stale |= (datetime.now() - datetime.fromisoformat(details['fetched_at'])).total_seconds() > 36 * 3600
    except (ValueError, KeyError, TypeError):
        details_stale = True
    advice = _load_json(Path('cache/wilma_recommendations.json')) or {}
    advice_status = _load_json(Path('cache/wilma_recommendations_status.json')) or {}
    advice_stale = (advice.get('reference_date') != today.isoformat()
                    or advice_status.get('ok') is False)
    return {'recommendations': advice.get('children') or [],
            'recommendations_start': advice.get('period_start'),
            'recommendations_end': advice.get('period_end'),
            'recommendations_stale': advice_stale,
            'recommendations_updated': advice.get('generated_at'), 'items': items, 'fetched_at': summary.get('fetched_at'),
            'stale': bool(summary.get('_stale')), 'schoolwork_fetched_at': details.get('fetched_at'),
            'schoolwork_stale': details_stale}

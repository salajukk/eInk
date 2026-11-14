#!/usr/bin/env python3
"""Fetch Wilma locally, summarize changed messages with logged-in Codex, publish atomically."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import date, datetime

import yaml

from analysis.wilma_ai import FIELDS, INSTRUCTIONS
from data.school_reminders import remove_expired, _dedupe_reminders, _message_reference_date
from integrations.wilma_messages import fetch_messages

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'cache'
VERSION = 'codex-nightly-v1'


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default


def atomic_json(path, value):
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def digest(message):
    return hashlib.sha256((VERSION + json.dumps(message, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()


def validate(raw, messages, today):
    if not isinstance(raw, dict) or not isinstance(raw.get('items'), list):
        raise ValueError('Invalid summary')
    by_id = {m['id']: m for m in messages}
    out = []
    for item in raw['items']:
        message = by_id[item['source_message_id']]
        if (not isinstance(item.get('title'), str) or not item['title'].strip()
                or len(item['title']) > 160 or type(item.get('needs_review')) is not bool
                or not isinstance(item.get('evidence'), str) or not item['evidence'].strip()
                or ' '.join(item['evidence'].split()) not in ' '.join((message['subject'] + '\n' + message['body']).split())
                or not isinstance(item.get('remember'), list)
                or any(not isinstance(v, str) or len(v) > 200 for v in item['remember'])):
            raise ValueError('Invalid reminder or evidence')
        when = date.fromisoformat(item['date']) if item['date'] else None
        end = date.fromisoformat(item['end_date']) if item['end_date'] else None
        if end and (not when or end < when):
            raise ValueError('Invalid date range')
        review = item['needs_review'] or when is None
        out.append({**item, 'date': (when or today).isoformat(), 'date_unknown': when is None,
                    'title': ('Tarkista: ' if review else '') + item['title'],
                    'source': 'wilma_message', 'student': message.get('student'),
                    'student_id': message.get('student_id'), 'action_required': True,
                    'confidence': 0.5 if review else 0.9, 'analyzer': VERSION})
    return out


def summarize(messages, today):
    properties = {**FIELDS, 'source_message_id': {'type': 'string'}}
    schema = {'type': 'object', 'properties': {'items': {'type': 'array', 'items': {
        'type': 'object', 'properties': properties, 'required': list(properties),
        'additionalProperties': False}}}, 'required': ['items'], 'additionalProperties': False}
    inputs = [{'id': m['id'], 'sent_date': _message_reference_date(m, today).isoformat(),
               'subject': m['subject'], 'body': m['body']} for m in messages]
    prompt = (INSTRUCTIONS + '\nAnalysoi kaikki seuraavat viestit. Käytä vain annettuja '
              'source_message_id-tunnisteita. Älä käytä työkaluja. Tänään on ' + today.isoformat()
              + '. Palauta kaikki tulevat muistutukset, myös myöhemmät kuin seuraava viikko.\n'
              + json.dumps(inputs, ensure_ascii=False))
    with tempfile.TemporaryDirectory(prefix='wilma-codex-') as name:
        work = Path(name)
        (work / 'schema.json').write_text(json.dumps(schema))
        command = ['/home/salamapi/.local/bin/codex', 'exec', '--ignore-user-config',
                   '--skip-git-repo-check', '--ephemeral', '--sandbox', 'read-only',
                   '-c', 'approval_policy="never"', '-c', 'mcp_servers={}',
                   '--cd', name, '--output-schema', str(work / 'schema.json'),
                   '--output-last-message', str(work / 'summary.json'), '-']
        result = subprocess.run(command, input=prompt, text=True, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, timeout=1200)
        if result.returncode:
            raise RuntimeError('Codex summary failed; previous summary retained')
        raw = json.loads((work / 'summary.json').read_text())
        atomic_json(CACHE / 'wilma_codex_last_result.json', raw)
        return validate(raw, messages, today)


def run():
    os.umask(0o077)
    CACHE.mkdir(exist_ok=True)
    with (CACHE / 'wilma_nightly.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        atomic_json(CACHE / 'wilma_recommendations_status.json', {'ok': False})
        cfg = yaml.safe_load((ROOT / 'config.yaml').read_text())
        from integrations.wilma_schoolwork import fetch_schoolwork
        try:
            schoolwork = fetch_schoolwork(cfg)
            atomic_json(CACHE / 'wilma_schoolwork.json', schoolwork)
            atomic_json(CACHE / 'wilma_schoolwork_status.json', {'ok': True})
            print(f"Wilma schoolwork updated: {len(schoolwork['items'])} entries", flush=True)
        except Exception:
            atomic_json(CACHE / 'wilma_schoolwork_status.json', {'ok': False})
            print('Wilma schoolwork fetch failed; previous data retained', flush=True)
        messages = fetch_messages(cfg)
        if not messages:
            raise ValueError('No Wilma messages fetched; previous summary retained')
        atomic_json(CACHE / 'wilma_messages.json', {'messages': messages, 'fetched_at': datetime.now().isoformat()})
        today = date.today()
        previous = read_json(CACHE / 'wilma_codex_state.json', {'messages': {}})['messages']
        changed = [m for m in messages if previous.get(m['id'], {}).get('hash') != digest(m)]
        # Bound each call without silently truncating individual messages.
        groups, batch, size = [], [], 0
        for message in changed:
            length = len(message['body']) + len(message['subject'])
            if length > 60000:
                raise ValueError('Message exceeds summary input limit')
            if batch and size + length > 60000:
                groups.append(batch)
                batch, size = [], 0
            batch.append(message)
            size += length
        if batch:
            groups.append(batch)
        extracted = []
        for group in groups:
            extracted.extend(summarize(group, today))
        state = dict(previous)
        for message in changed:
            state[message['id']] = {'hash': digest(message), 'reminders': [
                r for r in extracted if r['source_message_id'] == message['id']]}
        items = _dedupe_reminders(remove_expired([
            r for entry in state.values() for r in entry['reminders']], today))
        now = datetime.now().isoformat(timespec='seconds')
        # Publish the display first. Interrupted state publication merely causes a retry.
        atomic_json(CACHE / 'wilma_codex_summary.json', {
            'items': items, 'fetched_at': now, 'source_message_count': len(messages), 'analyzer': VERSION})
        atomic_json(CACHE / 'wilma_codex_state.json', {'messages': state, 'updated_at': now})
        from analysis.wilma_recommendations import update
        try:
            update(CACHE, today)
            atomic_json(CACHE / 'wilma_recommendations_status.json', {'ok': True})
            print('Two-day recommendations updated', flush=True)
        except Exception:
            atomic_json(CACHE / 'wilma_recommendations_status.json', {'ok': False})
            print('Recommendations failed; previous recommendations retained', flush=True)
        print(f'Wilma summary updated: {len(messages)} messages, {len(changed)} changed, {len(items)} reminders')


if __name__ == '__main__':
    try:
        run()
    except Exception as exc:
        # Avoid printing source data, request details or credentials.
        print(f'Wilma nightly failed ({type(exc).__name__}); previous summary retained')
        raise SystemExit(1)

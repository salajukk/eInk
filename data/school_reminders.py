"""Structured school reminders derived from Wilma messages.

This phase adds live/fixture source support plus local state and cache. Raw Wilma
message bodies are analyzed in memory and are not persisted. The module is still
kept separate from the dashboard renderer so the live source can be validated
before anything becomes visible on the family display.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from analysis.wilma_reminders import ANALYZER_VERSION, analyze_message
from integrations.wilma_messages import WilmaMessageSourceError, fetch_messages

CACHE_FILE = Path("cache/school_reminders.json")
STATE_FILE = Path("cache/wilma_message_state.json")
STRONG_SINGLE_WORD_EVENTS = {"retki", "koe", "vanhempainilta", "liikuntapäivä"}


def _load_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _cache_is_fresh(ttl_minutes: int) -> bool:
    if not CACHE_FILE.exists():
        return False
    age = datetime.now().timestamp() - CACHE_FILE.stat().st_mtime
    return age < ttl_minutes * 60


def remove_expired(reminders: list[dict], today: date | None = None) -> list[dict]:
    today = today or date.today()
    active = []
    for reminder in reminders:
        expiry = str(reminder.get("end_date") or reminder.get("date") or "")
        try:
            expiry_date = date.fromisoformat(expiry)
        except ValueError:
            continue
        if expiry_date >= today:
            active.append(reminder)
    return active


def _tokens(value: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch in "åäö" else " " for ch in value)
    stop = {"ja", "sekä", "the", "a", "an"}
    return {token for token in cleaned.split() if len(token) >= 3 and token not in stop}


def calendar_match(reminder: dict, event: dict) -> bool:
    """Return True only for a conservative same-day title match."""
    if str(reminder.get("date") or "") != str(event.get("date") or ""):
        return False

    reminder_tokens = _tokens(str(reminder.get("title") or ""))
    event_tokens = _tokens(str(event.get("title") or ""))
    if not reminder_tokens or not event_tokens:
        return False

    if len(reminder_tokens) == 1:
        token = next(iter(reminder_tokens))
        return token in STRONG_SINGLE_WORD_EVENTS and token in event_tokens

    overlap = len(reminder_tokens & event_tokens) / len(reminder_tokens)
    return overlap >= 0.8


def reconcile_with_calendar(reminders: list[dict], calendar: dict | None) -> dict:
    """Split reminders into standalone rows and calendar enrichments."""
    events = (calendar or {}).get("events") or []
    standalone = []
    enrichments = []

    for reminder in reminders:
        match = next((event for event in events if calendar_match(reminder, event)), None)
        if match:
            enrichments.append({"event": match, "reminder": reminder})
        else:
            standalone.append(reminder)

    return {"standalone": standalone, "enrichments": enrichments}


def _message_hash(message: dict) -> str:
    """Hash analysis-relevant fields without persisting the raw body."""
    payload = "\n".join(
        [ANALYZER_VERSION]
        + [
            str(message.get(key) or "")
            for key in ("id", "sent_at", "subject", "body", "student", "student_id")
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _message_reference_date(message: dict, fallback: date) -> date:
    """Resolve relative wording against message send date when it is available."""
    sent_at = str(message.get("sent_at") or "").strip()
    if sent_at:
        try:
            return date.fromisoformat(sent_at[:10])
        except ValueError:
            pass
    return fallback


def _dedupe_reminders(reminders: list[dict]) -> list[dict]:
    """Collapse exact duplicates without losing which child the reminder belongs to."""
    result = []
    seen = set()
    for reminder in reminders:
        remember = tuple(sorted(str(item).strip().casefold() for item in reminder.get("remember") or []))
        student_key = str(reminder.get("student_id") or reminder.get("student") or "").strip().casefold()
        key = (
            str(reminder.get("date") or ""),
            str(reminder.get("end_date") or ""),
            str(reminder.get("title") or "").strip().casefold(),
            remember,
            student_key,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(reminder)
    result.sort(
        key=lambda item: (
            item.get("date") or "",
            item.get("student") or "",
            item.get("title") or "",
        )
    )
    return result


def build(config: dict, reference_date: date | None = None) -> dict:
    """Fetch/analyze messages while reusing state for unchanged message bodies."""
    today = reference_date or date.today()
    messages = fetch_messages(config)
    previous = _load_json(STATE_FILE) or {}
    previous_messages = previous.get("messages") or {}
    if not isinstance(previous_messages, dict):
        previous_messages = {}

    state_messages: dict[str, dict] = {}
    all_reminders: list[dict] = []
    fetched_ids: set[str] = set()
    now_iso = datetime.now().isoformat(timespec="seconds")

    for message in messages:
        message_id = str(message.get("id") or "").strip()
        if not message_id:
            continue
        fetched_ids.add(message_id)
        digest = _message_hash(message)
        old = previous_messages.get(message_id)

        if isinstance(old, dict) and old.get("hash") == digest:
            reminders = remove_expired(old.get("reminders") or [], today)
        else:
            analysis_date = reference_date or _message_reference_date(message, today)
            reminders = remove_expired(analyze_message(message, analysis_date), today)

        state_messages[message_id] = {
            "hash": digest,
            "reminders": reminders,
            "last_seen": now_iso,
        }
        all_reminders.extend(reminders)

    # The live adapter intentionally fetches only a bounded recent-message window.
    # Preserve older state entries while they still contain a future reminder.
    for message_id, old in previous_messages.items():
        if message_id in fetched_ids or not isinstance(old, dict):
            continue
        reminders = remove_expired(old.get("reminders") or [], today)
        if not reminders:
            continue
        state_messages[message_id] = {
            "hash": str(old.get("hash") or ""),
            "reminders": reminders,
            "last_seen": str(old.get("last_seen") or ""),
        }
        all_reminders.extend(reminders)

    items = _dedupe_reminders(remove_expired(all_reminders, today))
    _save_json(
        STATE_FILE,
        {
            "messages": state_messages,
            "updated_at": now_iso,
        },
    )
    return {
        "items": items,
        "fetched_at": now_iso,
        "source_message_count": len(messages),
    }


def fetch(config: dict, use_cache: bool = True) -> dict:
    cache_cfg = config.get("cache") or {}
    try:
        ttl = int(cache_cfg.get("wilma_messages_ttl_minutes", 30))
    except (TypeError, ValueError):
        ttl = 30
    ttl = max(1, ttl)

    if use_cache and _cache_is_fresh(ttl):
        cached = _load_json(CACHE_FILE)
        if cached:
            cached["items"] = remove_expired(cached.get("items") or [])
            return cached

    try:
        data = build(config)
    except WilmaMessageSourceError:
        cached = _load_json(CACHE_FILE)
        if cached:
            cached["items"] = remove_expired(cached.get("items") or [])
            cached["_stale"] = True
            return cached
        raise

    _save_json(CACHE_FILE, data)
    return data

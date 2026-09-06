"""Structured school reminders derived from Wilma messages.

This module is not wired into ``main.py`` yet. Phase 1 establishes the data
contract, expiry logic and conservative calendar reconciliation using synthetic
messages only.
"""

from __future__ import annotations

from datetime import date, datetime

from analysis.wilma_reminders import analyze_messages
from integrations.wilma_messages import fetch_messages

STRONG_SINGLE_WORD_EVENTS = {"retki", "koe", "vanhempainilta", "liikuntapäivä"}


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
    """Split reminders into standalone rows and calendar enrichments.

    A calendar match is not discarded: remember-items are preserved in an
    enrichment record so phase 3 can attach them to the existing event instead
    of rendering a duplicate event.
    """
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


def build(config: dict, reference_date: date | None = None) -> dict:
    reference_date = reference_date or date.today()
    messages = fetch_messages(config)
    reminders = analyze_messages(messages, reference_date)
    reminders = remove_expired(reminders, reference_date)
    return {
        "items": reminders,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def fetch(config: dict, use_cache: bool = True) -> dict:
    # Cache is deliberately deferred until the live adapter exists. Fixtures are
    # small, deterministic and useful for repeatable tests during phase 1.
    return build(config)

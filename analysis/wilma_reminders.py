"""Conservative extraction of actionable reminders from Finnish Wilma messages.

The analyzer is deliberately independent from the Wilma transport and the
renderer. A later AI-backed analyzer can replace :func:`analyze_message`
without changing the surrounding data flow.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

WEEKDAYS = {
    "maanantaina": 0,
    "tiistaina": 1,
    "keskiviikkona": 2,
    "torstaina": 3,
    "perjantaina": 4,
    "lauantaina": 5,
    "sunnuntaina": 6,
}

SUBJECTS = {
    "matematiikan": "Matematiikan",
    "äidinkielen": "Äidinkielen",
    "englannin": "Englannin",
    "ruotsin": "Ruotsin",
    "ympäristöopin": "Ympäristöopin",
    "historian": "Historian",
    "biologian": "Biologian",
    "fysiikan": "Fysiikan",
    "kemian": "Kemian",
}

EVENT_RULES = (
    (re.compile(r"\bretk(?:i|elle|ellä|en|ellä)\b", re.I), "Retki", 0.92),
    (re.compile(r"\bvanhempainilta\w*\b", re.I), "Vanhempainilta", 0.94),
    (re.compile(r"\bliikuntapäiv\w*\b", re.I), "Liikuntapäivä", 0.92),
)

EXPLICIT_DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(?:(\d{4})\b)?")


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]


def _next_weekday(reference: date, weekday: int, force_next_week: bool = False) -> date:
    if force_next_week:
        next_monday = reference + timedelta(days=(7 - reference.weekday()))
        return next_monday + timedelta(days=weekday)
    delta = (weekday - reference.weekday()) % 7
    return reference + timedelta(days=delta)


def resolve_date(text: str, reference_date: date) -> date | None:
    """Resolve only a small set of high-confidence Finnish date expressions."""
    lower = text.casefold()

    explicit = EXPLICIT_DATE_RE.search(lower)
    if explicit:
        day, month = int(explicit.group(1)), int(explicit.group(2))
        year = int(explicit.group(3)) if explicit.group(3) else reference_date.year
        try:
            return date(year, month, day)
        except ValueError:
            return None

    if "ylihuomenna" in lower:
        return reference_date + timedelta(days=2)
    if "huomenna" in lower:
        return reference_date + timedelta(days=1)
    if "tänään" in lower:
        return reference_date

    for word, weekday in WEEKDAYS.items():
        if word in lower:
            force_next = bool(re.search(rf"\bensi\s+viikon\s+{re.escape(word)}\b", lower))
            return _next_weekday(reference_date, weekday, force_next_week=force_next)

    return None


def _subject_in(sentence: str) -> str | None:
    lower = sentence.casefold()
    for token, label in SUBJECTS.items():
        if token in lower:
            return label
    return None


def _event_title(sentence: str, subject_context: str | None) -> tuple[str, float] | None:
    for pattern, title, confidence in EVENT_RULES:
        if pattern.search(sentence):
            return title, confidence

    if re.search(r"\bkoe(?:\w*)\b|\bkokeen\b", sentence, re.I):
        title = f"{subject_context} koe" if subject_context else "Koe"
        return title, 0.91 if subject_context else 0.84
    return None


def _standalone_action(sentence: str) -> tuple[str, float] | None:
    lower = sentence.casefold()
    if "geometriset välineet" in lower or "geometrisia välineitä" in lower:
        return "Geometriset välineet mukaan", 0.92

    # Keep the first MVP intentionally narrow. Generic imperatives are easy to
    # over-detect in school newsletters, so add them only after fixture tests.
    return None


def _remember_items(sentence: str) -> list[str]:
    match = re.search(r"\bmukana\s+(.+?)(?:[.!?]|$)", sentence, re.I)
    if not match:
        return []

    raw = match.group(1).strip()
    raw = re.sub(r"^(?:myös\s+)?", "", raw, flags=re.I)
    parts = [part.strip(" ,") for part in re.split(r"\s+ja\s+|,", raw) if part.strip(" ,")]
    result = []
    for part in parts:
        clean = re.sub(r"^(?:omat|oma|oppilaan)\s+", "", part, flags=re.I).strip()
        if not clean:
            continue
        clean = clean[0].upper() + clean[1:]
        if "evä" in clean.casefold() and "mukaan" not in clean.casefold():
            clean = "Eväät mukaan"
        result.append(clean)
    return result


def _new_reminder(title: str, when: date, confidence: float, message_id: str) -> dict:
    return {
        "title": title,
        "date": when.isoformat(),
        "end_date": None,
        "remember": [],
        "action_required": True,
        "confidence": confidence,
        "source": "wilma_message",
        "source_message_id": message_id,
    }


def analyze_message(message: dict, reference_date: date) -> list[dict]:
    """Extract only high-confidence actionable reminders from one message.

    Dates must be resolvable. Informational sentences without a concrete event,
    deadline or supported action produce no reminder.
    """
    body = str(message.get("body") or "").strip()
    if not body:
        return []

    message_id = str(message.get("id") or "")
    current_date: date | None = None
    subject_context: str | None = None
    active_by_date: dict[str, dict] = {}
    reminders: list[dict] = []

    for sentence in _sentences(body):
        found_subject = _subject_in(sentence)
        if found_subject:
            subject_context = found_subject

        found_date = resolve_date(sentence, reference_date)
        if found_date:
            current_date = found_date

        if current_date is None:
            continue

        event = _event_title(sentence, subject_context)
        if event:
            title, confidence = event
            reminder = _new_reminder(title, current_date, confidence, message_id)
            reminders.append(reminder)
            active_by_date[current_date.isoformat()] = reminder

        action = _standalone_action(sentence)
        if action and not event:
            title, confidence = action
            reminder = _new_reminder(title, current_date, confidence, message_id)
            reminders.append(reminder)
            active_by_date[current_date.isoformat()] = reminder

        remember = _remember_items(sentence)
        if remember:
            target = active_by_date.get(current_date.isoformat())
            if target:
                for item in remember:
                    if item not in target["remember"]:
                        target["remember"].append(item)

    return reminders


def analyze_messages(messages: list[dict], reference_date: date) -> list[dict]:
    reminders = []
    for message in messages:
        reminders.extend(analyze_message(message, reference_date))
    reminders.sort(key=lambda item: (item.get("date") or "", item.get("title") or ""))
    return reminders

# Wilma message reminders – MVP

This feature extracts only actionable school reminders from free-form Wilma
messages. It must not render whole messages on the family dashboard.

## Phase 1: synthetic messages only

The first implementation intentionally does **not** log in to Wilma and does not
change the dashboard yet. It establishes three replaceable layers:

```text
integrations/wilma_messages.py  -> message source adapter
analysis/wilma_reminders.py     -> conservative Finnish text analysis
data/school_reminders.py        -> expiry + calendar reconciliation contract
```

Synthetic examples live in `tests/fixtures/wilma_messages.json`. They contain no
real family, school or account data.

Run the phase-1 tests with the project's virtual-environment Python:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_wilma_reminders -v
```

The initial analyzer recognizes only a deliberately small set of high-confidence
patterns: explicit/relative dates, selected school events, mathematics tests,
and a small number of concrete bring-with-you actions. Informational newsletters
without a concrete dated action are ignored.

## Structured reminder contract

Example:

```json
{
  "title": "Retki",
  "date": "2026-09-16",
  "end_date": null,
  "remember": ["Eväät mukaan", "Säänmukainen vaatetus"],
  "action_required": true,
  "confidence": 0.92,
  "source": "wilma_message",
  "source_message_id": "retki-1"
}
```

`data/school_reminders.py` removes reminders whose date/end date has passed. It
also contains conservative same-day calendar matching. A match is returned as an
`enrichment` instead of being discarded so the later dashboard integration can
attach remember-items to the existing calendar event rather than show a duplicate.

## Next phases

1. Add a live Wilma adapter behind `integrations/wilma_messages.py` without
   exposing credentials to the repository or chat.
2. Add local cache/state so only new/changed messages need analysis and raw Wilma
   message bodies do not need to be persisted.
3. Wire `school_reminders` into `main.py` and add a compact
   `KOULUSTA MUISTETTAVAA` area to the 960x680 renderer only.
4. Keep the 7.5-inch renderer unchanged.

The text analyzer is intentionally replaceable. A later AI-backed implementation
can keep the same structured reminder contract.

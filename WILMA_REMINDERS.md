# Wilma message reminders – MVP

This feature extracts only actionable school reminders from free-form Wilma
messages. It must not render whole messages on the family dashboard.

The implementation is intentionally split into replaceable layers:

```text
integrations/wilma_messages.py  -> message source adapter
analysis/wilma_reminders.py     -> conservative Finnish text analysis
data/school_reminders.py        -> expiry + local state/cache + reconciliation contract
```

The dashboard renderer is still unchanged in the current phase.

## Phase 1: synthetic analysis

Synthetic examples live in `tests/fixtures/wilma_messages.json`. They contain no
real family, school or account data.

Run the tests with the project's virtual-environment Python:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_wilma_reminders -v
```

The initial analyzer recognizes only a deliberately small set of high-confidence
patterns: explicit/relative dates, selected school events, mathematics tests,
and a small number of concrete bring-with-you actions. Informational newsletters
without a concrete dated action are ignored.

## Phase 2: live Wilma adapter and private local state

`integrations/wilma_messages.py` now also has a small live adapter for the
community-observed Wilma web login/message endpoints. It deliberately stays
behind the same normalized `fetch_messages()` boundary because this is an
unofficial integration and Wilma may change the endpoint/login behaviour later.

No extra Python package is required by this adapter: it uses the project's
existing `requests` dependency plus Python's standard-library HTML parser.

Real credentials belong only in the local gitignored `config.yaml`. Example
shape (use your own values locally; never commit or paste them into chat):

```yaml
wilma_messages:
  provider: "live"
  base_url: "https://YOUR-WILMA.inschool.fi"
  username: "YOUR_WILMA_USERNAME"
  password: "YOUR_WILMA_PASSWORD"
  child_ids: []
  limit_per_child: 20

cache:
  wilma_messages_ttl_minutes: 30
```

An empty `child_ids` list means that the adapter tries to discover all children
linked to the parent account. `limit_per_child` only limits how many recent
message bodies are downloaded during one poll.

Test the live path without changing the dashboard:

```powershell
.\venv\Scripts\python.exe wilma_reminders_check.py --no-cache
```

The diagnostic prints only structured reminder data. It does not print the raw
Wilma message bodies.

### Privacy/state behaviour

Raw message bodies are analyzed in memory and are **not persisted**. Local
state stores only a SHA-256 content hash, the structured reminder result and
minimal timestamps in:

```text
cache/wilma_message_state.json
cache/school_reminders.json
```

Both files are covered by the existing `cache/*` gitignore rule.

Only new or changed message content is analyzed again. The analyzer version is
part of the content hash, so a future rule-version change can also force a safe
reanalysis. Older messages may fall outside the bounded download window, but a
future reminder already extracted from such a message stays in local state until
its date/end date has passed.

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
  "source_message_id": "123:456"
}
```

Relative wording such as `ensi viikon keskiviikkona` is resolved against the
message send date when the live source provides one, rather than against the day
when the dashboard happens to process the message.

`data/school_reminders.py` removes reminders whose date/end date has passed. It
also contains conservative same-day calendar matching. A match is returned as an
`enrichment` instead of being discarded so the later dashboard integration can
attach remember-items to the existing calendar event rather than show a duplicate.

## Next phase

After the live adapter has been validated against the family's real Wilma account:

1. wire the structured `school_reminders` result into the shared data/render path
2. reconcile it with the already-fetched calendar data
3. add a compact `KOULUSTA MUISTETTAVAA` area to `render_family_13in3.py`
4. keep the 7.5-inch renderer unchanged

The text analyzer remains intentionally replaceable. A later AI-backed
implementation can keep exactly the same structured reminder contract.

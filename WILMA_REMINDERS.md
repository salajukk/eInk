# Wilma message reminders – MVP

This feature extracts only actionable school reminders from free-form Wilma
messages. It must not render whole messages on the family dashboard.

The implementation is intentionally split into replaceable layers:

```text
integrations/wilma_messages.py  -> message source adapter
analysis/wilma_reminders.py     -> conservative Finnish text analysis
data/school_reminders.py        -> expiry + local state/cache + reconciliation contract
main.py                         -> presentation-time calendar reconciliation
render_family_13in3.py          -> compact 960x680 output only
```

The original 7.5-inch renderer remains unchanged.

## Phase 1: synthetic analysis

Synthetic examples live in `tests/fixtures/wilma_messages.json`. They contain no
real family, school or account data.

Run the tests with the project's virtual-environment Python:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_wilma_reminders -v
```

The analyzer recognizes only a deliberately small set of high-confidence
patterns: explicit/relative dates, selected school events, supported school
subjects for exams, and a small number of concrete bring-with-you actions.
Informational newsletters without a concrete dated action are ignored.

The Wilma message subject can provide subject context for an otherwise generic
exam sentence. For example, a subject of `Matematiikka` plus `Tiistaina pidämme
kokeen` can become `Matematiikan koe`. If no supported subject can be identified,
the conservative fallback remains simply `Koe`.

## Phase 2: live Wilma adapter and private local state

`integrations/wilma_messages.py` has a small live adapter for the community-
observed Wilma web login/message endpoints. It deliberately stays behind the
same normalized `fetch_messages()` boundary because this is an unofficial
integration and Wilma may change the endpoint/login behaviour later.

No extra Python package is required by this adapter: it uses the project's
existing `requests` dependency plus Python's standard-library HTML parser.

Real credentials belong only in the local gitignored `config.yaml`. Example
shape (use your own values locally; never commit or paste them into chat):

```yaml
features:
  school_reminders: true

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

For an existing local configuration that already contains
`wilma_messages.provider` but predates the `school_reminders` feature flag, the
module is enabled automatically. Adding `features.school_reminders: false`
disables it explicitly.

An empty `child_ids` list means that the adapter tries to discover all children
linked to the parent account. `limit_per_child` only limits how many recent
message bodies are downloaded during one poll.

Test the live path directly with:

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
part of the content hash, so a rule-version change can force a safe reanalysis.
Older messages may fall outside the bounded download window, but a future
reminder already extracted from such a message stays in local state until its
date/end date has passed.

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

## Phase 3: dashboard integration

`school_reminders` is now part of the shared data-module pipeline. Before the
960x680 renderer is called, `main.py` compares active reminders with the already-
fetched family calendar using the conservative same-day title matcher.

The result is split into:

- `standalone`: reminders with no safe calendar match
- `enrichments`: reminders that match an existing calendar event

Standalone reminders are shown in a compact `KOULUSTA MUISTETTAVAA` area in the
existing reminders band. At most two nearest reminders are shown so the display
does not become a text wall.

A matched calendar item is **not** repeated in the school-reminder area. Instead,
its `remember` values are appended to the existing TÄNÄÄN/TULEVAT event line. For
example:

```text
KE 16.9.
  Luokan retki 08:15 - 13:00 · Eväät mukaan · Säänmukainen vaatetus
```

If the Wilma reminder only confirms an event already represented in the calendar
and contains no extra remember-items, nothing additional is rendered.

The 7.5-inch renderer API and layout are intentionally unchanged.

## Next iterations

The next work should be driven by real-message observations rather than expanding
rules speculatively. Useful candidates are:

1. review which real messages are missed or produce overly generic titles
2. add only high-confidence Finnish patterns backed by synthetic regression tests
3. consider an AI-backed analyzer behind the same structured contract after the
   rule-based MVP behaviour is understood

The source adapter, analyzer and renderer remain separate so each layer can be
replaced independently.

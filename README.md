# E-ink Dashboard

A home dashboard for a Waveshare 7.5" e-ink display (800×480), running on a Raspberry Pi. An inverted "departure board" band on top shows the clock, current weather and a leave-in countdown for the next transit connection; below it: daycare events, calendar, later departures, an electricity + waste stats line, and a 7-day forecast strip.

## Layout

```
┌────────────────────────────────────────────────────────┐
│  07:42  to 6.8.   ☁ 18° Pilvistä        lähtö 12 min   │  NOW band (inverted)
├──────────────────┬──────────────────┬──────────────────┤
│  PÄIVÄKOTI       │  KALENTERI       │  HSL             │
│  Daycare events  │  Calendar events │  Later departures│
├──────────────────┴──────────────────┴──────────────────┤
│  Sähkö 32.0 kWh eilen · Sekajäte 7 pv · Biojäte 26 pv  │  stats line
├────────────────────────────────────────────────────────┤
│  ENNUSTE  (7-day forecast as columns)                  │
└────────────────────────────────────────────────────────┘
```

The clock and the countdown live in the band's partial-refresh regions, so they tick every minute between full refreshes.

## Hardware

| Part | Model | Notes |
|---|---|---|
| Display | Waveshare 7.5" e-Paper HAT V2 (800×480) | Black/white |
| Computer | Raspberry Pi Zero 2 W (or any Pi with 40-pin GPIO) | Needs pre-soldered headers |
| Power | 5V micro-USB charger, ≥1A | Standard phone charger works |

> **Important:** The Raspberry Pi Zero 2 W is sold both with and without GPIO headers.
> The Waveshare HAT has a female connector and requires **male pins** on the Pi.
> Make sure to buy the **"with headers" (WH) version**, or solder a 2×20 male header yourself.

## Data sources

| Module | Source | Auth |
|---|---|---|
| Weather + forecast | [Open-Meteo](https://open-meteo.com/) | None |
| Calendar | Google Calendar iCal | Secret URL token |
| Waste | Manual schedule in config | None |
| Daycare | Espoo eVaka (`/api/citizen/auth/weak-login`) | Username + password |
| Transit | [HSL Digitransit v2 GraphQL](https://portal-api.digitransit.fi/) | API key |

## Development setup (macOS)

### 1. Clone and create virtualenv

```bash
git clone <repo>
cd eInk
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your credentials and location. The file contains passwords and API keys — do not commit it.

Key settings:

```yaml
location:
  latitude: 60.1699
  longitude: 24.9384
  name: "Helsinki"

hsl:
  api_key: "your-key-from-portal-api.digitransit.fi"
  to_name: "Pasila"
  to_lat: 60.1985
  to_lon: 24.9323
  min_walk_bus: 3       # minutes to nearest bus stop
  min_walk_rail: 15     # minutes to nearest train station

waste:
  collections:
    - type: "Sekajäte"
      interval_weeks: 2
      next_date: "2026-03-25"
    - type: "Biojäte"
      interval_weeks: 4
      next_date: "2026-03-16"
```

### 3. Google Calendar iCal link

In Google Calendar: *Calendar settings → "Private address in iCal format"*. Add the URL to `config.yaml`:

```yaml
calendars:
  - name: "Oma"
    ical_url: "https://calendar.google.com/calendar/ical/.../basic.ics"
```

### 4. HSL API key

Register at [portal-api.digitransit.fi](https://portal-api.digitransit.fi/) and create a subscription for the Routing API. Add the key to `config.yaml`.

### 5. Run

```bash
source venv/bin/activate

# Full run, open preview on macOS
python main.py --preview

# Force data refresh (skip cache)
python main.py --no-cache --preview

# Test a single module
python main.py --only weather
python main.py --only hsl --no-cache

# Partial-refresh just the cells listed in config.partial_updates (no API calls).
# On macOS the simulator overlays the patched regions onto output/dashboard.png.
python main.py --partial-only

# Force a true full refresh instead of the default fast refresh
python main.py --full-refresh
```

## Raspberry Pi deployment

### 1. Flash SD card

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/):
- OS: Raspberry Pi OS Lite (64-bit)
- Enable SSH, set username/password, configure WiFi (country: FI)

### 2. Connect display

Attach the Waveshare HAT to the 40-pin GPIO header with the Pi powered off.

### 3. Enable SPI

```bash
ssh -t USER@HOSTNAME "sudo raspi-config nonint do_spi 0"
```

### 4. Install system dependencies

```bash
ssh -t USER@HOSTNAME "sudo apt install -y git python3-venv python3-pip swig liblgpio-dev"
```

### 5. Sync project files from Mac

```bash
./sync.sh
```

Or manually:
```bash
rsync -av --exclude venv --exclude cache --exclude output --exclude .git \
  /path/to/eInk/ USER@HOSTNAME:~/eInk/
```

### 6. Set up virtualenv and install Python dependencies

```bash
ssh USER@HOSTNAME "cd ~/eInk && python3 -m venv venv && venv/bin/pip install -r requirements.txt"
```

The e-paper driver is `betterepd7in5` (on PyPI, pulled in by `requirements.txt`). It fixes the partial-update-after-sleep corruption the stock Waveshare driver exhibits and is significantly faster on the Pi Zero 2 W.

### 7. Create required directories

```bash
ssh USER@HOSTNAME "mkdir -p ~/eInk/cache ~/eInk/output"
```

### 8. Copy config

```bash
scp config.yaml USER@HOSTNAME:~/eInk/config.yaml
```

### 9. Test

```bash
ssh USER@HOSTNAME "cd ~/eInk && venv/bin/python main.py --no-cache"
```

### 10. Set up cron

The crontab is checked in at `cron/eink.crontab` and installed via `sync_cron.sh`. Three rhythms run on `flock`-protected mutually-exclusive minute slots so they can't collide on the SPI bus:

| Slot | Command | Purpose |
|---|---|---|
| Minutes 1–9, 11–19, …, 51–59 | `main.py --partial-only` | Partial-refresh cells in `config.partial_updates` (no API calls) |
| Minutes 10, 20, 30, 40, 50 | `main.py` | Fast refresh of the full dashboard |
| Minute 0 (every hour) + `@reboot` | `main.py --full-refresh` | True full refresh — clears ghosting, bootstraps partial baseline |

Edit `cron/eink.crontab` (update `juhani` to your username) then push:

```bash
./sync_cron.sh
```

The script preserves any other crontab entries on the Pi — it only replaces the block between `# >>> eink-managed >>>` markers.

### Sync changes from Mac

```bash
./sync.sh        # rsync project files (excludes venv, cache, output, .git)
./sync_cron.sh   # only when cron/eink.crontab changed
```

## Project structure

```
eInk/
├── main.py              # Entry point, CLI args, module orchestration
├── render.py            # Pillow-based image renderer (800×480, grayscale)
├── sync.sh              # rsync project files Mac → Pi
├── sync_cron.sh         # Push cron/eink.crontab to the Pi
├── config.yaml          # Your config (not committed)
├── config.example.yaml  # Template
├── cron/
│   └── eink.crontab     # Managed crontab block (installed via sync_cron.sh)
├── data/
│   ├── weather.py       # Open-Meteo (current + 7-day forecast)
│   ├── calendar.py      # iCal / Google Calendar
│   ├── electricity.py   # Caruna / pycaruna
│   ├── waste.py         # Manual waste schedule
│   ├── evaka.py         # Espoo daycare (eVaka)
│   └── hsl.py           # HSL Digitransit transit (incl. drop_past_departures filter)
├── display/
│   ├── simulator.py     # PNG output for macOS development
│   └── epaper.py        # Waveshare 7.5" V2 driver via betterepd7in5
├── fonts/               # Optional: place Inter-Regular.ttf + Inter-Bold.ttf here
├── cache/               # JSON cache files + cur_display.png partial baseline (auto-generated)
└── output/              # Output PNG (auto-generated, macOS only)
```

## Caching

Each module writes a JSON cache file under `cache/`. TTLs are configurable per module in `config.yaml`. Stale cache is used as a fallback when an API call fails — the dashboard always shows something even when offline.

```yaml
cache:
  ttl_minutes: 55           # weather, calendar
  hsl_ttl_minutes: 10       # real-time transit
  hsl_active_hours: [6, 22] # no HSL fetches outside these hours
  evaka_ttl_minutes: 1440   # daycare: once per day
  electricity_ttl_minutes: 720
```

## Partial updates

The cron's per-minute slot runs `main.py --partial-only`, which re-renders the dashboard from cache only (no API calls) and partial-refreshes the cells listed in config:

```yaml
partial_updates:
  clock: true   # NOW band clock+date — ticks every minute
  hsl: true     # NOW band leave-in countdown — recomputed every minute
```

Available cells are defined in `render.py` as `PARTIAL_CELLS`. Each entry is `{region, data_key, filter}` where `filter` is an optional `module:function` that mutates the cell's data before render — the HSL cell uses `data.hsl:drop_past_departures` to remove connections where the recomputed `minutes_until ≤ 0`. New partial-eligible cells need an `x`-aligned region (multiples of 8) and an entry in the registry.

If `partial_updates` is missing or empty, `--partial-only` is a no-op.

## Wilma AI summaries

The optional cloud analyzer extracts concise Finnish school reminders per child
from message subjects and bodies. Child and message IDs are attached locally.
Credentials and sender metadata are not sent to the AI service. Existing display
integration renders the reminders under `Koulusta muistettavaa`.

Configure in the gitignored `config.yaml`:

```yaml
wilma_ai:
  enabled: true
  model: "YOUR_RESPONSES_STRUCTURED_OUTPUTS_MODEL"
  api_key: "YOUR_OPENAI_API_KEY"
```

Alternatively supply `OPENAI_API_KEY` to the dashboard service environment.
Use a separately billed API key; do not commit it or paste it into chat.
Model output uses the Responses API strict JSON schema and `store: false`:
https://developers.openai.com/api/docs/guides/structured-outputs
This setting does not itself promise zero provider retention.

Unchanged messages reuse local analysis; changing the model invalidates their
analysis hash after the normal cache TTL (30 minutes by default). Request failures,
refusals, incomplete responses and malformed data preserve the existing stale
cache instead of overwriting it. No message bodies or API responses are logged.
Messages above 60,000 characters fail explicitly rather than being truncated.

Each reminder includes a verbatim evidence excerpt and original message ID.
Dates resolve against the message send date. Undated actions appear as `Tarkista:`
review tasks and remain visible until resolved in the source message or local
state; do not treat their displayed review date as an event date. AI interpretation
can still be wrong; consult the original Wilma message for confirmation.

With a key configured, validate from the project directory:

```bash
venv/bin/python wilma_reminders_check.py --no-cache
venv/bin/python -m unittest tests.test_wilma_ai tests.test_wilma_reminders
```

### Nightly Codex mode (no API key)

`wilma_nightly.py` fetches Wilma messages to private `cache/wilma_messages.json`,
then invokes the installed Codex CLI with saved ChatGPT login, read-only sandbox,
ephemeral session and a strict output schema. Changed messages are analyzed in
bounded batches. The job retains older future reminders. Only validated output
is atomically published as `cache/wilma_codex_summary.json`; failed runs retain
the last successful summary. State is in `cache/wilma_codex_state.json`.
The current snapshot and state contain family data and stay gitignored with
owner-only permissions. Codex output is not written to the system log.

Set `wilma_ai.provider: codex_file` and `features.school_reminders: true` locally.
In this mode the display only reads the summary file, never contacts Wilma or AI.
The header shows last successful update time and marks data stale after 36 hours.
Undated review tasks remain until the message changes or local state is resolved.

Installed schedule: daily at 12:00, 13:00, 14:00 and 15:00, host timezone Europe/Helsinki, using the
salamapi user's crontab. Run manually with:

```bash
cd /home/salamapi/eInk
venv/bin/python wilma_nightly.py
```

Check `cache/wilma_nightly.log` if the update time stops advancing. Renew Codex
ChatGPT login if required. Normal Codex plan usage limits apply. No API key is
needed. Disable by removing the marked cron block; the last summary stays visible.

### All school reminders on the tablet

Open `/school` or tap the dashboard's `Koulusta muistettavaa` area. You can also
swipe left from the monthly calendar, then right to return. The school page shows
all active reminders in Neve/Sera columns, with full text, dates and expandable
source excerpts. Undated review tasks are grouped separately without an invented
event date. On narrow screens columns stack and the page scrolls vertically.
The header reports the last successful update and warns when it is delayed.
`/school-reminders.json` reads only the locally saved summary; opening this page
never polls Wilma or invokes Codex. The dashboard still shows one compact row per
child. Reload an already-open tablet browser once after installation.

### Homework, exams and lesson notes

The school page groups records into `Läksyt ja kokeet`, `Merkinnät` and `Muut`,
with separate child columns inside each group. Wilma is polled every day at
12:00, 13:00, 14:00 and 15:00 in Europe/Helsinki; this replaces the 03:15 job.
The existing `wilma_nightly.py` filename is retained for compatibility. Each run
refreshes direct records and summarizes changed messages using Codex.

Direct records are stored privately in `cache/wilma_schoolwork.json`. Homework
from teaching group journals is shown for the last 14 days with its given date,
without inventing deadlines or completion status. Exams include future dates
and original scope descriptions. Notes include the last 28 days; duplicate
identical cells on the same day are collapsed. Notes are read from the history
view, not just unexplained absences. Raw records never go through the AI model.

A failed direct fetch preserves the previous snapshot and marks its status as
failed in `cache/wilma_schoolwork_status.json`. The page reports direct-fetch and
message-summary times separately, since AI failure must not hide fresh homework.
Install `beautifulsoup4` from requirements if not already available.

### Two-day recommendations

The first section of the school page contains exactly three short Finnish sentences
for each child, generated by Codex from saved homework, exams, recent notes and
message reminders. The visible period covers tomorrow and the following day.
The advice prioritizes preparation for the nearest exams and conditional checking
of homework, since completion and due dates are not known. Notes older than seven
days are excluded from advice inputs. The original records remain below.

Recommendations update after each successful scheduled refresh. A fingerprint
includes the current date and source contents, so unchanged records are reused
within a day and the two-day period is regenerated on a new day. A schema and
validation require both children, exactly three sentences each, and source IDs
belonging to the correct child. Results are atomically saved in
`cache/wilma_recommendations.json`; failures retain old advice with a delayed-update
warning and the original period. Generation uses the existing ChatGPT login.

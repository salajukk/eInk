# Perheen näyttö – development notes

Read [README.md](README.md) and [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) first. This repository is named `eInk` for historical reasons, but the active product is **a browser-based family dashboard served over the trusted home LAN**, not a physical e-paper display.

## Current deployment

- Development branch: **`main`**. The old `family-dashboard-v1` code was merged into `main` on 2026-11-15.
- Production hardware: Raspberry Pi 5 (2 GB), Raspberry Pi OS Lite 64-bit, always-on headless service.
- Display: reused Android tablet in kiosk mode; other devices on home Wi-Fi use the same HTTP URL.
- Server: `web_dashboard.py`, default `0.0.0.0:8080`, protected by the trusted LAN (no built-in login).
- Supervisor: `dashboard_supervisor.py` launched by `family-dashboard.service`, with 60-second Git checks and 30-second dashboard rendering by default.
- Raspberry Pi URL uses a router-reserved LAN IP, not a `.local` name.
- The deployed Pi may still be checking out `family-dashboard-v1` until its local branch is migrated. **Do not assume GitHub merge changes the Pi checkout**. Migration instructions: [AUTO_UPDATE.md](AUTO_UPDATE.md).

## Project structure

- `web_dashboard.py`: HTTP server, primary dashboard image, browser shell, monthly calendar and school view.
- `main.py`: feature switches, data orchestration, renderer selection and CLI diagnostics.
- `render_family_13in3.py`: 960 × 680 primary family dashboard renderer, reused as browser PNG despite the historical layout name.
- `data/`: weather, calendar, calendar_month, HSL, school, tasks, school reminders, and legacy optional sources.
- `integrations/`: Wilma source adapters.
- `analysis/`: school reminder and recommendation logic.
- `wilma_nightly.py`: scheduled Wilma schoolwork and summary refresh.
- `school_summary_page.py`: JSON payload for school view.
- `system_health.py`, `system_health_page.py`: read-only Raspberry Pi health collection and UI.
- `dashboard_supervisor.py`: fast-forward-only Git updates, service restart and process recovery.
- `config.example.yaml`: configuration template. Real `config.yaml` and `cache/` data are private and gitignored.
- `tests/`: unit tests.

`display/epaper*.py`, `render.py`, `render_family.py`, and the `requirements-pi-*.txt` files are retained legacy hardware paths, not part of the deployed kiosk system. Avoid reintroducing a physical e-ink requirement.

## Setup and common commands

~~~bash
git clone https://github.com/salajukk/eInk.git
cd eInk
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
cp config.example.yaml config.yaml
# set your local config.yaml values
venv/bin/python web_dashboard.py
# or run the supervisor:
venv/bin/python dashboard_supervisor.py
~~~

A Raspberry Pi service is boot-enabled through `family-dashboard.service`. Do not start a second web server on port 8080 while the service is running.

Diagnosis:

~~~bash
venv/bin/python main.py --only weather --no-cache
venv/bin/python main.py --only calendar --no-cache
venv/bin/python main.py --only hsl --no-cache
venv/bin/python -m unittest discover -s tests -v
systemctl status family-dashboard.service
journalctl -u family-dashboard.service -n 100 --no-pager
~~~

## Browser behavior

- Primary dashboard renders a 960 × 680 PNG to `output/dashboard.png`, visually fitted into the browser screen. The browser refreshes it without reloading the entire page.
- Swipe right from primary: system health. Swipe left: monthly calendar. Swipe left from monthly calendar: school reminders. Return gestures work in the opposite direction.
- Routes: `/`, `/dashboard.png`, `/calendar-month.json`, `/system`, `/system-health.json`, `/school`, `/school-reminders.json`, `/health`.
- Browser data refresh: generic weather/calendar caches capped at 5 min, HSL capped at 1 min; expired departure data is pruned on each image render.

## School and Wilma

- Wilma school timetable can come from private iCal feeds configured in `school_schedules`.
- Nightly job filename `wilma_nightly.py` is retained, but the current installed schedule is four daytime runs at 12:00, 13:00, 14:00, 15:00 Europe/Helsinki.
- School page may display AI-assisted summaries and short recommendations from local saved schoolwork and messages; always preserve source references and do not invent due dates or completion.
- A failure must not erase the last successful cache. Do not log message bodies, secret credentials or AI responses.
- Consult [WILMA_REMINDERS.md](WILMA_REMINDERS.md) and the tests for the precise data contracts.

## Safety and implementation rules

- Keep family data on the trusted LAN; never expose port 8080 directly to the internet.
- Keep iCal private URLs, Wilma credentials, Digitransit tokens, AI keys and cache records out of commits and chat.
- Prefer small code changes that preserve the kiosk view and do not require a physical display.
- Only update `main` for new development. The old feature branch is preserved temporarily for safe deployment migration.
- The supervisor accepts only fast-forward pulls and does **not** install new dependencies automatically.
- Test the relevant module(s) and verify the changed routes or rendering before deploying. Avoid gratuitous dashboard or service restarts.

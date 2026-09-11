# Family Dashboard

This branch keeps the original layouts available and adds a family-focused 13.3inch dashboard layout.

The currently deployed home display is an Android tablet served by an always-on Raspberry Pi 5. The **primary 960x680 family dashboard** still stays compatible with the possible future Waveshare 13.3inch black/white e-paper output, while the tablet browser may also provide optional interactive secondary views.

The primary dashboard remains one glanceable black/white screen with no required scrolling or touch interaction. Tablet/browser-only views may use gestures and scrolling as long as they stay separate from the shared renderer and do not break the existing e-paper or 7.5inch paths.

## Supported display configurations

### Current shared 960x680 dashboard / possible future 13.3inch target

Use the 13.3inch layout for the primary tablet dashboard:

```yaml
display:
  model: "waveshare_13in3k"
  width: 960
  height: 680
  rotation: 0
  layout: "family_13in3"
```

On a normal development computer this configuration still uses the simulator/output PNG. On the Raspberry Pi, `web_dashboard.py` deliberately bypasses display hardware for the Android/tablet deployment; later `main.py` can select the physical Waveshare 13.3inch e-Paper HAT (K) adapter if the panel is connected and tested.

### Original 7.5inch Waveshare V2

```yaml
display:
  model: "waveshare_7in5_v2"
  width: 800
  height: 480
  rotation: 0
  layout: "family"
```

The original upstream layout is still available with `display.layout: legacy`.

## 1. Local Windows/macOS/Linux development

The common requirements deliberately contain no Raspberry Pi display driver, so they also work on development machines:

```bash
python3 -m venv venv
pip install -r requirements.txt
```

On Windows PowerShell in this project, using the virtual environment Python directly is fine:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe main.py --no-cache
```

The simulator writes the rendered image to:

```text
output/dashboard.png
```

## 2. Android/tablet deployment

`web_dashboard.py` is the browser output path. Its primary view reuses the existing data modules and `family_13in3` renderer, writes the result to `output/dashboard.png`, and serves that PNG full-screen. It does not talk to e-paper hardware.

The tablet shell also has a separate interactive monthly calendar. This secondary view is browser-only: it is HTML/JavaScript around the shared dashboard rather than a change to `render_family_13in3.py`.

Usage on the tablet:

- primary view: the existing 960x680 family dashboard
- swipe **right**: open the monthly calendar
- swipe **left** from the month view: return to the primary dashboard
- scroll vertically in the month view
- use `‹` / `›` to move to the previous/next month

The month table shows one row per day and one column per configured `calendars:` entry. It uses `data/calendar_month.py` to fetch every occurrence in the selected month instead of the compact 20-event cache used by the primary dashboard. See `TABLET_MONTH_CALENDAR.md`.

The current home server is:

- Raspberry Pi 5, 2 GB RAM
- Raspberry Pi OS Lite 64-bit
- Kingston 64 GB microSD
- official Raspberry Pi 5 27 W USB-C power supply
- hostname `familydisplay`
- repository checkout on `family-dashboard-v1`
- `dashboard_supervisor.py` running as boot-enabled `family-dashboard.service`

The home router has a DHCP reservation for the Raspberry Pi so the Android tablet can use a stable LAN IP. `.local` name resolution was not reliable on the tablet, so do not depend on `familydisplay.local` for the permanent tablet URL.

The Raspberry-hosted deployment has been reboot-tested successfully: after restart the Pi rejoins Wi-Fi, `systemd` starts the supervisor, the supervisor starts `web_dashboard.py`, and the tablet receives a fresh dashboard without a Windows computer or open SSH session.

For manual testing, start the server on a computer or Pi that is on the same trusted home network as the Android tablet.

Windows PowerShell:

```powershell
.\venv\Scripts\python.exe web_dashboard.py
```

macOS/Linux/Raspberry Pi:

```bash
venv/bin/python web_dashboard.py
```

Defaults:

```text
HTTP port:       8080
Dashboard render: every 30 seconds
Listen address:  0.0.0.0 (home LAN)
```

The web server starts each session with one forced fresh primary-dashboard data fetch. After that it uses the normal module caches, but caps the generic calendar/weather-style cache at 5 minutes and the HSL cache at 1 minute. The same 5-minute generic cap is used for month-calendar requests.

Cached HSL departure boards are also aged on every 30-second render, so buses/trains whose departure time has already passed are removed even before the next Digitransit API refresh.

First verify on the server itself:

```text
http://localhost:8080
```

Then open the same page on the Android tablet using the server's reserved LAN IP and port 8080.

The primary dashboard still fits inside the tablet screen without scrolling and automatically reloads the rendered PNG. The monthly calendar intentionally scrolls vertically because an entire month with multiple calendar columns cannot remain legible in a single 960x680 frame.

Optional arguments:

```bash
python web_dashboard.py --port 8080 --refresh-seconds 30 --config config.yaml
```

For diagnostics, the server exposes:

```text
/health
/dashboard.png
/calendar-month.json?year=2026&month=9
```

Keep this server on the trusted home LAN. Do not expose or port-forward it to the public internet because both the rendered dashboard and the month endpoint can contain private family calendar information.

See `AUTO_UPDATE.md` for the supervisor and `systemd` deployment details.

## 3. Data-module tests

```bash
python main.py --only weather --no-cache
python main.py --only calendar --no-cache
python main.py --only hsl --no-cache
python main.py --only school --no-cache
python main.py --only tasks
python -m unittest tests.test_calendar_month -v
```

Use `--no-cache` when checking a calendar edit or troubleshooting a departure feed so the diagnostic shows the source data rather than an older cache entry.

## 4. Physical 13.3inch setup on the Raspberry Pi 5

The Raspberry Pi 5 is already installed and serving the tablet. If the physical e-paper phase is pursued, the next hardware step is to verify the Waveshare 13.3inch HAT (K) path specifically on this Pi 5.

Enable SPI first with Raspberry Pi configuration tools.

Then install the 13.3inch hardware dependencies inside the existing project virtual environment:

```bash
cd ~/eInk
venv/bin/pip install -r requirements-pi-13in3.txt
mkdir -p cache output
```

If setting up a fresh Pi from scratch, create the virtual environment first with `python3 -m venv venv`.

`requirements-pi-13in3.txt` installs the common dashboard dependencies plus the Waveshare vendor driver and Raspberry Pi SPI/GPIO dependencies. Because the final computer is a Raspberry Pi 5 rather than the earlier Pi 3 A+ plan, treat the real hardware smoke test as the compatibility gate for the driver/GPIO path.

Before connecting the full dashboard to the display, run the minimal hardware smoke test:

```bash
venv/bin/python test_display_13in3.py
```

If the bordered test page appears, SPI, the HAT, the Waveshare driver and the panel are working on the Pi 5.

Then test the real dashboard:

```bash
venv/bin/python main.py --no-cache --full-refresh
```

## 5. Partial refresh on the 13.3inch panel

Partial refresh is intentionally disabled for `waveshare_13in3k` for the first hardware version.

The Waveshare partial-update sequence expects the panel RAM to be primed with `display_Base()` in the same powered session. The dedicated e-paper path currently runs as short-lived processes, so blindly reusing the 7.5inch cross-process partial-refresh strategy would be risky. `main.py --partial-only` therefore safely skips a tick on the 13.3inch model instead of refreshing the panel incorrectly.

Use this configuration initially:

```yaml
partial_updates:
  clock: false
  hsl: false
```

The complete dashboard can still refresh normally every 10 minutes. True partial refresh can be enabled later after testing it on the physical 13.3inch panel.

## 6. Raspberry Pi setup for the old 7.5inch display

For the original 7.5inch V2 hardware use:

```bash
venv/bin/pip install -r requirements-pi-7in5.txt
```

That file installs `betterepd7in5` in addition to the common dependencies. The 7.5inch adapter continues to support partial refresh.

## 7. Dedicated e-paper deployment

This deployment path remains available for a possible physical-display phase.

Copy the deployment template and set the Raspberry Pi SSH target:

```bash
cp deploy.env.example deploy.env
```

Example:

```bash
PI_TARGET=youruser@familydisplay.local
```

If `.local` name resolution is unavailable on the machine running the sync, use the Pi's reserved LAN IP instead.

`deploy.env` and `config.yaml` are gitignored and must contain the real machine-specific settings and secrets only locally.

Sync the application with:

```bash
./sync.sh
```

When the physical display has been tested successfully, install the managed cron block with:

```bash
./sync_cron.sh
```

For the 13.3inch model the minute-level `--partial-only` cron invocations are currently skipped safely by the application. Full dashboard refreshes continue normally.

## Architecture

The core primary-dashboard flow remains shared:

```text
data/<feature>.py -> render_family_13in3.py -> 960x680 image
```

Tablet primary view:

```text
data modules -> render_family_13in3.py -> output/dashboard.png -> web_dashboard.py -> Android browser
```

Tablet monthly calendar:

```text
configured iCal feeds -> data/calendar_month.py -> /calendar-month.json -> web_dashboard.py HTML/JS
```

Possible future 13.3inch e-paper:

```text
data modules -> render_family_13in3.py -> display/epaper_13in3.py -> Waveshare panel
```

Family renderers:

```text
render_family.py          800x480 / 7.5inch
render_family_13in3.py    960x680 / primary tablet dashboard + 13.3inch K
```

Hardware/output adapters:

```text
web_dashboard.py          Android/browser output + tablet-only secondary views
display/epaper.py         Waveshare 7.5inch V2
display/epaper_13in3.py   Waveshare 13.3inch HAT (K)
display/simulator.py      development preview
```

`main.py` chooses the hardware adapter from `display.model` only when it is actually running on a Raspberry Pi. On a normal development computer it always uses the simulator. `web_dashboard.py` bypasses display hardware entirely and serves the shared rendered 960x680 image to the tablet browser, with optional browser-only views layered around it.

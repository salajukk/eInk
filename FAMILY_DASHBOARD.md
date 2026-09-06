# Family Dashboard

This branch keeps the original layouts available and adds a family-focused 13.3inch dashboard layout.

The long-term target is still a Waveshare 13.3inch black/white e-paper wall display, but the current MVP runs the **same 960x680 dashboard** on an existing Android tablet first. The tablet phase is used to validate whether an always-visible family dashboard is useful enough to justify the dedicated e-paper + Raspberry Pi hardware.

The Android MVP must remain e-paper-compatible: one glanceable screen, black/white presentation, no required scrolling, animations or touch interaction, and the same 960x680 renderer that will later be used for the 13.3inch panel.

## Supported display configurations

### Current MVP / future 13.3inch target

Use the 13.3inch layout during the Android test as well:

```yaml
display:
  model: "waveshare_13in3k"
  width: 960
  height: 680
  rotation: 0
  layout: "family_13in3"
```

On a normal development computer this configuration still uses the simulator/output PNG. On the future Raspberry Pi it selects the physical Waveshare 13.3inch e-Paper HAT (K) adapter.

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

## 2. Android tablet MVP

`web_dashboard.py` is the browser-friendly output path for the MVP. It reuses the existing data modules and `family_13in3` renderer, writes the result to `output/dashboard.png`, and serves that PNG as a simple full-screen web page. It does **not** duplicate the dashboard UI in HTML and does not talk to e-paper hardware.

Start it on a computer that is on the same trusted home network as the Android tablet.

Windows PowerShell:

```powershell
.\venv\Scripts\python.exe web_dashboard.py
```

macOS/Linux:

```bash
venv/bin/python web_dashboard.py
```

Defaults:

```text
HTTP port:       8080
Dashboard render: every 60 seconds
Listen address:  0.0.0.0 (home LAN)
```

First verify on the computer itself:

```text
http://localhost:8080
```

Then open the same page on the Android tablet using the computer's LAN IP, for example:

```text
http://192.168.1.10:8080
```

The exact LAN IP depends on the computer/network. On Windows, `ipconfig` can be used to find the IPv4 address. If Windows Firewall asks for permission, allow the server on the **private/home network only**.

The browser page fits the 960x680 dashboard inside the available tablet screen without scrolling and automatically reloads the rendered PNG. Keep the tablet screen awake and use browser full-screen/kiosk presentation as practical during the kitchen test.

Optional arguments:

```bash
python web_dashboard.py --port 8080 --refresh-seconds 60 --config config.yaml
```

For a one-off diagnostic, the server also exposes:

```text
/health
/dashboard.png
```

Keep this server on the trusted home LAN. Do not expose or port-forward it to the public internet because the rendered dashboard can contain private family calendar information.

## 3. Data-module tests

```bash
python main.py --only weather --no-cache
python main.py --only calendar --no-cache
python main.py --only hsl --no-cache
python main.py --only school --no-cache
python main.py --only tasks
```

## 4. Raspberry Pi setup for the future 13.3inch display

This phase is intentionally after the Android MVP decision gate.

Enable SPI first with Raspberry Pi configuration tools.

Then install the 13.3inch hardware dependencies inside the project virtual environment:

```bash
cd ~/eInk
python3 -m venv venv
venv/bin/pip install -r requirements-pi-13in3.txt
mkdir -p cache output
```

`requirements-pi-13in3.txt` installs the common dashboard dependencies plus the Waveshare vendor driver and Raspberry Pi SPI/GPIO dependencies.

Before connecting the full dashboard to the display, run the minimal hardware smoke test:

```bash
venv/bin/python test_display_13in3.py
```

If the bordered test page appears, SPI, the HAT, the Waveshare driver and the panel are working.

Then test the real dashboard:

```bash
venv/bin/python main.py --no-cache --full-refresh
```

## 5. Partial refresh on the 13.3inch panel

Partial refresh is intentionally disabled for `waveshare_13in3k` for the first hardware version.

The Waveshare partial-update sequence expects the panel RAM to be primed with `display_Base()` in the same powered session. The dashboard currently runs as short-lived cron processes, so blindly reusing the 7.5inch cross-process partial-refresh strategy would be risky. `main.py --partial-only` therefore safely skips a tick on the 13.3inch model instead of refreshing the panel incorrectly.

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

This deployment path remains available for the later hardware phase.

Copy the deployment template and set the Raspberry Pi SSH target:

```bash
cp deploy.env.example deploy.env
```

Example:

```bash
PI_TARGET=youruser@familydisplay.local
```

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

The data/rendering flow stays intentionally shared between outputs:

```text
data/<feature>.py -> renderer -> PNG / display output
```

Android MVP:

```text
data modules -> render_family_13in3.py -> output/dashboard.png -> web_dashboard.py -> Android browser
```

Future 13.3inch e-paper:

```text
data modules -> render_family_13in3.py -> display/epaper_13in3.py -> Waveshare panel
```

Family renderers:

```text
render_family.py          800x480 / 7.5inch
render_family_13in3.py    960x680 / Android MVP + 13.3inch K
```

Hardware/output adapters:

```text
web_dashboard.py          Android/browser MVP output
display/epaper.py         Waveshare 7.5inch V2
display/epaper_13in3.py   Waveshare 13.3inch HAT (K)
display/simulator.py      development preview
```

`main.py` chooses the hardware adapter from `display.model` only when it is actually running on a Raspberry Pi. On a normal development computer it always uses the simulator. `web_dashboard.py` bypasses display hardware entirely and serves the same rendered 960x680 image to the tablet browser.

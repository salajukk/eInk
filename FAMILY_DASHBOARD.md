# Family Dashboard

This branch keeps the original layouts available and adds a family-focused 13.3inch wall-dashboard layout.

## Supported display configurations

### Recommended: Waveshare 13.3inch e-Paper HAT (K)

```yaml
display:
  model: "waveshare_13in3k"
  width: 960
  height: 680
  rotation: 0
  layout: "family_13in3"
```

Target hardware is the black/white Waveshare 13.3inch e-Paper HAT (K), 960x680.

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

## 2. Data-module tests

```bash
python main.py --only weather --no-cache
python main.py --only calendar --no-cache
python main.py --only hsl --no-cache
python main.py --only school --no-cache
python main.py --only tasks
```

## 3. Raspberry Pi setup for the 13.3inch display

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

## 4. Partial refresh on the 13.3inch panel

Partial refresh is intentionally disabled for `waveshare_13in3k` for the first hardware version.

The Waveshare partial-update sequence expects the panel RAM to be primed with `display_Base()` in the same powered session. The dashboard currently runs as short-lived cron processes, so blindly reusing the 7.5inch cross-process partial-refresh strategy would be risky. `main.py --partial-only` therefore safely skips a tick on the 13.3inch model instead of refreshing the panel incorrectly.

Use this configuration initially:

```yaml
partial_updates:
  clock: false
  hsl: false
```

The complete dashboard can still refresh normally every 10 minutes. True partial refresh can be enabled later after testing it on the physical 13.3inch panel.

## 5. Raspberry Pi setup for the old 7.5inch display

For the original 7.5inch V2 hardware use:

```bash
venv/bin/pip install -r requirements-pi-7in5.txt
```

That file installs `betterepd7in5` in addition to the common dependencies. The 7.5inch adapter continues to support partial refresh.

## 6. Deployment

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

When the display has been tested successfully, install the managed cron block with:

```bash
./sync_cron.sh
```

For the 13.3inch model the minute-level `--partial-only` cron invocations are currently skipped safely by the application. Full dashboard refreshes continue normally.

## Architecture

The data flow stays intentionally simple:

```text
data/<feature>.py -> main.py -> renderer -> display adapter
```

Family renderers:

```text
render_family.py          800x480 / 7.5inch
render_family_13in3.py    960x680 / 13.3inch K
```

Hardware adapters:

```text
display/epaper.py         Waveshare 7.5inch V2
display/epaper_13in3.py   Waveshare 13.3inch HAT (K)
display/simulator.py      development preview
```

`main.py` chooses the hardware adapter from `display.model` only when it is actually running on a Raspberry Pi. On a normal development computer it always uses the simulator.

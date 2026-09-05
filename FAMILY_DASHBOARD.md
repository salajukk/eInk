# Family Dashboard V1

This fork keeps the original dashboard available as `display.layout: legacy` and adds a family-focused layout as `display.layout: family`.

## V1 layout

```text
┌────────────────────────────────────────────────────────┐
│  09:42  la 5.9.      weather        PERHEEN NÄYTTÖ    │
├───────────────────────────┬────────────────────────────┤
│ TÄNÄÄN                    │ TULEVAT                    │
│ 10:00 · Perhe             │ su 6.9. · Perhe           │
│ Koripallo                 │ Synttärit                  │
│ ...                       │ ...                        │
├───────────────────────────┴────────────────────────────┤
│ MUISTETTAVAA  □ item  □ item  □ item                  │
├────────────────────────────────────────────────────────┤
│ ENNUSTE  ma  ti  ke  to  pe  la  su                   │
└────────────────────────────────────────────────────────┘
```

If HSL is enabled, the next departure countdown replaces the title on the right side of the top band.

## 1. Local setup

```bash
git checkout family-dashboard-v1
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

Edit `config.yaml`. For the first test, only these modules need to be enabled:

```yaml
features:
  weather: true
  calendar: true
  tasks: true
  hsl: false
  waste: false
  electricity: false
  evaka: false

display:
  width: 800
  height: 480
  layout: family
```

Add your home coordinates, private iCal links and temporary reminders.

## 2. Test individual data modules

```bash
python main.py --only weather --no-cache
python main.py --only calendar --no-cache
python main.py --only tasks
```

## 3. Render a preview

On macOS:

```bash
python main.py --no-cache --preview
```

On other development systems, run without `--preview` and inspect `output/dashboard.png`.

Do layout work in `render_family.py`. The original `render.py` is intentionally left intact so upstream changes are easier to merge.

## 4. Raspberry Pi deployment

Copy the deployment template and set your SSH target:

```bash
cp deploy.env.example deploy.env
```

Example `deploy.env`:

```bash
PI_TARGET=youruser@familydisplay.local
```

`deploy.env` is gitignored.

Then sync files:

```bash
./sync.sh
```

On the Pi, create the virtual environment and install dependencies:

```bash
cd ~/eInk
python3 -m venv venv
venv/bin/pip install -r requirements.txt
mkdir -p cache output
```

Copy your real `config.yaml` to the Pi and test a full refresh:

```bash
venv/bin/python main.py --no-cache --full-refresh
```

When the display works correctly, install the managed cron block:

```bash
./sync_cron.sh
```

The crontab uses `$HOME/eInk`, so it no longer depends on a hard-coded Raspberry Pi username.

## Architecture for new features

Keep the existing flow:

```text
data/<feature>.py -> main.py -> render_family.py -> display
```

A new data module should expose:

```python
def fetch(config: dict, use_cache: bool = True) -> dict:
    ...
```

Then add its name to `MODULES` in `main.py`, add a `features.<name>` switch in the config, and pass the returned dictionary to the renderer.

Good next candidates are school lunch, hobby schedules, birthdays and a real task provider such as Google Tasks or Todoist.

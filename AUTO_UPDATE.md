# Automatic GitHub updates

`dashboard_supervisor.py` is the preferred way to run the Android/tablet MVP server when you want repository changes to deploy automatically.

The same supervisor is designed to work first on the Windows PC and later on Raspberry Pi.

## What it does

The supervisor:

1. starts `web_dashboard.py`
2. checks `origin/family-dashboard-v1` every 60 seconds
3. if a newer commit exists, stops the dashboard briefly
4. runs a fast-forward-only Git pull
5. restarts the dashboard using the new code
6. keeps watching for later changes

This means a change committed to `family-dashboard-v1` from another computer, phone workflow or ChatGPT/GitHub session can normally appear on the kitchen dashboard within about one minute without manually running `git pull` on the server.

## Windows MVP server

First update the checkout once manually:

```powershell
cd C:\Users\salam\Documents\eInk
git pull
```

Then run the supervisor instead of starting `web_dashboard.py` directly:

```powershell
.\venv\Scripts\python.exe dashboard_supervisor.py
```

Leave this PowerShell window running. The dashboard stays available at the same address as before:

```text
http://localhost:8080
```

The tablet continues to use the Windows computer's LAN address, for example:

```text
http://192.168.1.10:8080
```

Default timing:

```text
GitHub update check: every 60 seconds
Dashboard render:    every 30 seconds
```

You can change the Git check interval, but the supervisor intentionally refuses intervals below 30 seconds:

```powershell
.\venv\Scripts\python.exe dashboard_supervisor.py --check-seconds 60
```

## Safety behaviour

Automatic deployment deliberately has a few safeguards:

- it follows only `family-dashboard-v1` by default
- it never switches branches automatically
- it only accepts fast-forward Git updates
- if tracked files have local edits, it skips the pull rather than overwriting them
- `config.yaml`, credentials and caches remain local and gitignored
- if the dashboard process crashes, the supervisor restarts it
- if `dashboard_supervisor.py` itself changes, it attempts to reload itself after pulling

Do not use the server checkout for ad-hoc edits while automatic updates are enabled. Make code changes through Git and let the server act as a deployment checkout.

## Python dependency changes

The supervisor updates repository files but does **not** automatically install new Python packages. If a commit changes a `requirements*.txt` file, the supervisor prints a warning.

Normal layout, rendering and data-logic changes should deploy without manual package installation. If a future change adds a new dependency, install the updated requirements manually once.

## Later Raspberry Pi deployment

The same command will work from the repository on Raspberry Pi:

```bash
venv/bin/python dashboard_supervisor.py
```

When the Raspberry Pi becomes the permanent tablet-dashboard server, configure the supervisor to start automatically at boot with `systemd`. That boot-service setup should be done on the real Pi after its operating system, network and repository checkout have been tested.

The future physical e-paper output remains a separate deployment mode; this supervisor currently manages the browser/tablet `web_dashboard.py` server.

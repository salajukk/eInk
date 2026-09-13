# Automatic GitHub updates

`dashboard_supervisor.py` is the preferred way to run the Android/tablet MVP server when you want repository changes to deploy automatically.

The permanent MVP server is now the Raspberry Pi 5. The earlier Windows-server path is still useful for development or fallback testing, but normal kitchen-tablet operation no longer depends on a Windows computer.

## What it does

The supervisor:

1. starts `web_dashboard.py`
2. checks `origin/family-dashboard-v1` every 60 seconds
3. if a newer commit exists, stops the dashboard briefly
4. runs a fast-forward-only Git pull
5. restarts the web dashboard using the new code
6. keeps watching for later changes

This means a change committed to `family-dashboard-v1` from another computer, phone workflow or ChatGPT/GitHub session can normally appear on the kitchen dashboard within about one minute without manually running `git pull` on the server.

## Current Raspberry Pi MVP server

The current home deployment has been verified on:

- Raspberry Pi 5, 2 GB RAM
- Raspberry Pi OS Lite 64-bit
- repository at `~/eInk` on branch `family-dashboard-v1`
- project virtual environment at `~/eInk/venv`
- local gitignored `config.yaml`
- hostname `familydisplay`
- DHCP reservation on the home router so the tablet can use a stable LAN address

Run the supervisor manually for a first test:

```bash
cd ~/eInk
venv/bin/python dashboard_supervisor.py
```

Once the manual run works, install it as a `systemd` service. The tested service shape is:

```ini
[Unit]
Description=Family Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_PI_USER
WorkingDirectory=/home/YOUR_PI_USER/eInk
ExecStart=/home/YOUR_PI_USER/eInk/venv/bin/python /home/YOUR_PI_USER/eInk/dashboard_supervisor.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Save that as:

```text
/etc/systemd/system/family-dashboard.service
```

Replace `YOUR_PI_USER` with the actual local Raspberry Pi account, then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now family-dashboard.service
```

Check status with:

```bash
systemctl status family-dashboard.service
```

The expected state is:

```text
Active: active (running)
```

The current Raspberry deployment has been reboot-tested successfully: after reboot it reconnects to Wi-Fi, starts `family-dashboard.service`, starts the supervisor and serves a fresh dashboard to the Android tablet without an SSH session or Windows server.

The tablet should use the Pi's reserved LAN IP and port 8080. `.local` name resolution was not reliable on the Android tablet, so the home router's DHCP reservation is the preferred way to keep the address stable.

## Windows development/fallback server

For a temporary Windows run, first update the checkout once manually:

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

The tablet can use the Windows computer's LAN address while this fallback server is running.

Default timing on both Windows and Raspberry Pi:

```text
GitHub update check: every 60 seconds
Dashboard render:    every 30 seconds
```

You can change the Git check interval, but the supervisor intentionally refuses intervals below 30 seconds:

```bash
venv/bin/python dashboard_supervisor.py --check-seconds 60
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

Normal layout, rendering, documentation and data-logic changes should deploy without manual package installation. If a future change adds a new dependency, install the updated requirements manually once on the Raspberry Pi.

## Physical e-paper deployment remains separate

The supervisor currently manages the browser/tablet `web_dashboard.py` server. The future physical Waveshare 13.3inch output remains a separate deployment mode and must be tested independently on the Raspberry Pi 5 before the current draft PR is considered complete.

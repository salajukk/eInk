# Raspberry Pi system health

`system_health.py` is a read-only health monitor for the Raspberry Pi that serves the family dashboard. It does not restart services or change system configuration.

The current implementation has two layers:

```text
system_health.py       -> measurements + status + local 24 h history
system_health_page.py  -> read-only /system web UI helpers
web_dashboard.py       -> /system and /system-health.json routes
```

Push notifications and a background systemd timer are intentionally still deferred.

## Manual check on the Raspberry Pi

From the repository directory:

```bash
venv/bin/python system_health.py
```

Expected shape:

```text
SYSTEM HEALTH: OK

Temperature        48.3 °C
CPU load (1m)      0.03
RAM used           12.4 %
Disk used          8.0 %
Uptime             3 h 12 min
Throttling         0x0
Dashboard service  active
Web dashboard      OK
Internet           OK
Last check         2026-09-12T08:30:00+03:00
```

The same run atomically updates:

```text
cache/health/health.json
cache/health/history.json
```

The existing `cache/*` gitignore rule keeps this runtime data out of GitHub.

For raw JSON on stdout:

```bash
venv/bin/python system_health.py --json
```

## /system page

The tablet web server exposes a separate diagnostic page:

```text
http://<raspberry-ip>:8080/system
```

The page shows the latest values for temperature, CPU load, RAM, disk, uptime,
throttling, the dashboard service, the local web dashboard and internet connectivity.
It also draws small 24-hour charts for temperature, RAM and disk usage using only
browser-native HTML/JavaScript; no external chart library is required.

Opening `/system` triggers a fresh read-only health check. While the page stays open,
it refreshes every five minutes. Checks inside the same five-minute interval replace
the newest history point instead of growing the history file unnecessarily.

The page links back to the normal family dashboard. It is intentionally separate
from the swipeable primary/month-calendar UI because system diagnostics are an
occasional maintenance view rather than daily family content.

## History behaviour

`cache/health/history.json` contains only compact chart fields:

- check timestamp
- overall status
- CPU temperature
- one-minute CPU load
- RAM usage percentage
- disk usage percentage

Issue messages and other verbose snapshot data are not duplicated into history.
Points older than 24 hours are removed whenever history is written. The target
sampling interval is five minutes, so a full day will later contain at most roughly
288 useful points when the background timer is enabled.

At this stage history grows when either:

1. `system_health.py` is run manually, or
2. `/system` is open and performs its five-minute refresh.

There is deliberately **no always-on health timer yet**. That is the next phase.

## Measurements

The monitor collects:

- Raspberry Pi CPU temperature, primarily from Linux thermal sysfs with `vcgencmd measure_temp` as fallback
- `vcgencmd get_throttled`
- one-minute system load average
- RAM usage based on `/proc/meminfo` and `MemAvailable`
- root filesystem usage
- uptime from `/proc/uptime`
- `systemctl is-active family-dashboard.service`
- local dashboard HTTP health at `http://127.0.0.1:8080/health`
- outbound internet connectivity using a small HTTP 204 connectivity check

The local web check deliberately uses `127.0.0.1` so it answers the question “is the dashboard web server itself responding?” separately from router/Wi-Fi/internet problems.

## Status rules

Overall status is one of `ok`, `warning` or `critical`.

Initial thresholds:

- CPU temperature >= 70 °C: warning
- CPU temperature >= 80 °C: critical
- throttling flags other than `0x0`: warning
- disk usage >= 80%: warning (less than 20% free)
- disk usage >= 95%: critical
- RAM usage >= 90%: warning
- RAM usage >= 97%: critical
- `family-dashboard.service` not active: critical
- local dashboard health endpoint not responding: critical
- internet connectivity check failing: warning

If a Pi-specific temperature or throttling metric cannot be read, the snapshot is a warning because monitoring is incomplete.

The latest JSON snapshot includes an `issues` list with stable issue codes so the later notification layer can detect state transitions without parsing display text.

## Tests

Run:

```bash
venv/bin/python -m unittest tests.test_system_health -v
```

The unit tests mock service/network/system collectors and do not require Raspberry Pi hardware. They also cover 24-hour retention, five-minute history coalescing and the standalone system page.

## Next phase

The next controlled step is to add a small systemd timer that runs the existing
`system_health.py` every five minutes even when `/system` is closed. No new data
format is required.

After that has run reliably, push notifications can be added with state-change
suppression: one alert when an issue starts and one recovery notification when it
clears, rather than one notification every five minutes.

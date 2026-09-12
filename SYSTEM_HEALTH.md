# Raspberry Pi system health – Phase 1

`system_health.py` is a read-only health snapshot for the Raspberry Pi that serves the family dashboard.

Phase 1 deliberately does **not** restart services, create a `/system` web page, keep history or send notifications. It only measures the current state, evaluates simple thresholds, prints a summary and writes the latest structured snapshot to a local cache file.

## Run on the Raspberry Pi

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
```

The existing `cache/*` gitignore rule keeps this runtime data out of GitHub.

For raw JSON on stdout:

```bash
venv/bin/python system_health.py --json
```

## Measurements

The first version collects:

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

## Initial status rules

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

The JSON includes an `issues` list with stable issue codes so a later notification layer can detect state transitions without parsing display text.

## Tests

Run:

```bash
venv/bin/python -m unittest tests.test_system_health -v
```

The unit tests mock service/network/system collectors and do not require Raspberry Pi hardware.

## Next phases

Phase 2 can add:

1. periodic snapshots and a bounded 24-hour history
2. a read-only `/system` page in `web_dashboard.py`
3. simple temperature/RAM/disk charts
4. a systemd timer for collection

Phase 3 can add push notifications, preferably with state-change suppression so one outage produces one alert and one recovery notification rather than repeated messages.

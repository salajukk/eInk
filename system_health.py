#!/usr/bin/env python3
"""Read-only health snapshot for the Family Display Raspberry Pi.

Phase 1 intentionally does not restart services or send notifications. It only
collects local system metrics, evaluates simple thresholds, prints a human-
readable summary and stores the latest structured snapshot under cache/health/.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib import error, request

OUTPUT_PATH = Path("cache/health/health.json")
DASHBOARD_SERVICE = "family-dashboard.service"
LOCAL_HEALTH_URL = "http://127.0.0.1:8080/health"
INTERNET_CHECK_URL = "https://connectivitycheck.gstatic.com/generate_204"

TEMP_WARNING_C = 70.0
TEMP_CRITICAL_C = 80.0
DISK_WARNING_PERCENT = 80.0  # less than 20% free
DISK_CRITICAL_PERCENT = 95.0
MEMORY_WARNING_PERCENT = 90.0
MEMORY_CRITICAL_PERCENT = 97.0


def _run(command: list[str], timeout: float = 3.0) -> tuple[int | None, str]:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return completed.returncode, completed.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, ""


def _is_raspberry_pi() -> bool:
    for model_path in (
        Path("/proc/device-tree/model"),
        Path("/sys/firmware/devicetree/base/model"),
    ):
        try:
            if model_path.exists() and "raspberry pi" in model_path.read_text(errors="ignore").casefold():
                return True
        except OSError:
            pass
    return False


def _temperature_c() -> float | None:
    path = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        raw = path.read_text().strip()
        return round(float(raw) / 1000.0, 1)
    except (OSError, ValueError):
        pass

    code, output = _run(["vcgencmd", "measure_temp"])
    if code == 0 and "=" in output:
        try:
            return round(float(output.split("=", 1)[1].split("'", 1)[0]), 1)
        except (ValueError, IndexError):
            pass
    return None


def _throttled() -> str | None:
    code, output = _run(["vcgencmd", "get_throttled"])
    if code != 0 or "=" not in output:
        return None
    value = output.split("=", 1)[1].strip().lower()
    return value or None


def _cpu_load_1m() -> float | None:
    try:
        return round(os.getloadavg()[0], 2)
    except (AttributeError, OSError):
        return None


def _memory_percent_from_text(text: str) -> float | None:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        token = raw.strip().split()[0] if raw.strip() else ""
        try:
            values[key] = int(token)
        except ValueError:
            continue

    total = values.get("MemTotal")
    available = values.get("MemAvailable")
    if not total or available is None:
        return None
    used = max(0, total - available)
    return round(used / total * 100.0, 1)


def _memory_percent() -> float | None:
    try:
        return _memory_percent_from_text(Path("/proc/meminfo").read_text())
    except OSError:
        return None


def _disk_percent(path: str = "/") -> float | None:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return None
    if usage.total <= 0:
        return None
    return round(usage.used / usage.total * 100.0, 1)


def _uptime_seconds() -> int | None:
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        return None


def _service_status(service: str = DASHBOARD_SERVICE) -> str:
    code, output = _run(["systemctl", "is-active", service])
    if output:
        return output.splitlines()[0].strip().lower()
    return "unknown" if code is None else "inactive"


def _http_ok(url: str, timeout: float = 3.0, expected: set[int] | None = None) -> bool:
    expected = expected or {200}
    try:
        with request.urlopen(url, timeout=timeout) as response:
            return response.status in expected
    except (error.URLError, OSError, ValueError):
        return False


def _format_uptime(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours or days:
        parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    return " ".join(parts)


def evaluate_status(snapshot: dict) -> tuple[str, list[dict]]:
    """Return overall status plus machine-readable issues."""
    issues: list[dict] = []

    def add(severity: str, code: str, message: str) -> None:
        issues.append({"severity": severity, "code": code, "message": message})

    temperature = snapshot.get("temperature_c")
    if isinstance(temperature, (int, float)):
        if temperature >= TEMP_CRITICAL_C:
            add("critical", "temperature", f"CPU temperature is {temperature:.1f} °C")
        elif temperature >= TEMP_WARNING_C:
            add("warning", "temperature", f"CPU temperature is {temperature:.1f} °C")
    elif snapshot.get("raspberry_pi"):
        add("warning", "temperature_unavailable", "CPU temperature is unavailable")

    throttled = snapshot.get("throttled")
    if throttled not in (None, "0x0"):
        add("warning", "throttled", f"Raspberry Pi throttling flags: {throttled}")
    elif throttled is None and snapshot.get("raspberry_pi"):
        add("warning", "throttled_unavailable", "Throttling status is unavailable")

    memory = snapshot.get("memory_percent")
    if isinstance(memory, (int, float)):
        if memory >= MEMORY_CRITICAL_PERCENT:
            add("critical", "memory", f"RAM usage is {memory:.1f}%")
        elif memory >= MEMORY_WARNING_PERCENT:
            add("warning", "memory", f"RAM usage is {memory:.1f}%")

    disk = snapshot.get("disk_percent")
    if isinstance(disk, (int, float)):
        if disk >= DISK_CRITICAL_PERCENT:
            add("critical", "disk", f"Disk usage is {disk:.1f}%")
        elif disk >= DISK_WARNING_PERCENT:
            add("warning", "disk", f"Disk usage is {disk:.1f}%")

    if snapshot.get("dashboard_service") != "active":
        add("critical", "dashboard_service", "family-dashboard.service is not active")

    if snapshot.get("web_dashboard") != "ok":
        add("critical", "web_dashboard", "Local dashboard health endpoint is not responding")

    if snapshot.get("internet") != "ok":
        add("warning", "internet", "Internet connectivity check failed")

    severities = {issue["severity"] for issue in issues}
    if "critical" in severities:
        return "critical", issues
    if "warning" in severities:
        return "warning", issues
    return "ok", issues


def collect_snapshot() -> dict:
    snapshot = {
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "hostname": platform.node(),
        "raspberry_pi": _is_raspberry_pi(),
        "temperature_c": _temperature_c(),
        "throttled": _throttled(),
        "cpu_load_1m": _cpu_load_1m(),
        "memory_percent": _memory_percent(),
        "disk_percent": _disk_percent(),
        "uptime_seconds": _uptime_seconds(),
        "dashboard_service": _service_status(),
        "web_dashboard": "ok" if _http_ok(LOCAL_HEALTH_URL, expected={200}) else "error",
        "internet": "ok" if _http_ok(INTERNET_CHECK_URL, expected={200, 204}) else "error",
    }
    status, issues = evaluate_status(snapshot)
    snapshot["status"] = status
    snapshot["issues"] = issues
    return snapshot


def write_snapshot(snapshot: dict, path: Path = OUTPUT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def _value(value, suffix: str = "") -> str:
    return "unknown" if value is None else f"{value}{suffix}"


def format_summary(snapshot: dict) -> str:
    status = str(snapshot.get("status") or "unknown").upper()
    lines = [f"SYSTEM HEALTH: {status}", ""]
    rows = [
        ("Temperature", _value(snapshot.get("temperature_c"), " °C")),
        ("CPU load (1m)", _value(snapshot.get("cpu_load_1m"))),
        ("RAM used", _value(snapshot.get("memory_percent"), " %")),
        ("Disk used", _value(snapshot.get("disk_percent"), " %")),
        ("Uptime", _format_uptime(snapshot.get("uptime_seconds"))),
        ("Throttling", snapshot.get("throttled") or "unknown"),
        ("Dashboard service", snapshot.get("dashboard_service") or "unknown"),
        ("Web dashboard", str(snapshot.get("web_dashboard") or "unknown").upper()),
        ("Internet", str(snapshot.get("internet") or "unknown").upper()),
        ("Last check", str(snapshot.get("checked_at") or "")),
    ]
    width = max(len(label) for label, _ in rows)
    lines.extend(f"{label:<{width}}  {value}" for label, value in rows)

    issues = snapshot.get("issues") or []
    if issues:
        lines.extend(["", "Issues:"])
        for issue in issues:
            lines.append(f"- {str(issue.get('severity', '')).upper()}: {issue.get('message', '')}")
    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description="Read-only Raspberry Pi health check")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the JSON snapshot instead of the human-readable summary",
    )
    parser.add_argument(
        "--output",
        default=str(OUTPUT_PATH),
        help=f"Snapshot path (default: {OUTPUT_PATH})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    snapshot = collect_snapshot()
    write_snapshot(snapshot, Path(args.output))
    if args.json:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
    else:
        print(format_summary(snapshot))


if __name__ == "__main__":
    main()

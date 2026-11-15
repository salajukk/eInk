import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import system_health
import system_health_page


class SystemHealthTests(unittest.TestCase):
    def _healthy(self):
        return {
            "raspberry_pi": True,
            "temperature_c": 48.3,
            "throttled": "0x0",
            "cpu_load_1m": 0.03,
            "memory_percent": 12.4,
            "disk_percent": 8.0,
            "uptime_seconds": 11520,
            "dashboard_service": "active",
            "web_dashboard": "ok",
            "internet": "ok",
        }

    def _history_snapshot(self, when: datetime, temperature: float = 48.3):
        return {
            "checked_at": when.isoformat(timespec="seconds"),
            "status": "ok",
            "temperature_c": temperature,
            "cpu_load_1m": 0.03,
            "memory_percent": 12.4,
            "disk_percent": 8.0,
            "issues": [{"severity": "warning", "message": "not duplicated in history"}],
        }

    def test_memory_parser_uses_mem_available(self):
        text = """MemTotal:       1000 kB\nMemFree:         100 kB\nMemAvailable:    750 kB\n"""
        self.assertEqual(system_health._memory_percent_from_text(text), 25.0)

    def test_healthy_snapshot_is_ok(self):
        status, issues = system_health.evaluate_status(self._healthy())
        self.assertEqual(status, "ok")
        self.assertEqual(issues, [])

    def test_temperature_and_disk_thresholds(self):
        warning = self._healthy()
        warning["temperature_c"] = 70.0
        warning["disk_percent"] = 80.0
        status, issues = system_health.evaluate_status(warning)
        self.assertEqual(status, "warning")
        self.assertEqual({item["code"] for item in issues}, {"temperature", "disk"})

        critical = self._healthy()
        critical["temperature_c"] = 80.0
        status, issues = system_health.evaluate_status(critical)
        self.assertEqual(status, "critical")
        self.assertIn("temperature", {item["code"] for item in issues})

    def test_service_and_web_failures_are_critical_but_internet_is_warning(self):
        internet = self._healthy()
        internet["internet"] = "error"
        self.assertEqual(system_health.evaluate_status(internet)[0], "warning")

        broken = self._healthy()
        broken["dashboard_service"] = "inactive"
        broken["web_dashboard"] = "error"
        status, issues = system_health.evaluate_status(broken)
        self.assertEqual(status, "critical")
        self.assertEqual(
            {item["code"] for item in issues},
            {"dashboard_service", "web_dashboard"},
        )

    def test_collect_snapshot_combines_collectors_and_status(self):
        with patch.object(system_health, "_is_raspberry_pi", return_value=True), patch.object(
            system_health, "_temperature_c", return_value=51.2
        ), patch.object(system_health, "_throttled", return_value="0x0"), patch.object(
            system_health, "_cpu_load_1m", return_value=0.11
        ), patch.object(system_health, "_memory_percent", return_value=22.0), patch.object(
            system_health, "_disk_percent", return_value=9.0
        ), patch.object(system_health, "_uptime_seconds", return_value=3600), patch.object(
            system_health, "_service_status", return_value="active"
        ), patch.object(system_health, "_http_ok", side_effect=[True, True]):
            snapshot = system_health.collect_snapshot()

        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(snapshot["temperature_c"], 51.2)
        self.assertEqual(snapshot["dashboard_service"], "active")
        self.assertEqual(snapshot["web_dashboard"], "ok")
        self.assertEqual(snapshot["internet"], "ok")

    def test_write_snapshot_is_valid_json(self):
        snapshot = {"status": "ok", "temperature_c": 48.3}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "health" / "health.json"
            system_health.write_snapshot(snapshot, path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), snapshot)
            self.assertFalse(path.with_name(path.name + ".tmp").exists())

    def test_history_drops_points_older_than_24_hours(self):
        now = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
        old = self._history_snapshot(now - timedelta(hours=25), 44.0)
        recent = self._history_snapshot(now - timedelta(hours=1), 46.0)
        current = self._history_snapshot(now, 48.0)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text(
                json.dumps({"points": [old, recent]}),
                encoding="utf-8",
            )
            points = system_health.record_history(current, path, now=now)
            stored = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual([point["temperature_c"] for point in points], [46.0, 48.0])
        self.assertEqual(len(stored["points"]), 2)
        self.assertEqual(stored["retention_hours"], 24)
        self.assertNotIn("issues", stored["points"][-1])

    def test_history_replaces_newest_point_inside_five_minutes(self):
        now = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
        previous = self._history_snapshot(now - timedelta(seconds=60), 45.0)
        current = self._history_snapshot(now, 49.0)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history.json"
            path.write_text(json.dumps({"points": [previous]}), encoding="utf-8")
            points = system_health.record_history(current, path, now=now)

        self.assertEqual(len(points), 1)
        self.assertEqual(points[0]["temperature_c"], 49.0)

    def test_system_page_has_no_external_dependencies(self):
        html = system_health_page.system_page().decode("utf-8")
        self.assertIn("Raspberry Pi Health", html)
        self.assertIn("/system-health.json", html)
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link rel=", html)


if __name__ == "__main__":
    unittest.main()

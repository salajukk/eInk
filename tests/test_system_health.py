import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import system_health


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


if __name__ == "__main__":
    unittest.main()

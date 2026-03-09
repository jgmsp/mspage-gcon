from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

from mspage_gcon.config import load_pod_ranges
from mspage_gcon.pipeline import (
    build_departures,
    build_ops_payload,
    normalize_gate,
    render_finance_text,
    should_fetch_now,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "airlabs_msp_sample.json"
ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.rows = payload["response"]
        self.pods = load_pod_ranges(ROOT / "config" / "pods.json")

    def test_normalize_gate_only_accepts_gates(self) -> None:
        self.assertEqual(normalize_gate("G8"), 8)
        self.assertEqual(normalize_gate("Gate G22"), 22)
        self.assertIsNone(normalize_gate("C17"))
        self.assertIsNone(normalize_gate("22"))

    def test_build_departures_filters_and_dedupes(self) -> None:
        departures = build_departures(self.rows, self.pods)

        self.assertEqual(len(departures), 3)
        self.assertEqual([item.gate_label for item in departures], ["G8", "G22", "G18"])
        self.assertEqual([item.flight_display for item in departures], ["2607", "942", "1062"])
        self.assertEqual([item.time_display_ops for item in departures], ["1834", "1840", "2005"])

    def test_pod_assignment_uses_config_ranges(self) -> None:
        departures = build_departures(self.rows, self.pods)
        gate_to_pod = {item.gate_number: item.pod_id for item in departures}

        self.assertEqual(gate_to_pod[8], "pod-2")
        self.assertEqual(gate_to_pod[22], "pod-5")
        self.assertEqual(gate_to_pod[18], "pod-5")

    def test_finance_text_snapshot(self) -> None:
        departures = build_departures(self.rows, self.pods)
        rendered = render_finance_text(departures)

        expected = (
            "Flight | Gate | Time\n"
            "2607   | 8    | 6:34\n"
            "942    | 22   | 6:40\n"
            "1062   | 18   | 8:05\n"
        )
        self.assertEqual(rendered, expected)

    def test_ops_payload_contains_metadata(self) -> None:
        departures = build_departures(self.rows, self.pods)
        generated_at = datetime(2026, 3, 9, 12, 0, tzinfo=ZoneInfo("UTC"))

        payload = build_ops_payload(departures, self.pods, generated_at=generated_at)

        self.assertEqual(payload["airport"], "MSP")
        self.assertEqual(payload["concourse"], "G")
        self.assertEqual(payload["generatedAt"], "2026-03-09T12:00:00Z")
        self.assertEqual(len(payload["pods"]), 5)
        self.assertEqual(payload["departures"][0]["destination"], "SLC")

    def test_schedule_hours_are_checked_in_chicago_time(self) -> None:
        now = datetime(2026, 3, 9, 4, 5, tzinfo=ZoneInfo("America/Chicago"))
        self.assertTrue(should_fetch_now({4, 13}, now=now))
        self.assertFalse(should_fetch_now({13}, now=now))

    def test_pages_shell_exists(self) -> None:
        index_html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        app_js = (ROOT / "docs" / "app.js").read_text(encoding="utf-8")

        self.assertIn("Concourse G Operations Board", index_html)
        self.assertIn("pod-filters", index_html)
        self.assertIn("loadSnapshot", app_js)


if __name__ == "__main__":
    unittest.main()

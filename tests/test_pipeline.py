from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo

from mspage_gcon.config import load_pod_ranges
from mspage_gcon.msp import (
    extract_ajax_markup,
    parse_departure_rows,
    parse_departure_time,
    parse_destination,
    parse_flight_number,
)
from mspage_gcon.pipeline import (
    build_departures,
    build_departures_from_now,
    build_ops_payload,
    normalize_gate,
    render_finance_text,
    should_fetch_now,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "msp_delta_ajax.json"
ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        commands = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.markup = extract_ajax_markup(commands)
        self.now = datetime(2026, 3, 9, 9, 15, tzinfo=ZoneInfo("America/Chicago"))
        self.rows = parse_departure_rows(self.markup, now=self.now)
        self.pods = load_pod_ranges(ROOT / "config" / "pods.json")

    def test_normalize_gate_accepts_t1g_and_g_formats(self) -> None:
        self.assertEqual(normalize_gate("T1G8"), 8)
        self.assertEqual(normalize_gate("G22"), 22)
        self.assertIsNone(normalize_gate("T1A4"))
        self.assertIsNone(normalize_gate("22"))

    def test_parse_departure_time_reads_msp_display_string(self) -> None:
        parsed = parse_departure_time("Mar 09 — 10:24 a.m.", now=self.now)

        self.assertEqual(parsed, datetime(2026, 3, 9, 10, 24, tzinfo=ZoneInfo("America/Chicago")))

    def test_parse_helpers_extract_destination_and_flight_number(self) -> None:
        self.assertEqual(parse_destination("Los Cabos (SJD)"), "SJD")
        self.assertEqual(parse_flight_number("DeltaDL 1826"), "1826")
        self.assertIsNone(parse_flight_number("UnitedUA 1220"))

    def test_parse_departure_rows_filters_non_t1g_scope(self) -> None:
        self.assertEqual(len(self.rows), 4)
        self.assertEqual([row["dep_gate"] for row in self.rows], ["T1G9", "T1G22", "T1G5", "T1G18"])
        self.assertEqual([row["arr_iata"] for row in self.rows], ["SJD", "PHX", "SEA", "SAT"])
        self.assertEqual([row["flight_number"] for row in self.rows], ["1826", "2208", "1476", "889"])

    def test_build_departures_preserves_sorted_t1g_rows(self) -> None:
        departures = build_departures(self.rows, self.pods)

        self.assertEqual(len(departures), 4)
        self.assertEqual([item.gate_label for item in departures], ["G9", "G22", "G5", "G18"])
        self.assertEqual([item.flight_display for item in departures], ["1826", "2208", "1476", "889"])
        self.assertEqual([item.time_display_ops for item in departures], ["1000", "1000", "1024", "1105"])

    def test_pod_assignment_uses_config_ranges(self) -> None:
        departures = build_departures(self.rows, self.pods)
        gate_to_pod = {item.gate_number: item.pod_id for item in departures}

        self.assertEqual(gate_to_pod[5], "pod-1")
        self.assertEqual(gate_to_pod[9], "pod-1")
        self.assertEqual(gate_to_pod[18], "pod-5")
        self.assertEqual(gate_to_pod[22], "pod-5")

    def test_finance_text_snapshot(self) -> None:
        departures = build_departures(self.rows, self.pods)
        rendered = render_finance_text(departures)

        expected = (
            "Flight | Gate | Time\n"
            "1826   | 9    | 10:00\n"
            "2208   | 22   | 10:00\n"
            "1476   | 5    | 10:24\n"
            "889    | 18   | 11:05\n"
        )
        self.assertEqual(rendered, expected)

    def test_build_departures_from_now_filters_past_etd(self) -> None:
        now = datetime(2026, 3, 9, 10, 1, tzinfo=ZoneInfo("America/Chicago"))
        departures = build_departures_from_now(self.rows, self.pods, now=now)

        numbers = [item.flight_display for item in departures]
        self.assertEqual(numbers, ["1476", "889"])

    def test_ops_payload_contains_metadata_without_status(self) -> None:
        departures = build_departures(self.rows, self.pods)
        generated_at = datetime(2026, 3, 9, 12, 0, tzinfo=ZoneInfo("UTC"))

        payload = build_ops_payload(departures, self.pods, generated_at=generated_at)

        self.assertEqual(payload["airport"], "MSP")
        self.assertEqual(payload["concourse"], "G")
        self.assertEqual(payload["generatedAt"], "2026-03-09T12:00:00Z")
        self.assertEqual(len(payload["pods"]), 3)
        self.assertEqual(payload["departures"][0]["destination"], "SJD")
        self.assertNotIn("status", payload["departures"][0])

    def test_schedule_hours_are_checked_in_chicago_time(self) -> None:
        now = datetime(2026, 3, 9, 4, 5, tzinfo=ZoneInfo("America/Chicago"))
        self.assertTrue(should_fetch_now({4, 13}, now=now))
        self.assertFalse(should_fetch_now({13}, now=now))

    def test_pages_shell_exists(self) -> None:
        index_html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        app_js = (ROOT / "docs" / "app.js").read_text(encoding="utf-8")
        anime_js = (ROOT / "docs" / "vendor" / "anime.iife.min.js").read_text(encoding="utf-8")

        self.assertIn("Concourse G", index_html)
        self.assertIn("pod-filters", index_html)
        self.assertIn("theme-cycle", index_html)
        self.assertIn("Board filters", index_html)
        self.assertIn("vendor/anime.iife.min.js", index_html)
        self.assertIn("window.anime", app_js)
        self.assertIn("anime.js - IIFE", anime_js)


if __name__ == "__main__":
    unittest.main()

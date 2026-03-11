from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zoneinfo import ZoneInfo

from mspage_gcon.config import load_pod_ranges
from mspage_gcon.msp import (
    extract_ajax_markup,
    has_next_page,
    is_suspicious_parse,
    parse_departure_rows,
    parse_departure_rows_with_diagnostics,
    parse_departure_time,
    parse_destination,
    parse_flight_number,
    parse_status,
)
from mspage_gcon.pipeline import (
    FinanceEntry,
    build_departures,
    build_departures_from_now,
    build_finance_entries,
    build_ops_payload,
    normalize_gate,
    render_finance_text,
    should_fetch_now,
    summarize_finance_entries,
    write_outputs,
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

    def test_parse_helpers_extract_destination_flight_number_and_status(self) -> None:
        self.assertEqual(parse_destination("Los Cabos (SJD)"), "SJD")
        self.assertEqual(parse_flight_number("DeltaDL 1826"), "1826")
        self.assertEqual(parse_status("boarding"), "Boarding")
        self.assertEqual(parse_status("On Time"), "On Time")
        self.assertIsNone(parse_flight_number("UnitedUA 1220"))

    def test_has_next_page_detects_pagination_links(self) -> None:
        self.assertTrue(has_next_page('<a href="?flight_type=departures&amp;text=&amp;page=1">Next</a>', 0))
        self.assertFalse(has_next_page('<a href="?flight_type=departures&amp;text=&amp;page=2">Current</a>', 2))

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
        rendered = render_finance_text(build_finance_entries(departures, day=self.now))

        expected = (
            "Flight | Gate | Time\n"
            "1826   | 9    | 10:00\n"
            "2208   | 22   | 10:00\n"
            "1476   | 5    | 10:24\n"
            "889    | 18   | 11:05\n"
            "\n"
            "Total flights: 4\n"
            "AM flights: 4\n"
            "PM flights: 0\n"
        )
        self.assertEqual(rendered, expected)

    def test_build_departures_from_now_filters_past_etd(self) -> None:
        now = datetime(2026, 3, 9, 10, 1, tzinfo=ZoneInfo("America/Chicago"))
        departures = build_departures_from_now(self.rows, self.pods, now=now)

        numbers = [item.flight_display for item in departures]
        self.assertEqual(numbers, ["1476", "889"])

    def test_ops_payload_contains_metadata_with_optional_status(self) -> None:
        rows = list(self.rows)
        rows[0] = {**rows[0], "status": "Boarding"}
        departures = build_departures(rows, self.pods)
        generated_at = datetime(2026, 3, 9, 12, 0, tzinfo=ZoneInfo("UTC"))

        payload = build_ops_payload(departures, self.pods, generated_at=generated_at)

        self.assertEqual(payload["airport"], "MSP")
        self.assertEqual(payload["concourse"], "G")
        self.assertEqual(payload["generatedAt"], "2026-03-09T12:00:00Z")
        self.assertEqual(len(payload["pods"]), 3)
        self.assertEqual(payload["departures"][0]["destination"], "SJD")
        self.assertEqual(payload["departures"][0]["status"], "Boarding")
        self.assertNotIn("status", payload["departures"][1])

    def test_schedule_hours_are_checked_in_chicago_time(self) -> None:
        now = datetime(2026, 3, 9, 5, 5, tzinfo=ZoneInfo("America/Chicago"))
        self.assertTrue(should_fetch_now({5, 13}, now=now))
        self.assertFalse(should_fetch_now({13}, now=now))

    def test_finance_summary_excludes_pre430_from_subtotals(self) -> None:
        chicago = ZoneInfo("America/Chicago")
        entries = [
            FinanceEntry("1001", 1, "03:45", int(datetime(2026, 3, 9, 3, 45, tzinfo=chicago).timestamp())),
            FinanceEntry("1002", 2, "05:10", int(datetime(2026, 3, 9, 5, 10, tzinfo=chicago).timestamp())),
            FinanceEntry("1003", 3, "13:05", int(datetime(2026, 3, 9, 13, 5, tzinfo=chicago).timestamp())),
        ]

        self.assertEqual(summarize_finance_entries(entries), {"total": 3, "am": 1, "pm": 1})

    def test_write_outputs_replaces_finance_snapshot_on_next_report_run(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            first_departures = build_departures(self.rows[:2], self.pods)
            second_departures = build_departures(self.rows[2:], self.pods)

            write_outputs(
                output_dir=output_dir,
                departures=first_departures,
                pods=self.pods,
                generated_at=datetime(2026, 3, 9, 14, 0, tzinfo=ZoneInfo("UTC")),
            )
            write_outputs(
                output_dir=output_dir,
                departures=second_departures,
                pods=self.pods,
                generated_at=datetime(2026, 3, 9, 20, 0, tzinfo=ZoneInfo("UTC")),
            )

            finance_text = (output_dir / "finance.txt").read_text(encoding="utf-8")
            self.assertNotIn("1826   | 9    | 10:00", finance_text)
            self.assertNotIn("2208   | 22   | 10:00", finance_text)
            self.assertIn("1476   | 5    | 10:24", finance_text)
            self.assertIn("889    | 18   | 11:05", finance_text)
            self.assertIn("Total flights: 2", finance_text)
            self.assertIn("AM flights: 2", finance_text)
            self.assertIn("PM flights: 0", finance_text)

    def test_write_outputs_resets_finance_log_on_new_chicago_day(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            first_departures = build_departures(self.rows, self.pods)
            next_day_rows = [
                {
                    "dep_gate": "T1G9",
                    "dep_time": "2026-03-10 10:00",
                    "dep_time_ts": int(datetime(2026, 3, 10, 10, 0, tzinfo=ZoneInfo("America/Chicago")).timestamp()),
                    "arr_iata": "SJD",
                    "flight_iata": "DL1826",
                    "flight_number": "1826",
                }
            ]
            next_day_departure = build_departures(next_day_rows, self.pods)

            write_outputs(
                output_dir=output_dir,
                departures=first_departures,
                pods=self.pods,
                generated_at=datetime(2026, 3, 9, 20, 0, tzinfo=ZoneInfo("UTC")),
            )
            write_outputs(
                output_dir=output_dir,
                departures=next_day_departure,
                pods=self.pods,
                generated_at=datetime(2026, 3, 10, 14, 0, tzinfo=ZoneInfo("UTC")),
            )

            finance_text = (output_dir / "finance.txt").read_text(encoding="utf-8")
            self.assertIn("1826   | 9    | 10:00", finance_text)
            self.assertNotIn("2208   | 22   | 10:00", finance_text)
            self.assertIn("Total flights: 1", finance_text)

    def test_write_outputs_can_skip_finance_updates_for_hourly_ops_refresh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            departures = build_departures(self.rows[:2], self.pods)

            write_outputs(
                output_dir=output_dir,
                departures=departures,
                pods=self.pods,
                generated_at=datetime(2026, 3, 9, 14, 0, tzinfo=ZoneInfo("UTC")),
            )
            original_finance = (output_dir / "finance.txt").read_text(encoding="utf-8")

            write_outputs(
                output_dir=output_dir,
                departures=build_departures(self.rows[2:], self.pods),
                pods=self.pods,
                generated_at=datetime(2026, 3, 9, 15, 0, tzinfo=ZoneInfo("UTC")),
                update_finance=False,
            )

            self.assertEqual((output_dir / "finance.txt").read_text(encoding="utf-8"), original_finance)

    def test_write_outputs_can_clear_finance_at_six_pm(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            departures = build_departures(self.rows, self.pods)

            write_outputs(
                output_dir=output_dir,
                departures=departures,
                pods=self.pods,
                generated_at=datetime(2026, 3, 9, 13, 0, tzinfo=ZoneInfo("UTC")),
            )
            write_outputs(
                output_dir=output_dir,
                departures=departures,
                pods=self.pods,
                generated_at=datetime(2026, 3, 9, 23, 0, tzinfo=ZoneInfo("UTC")),
                update_finance=False,
                clear_finance=True,
            )

            finance_text = (output_dir / "finance.txt").read_text(encoding="utf-8")
            self.assertEqual(
                finance_text,
                "Flight | Gate | Time\n\nTotal flights: 0\nAM flights: 0\nPM flights: 0\n",
            )

    def test_status_parsing_is_optional_and_non_blocking(self) -> None:
        markup = (
            "<table><tbody>"
            "<tr>"
            '<td class="views-field views-field-scheduled-time">Mar 09 — 9:55 p.m.</td>'
            '<td class="views-field views-field-city-airport">Sioux Falls (FSD)</td>'
            '<td class="views-field views-field-airline views-field-name">DeltaDL 1694</td>'
            '<td class="flight-search-results__status views-field views-field-flight-status-1">Boarding</td>'
            '<td class="views-field views-field-terminal-1 views-field-gate-1">T1G1</td>'
            "</tr>"
            "</tbody></table>"
        )

        rows, diagnostics = parse_departure_rows_with_diagnostics(markup, now=self.now)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "Boarding")
        self.assertEqual(diagnostics.status_rows, 1)

    def test_suspicious_parse_is_detected(self) -> None:
        markup = (
            "<table><tbody>"
            "<tr>"
            '<td class="views-field views-field-airline views-field-name">DeltaDL 1694</td>'
            '<td class="views-field views-field-terminal-1 views-field-gate-1">T1G1</td>'
            "</tr>"
            "</tbody></table>"
        )

        _, diagnostics = parse_departure_rows_with_diagnostics(markup, now=self.now)
        self.assertTrue(is_suspicious_parse(diagnostics))

    def test_pages_shell_exists(self) -> None:
        index_html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        app_js = (ROOT / "docs" / "app.js").read_text(encoding="utf-8")
        anime_js = (ROOT / "docs" / "vendor" / "anime.iife.min.js").read_text(encoding="utf-8")

        self.assertIn("Concourse G", index_html)
        self.assertIn("pod-filters", index_html)
        self.assertIn("theme-cycle", index_html)
        self.assertIn("Board filters", index_html)
        self.assertIn("finance-plain", index_html)
        self.assertIn("vendor/anime.iife.min.js", index_html)
        self.assertIn("window.anime", app_js)
        self.assertIn("./finance.txt", app_js)
        self.assertIn("renderFinancePlainText", app_js)
        self.assertIn("anime.js - IIFE", anime_js)


if __name__ == "__main__":
    unittest.main()

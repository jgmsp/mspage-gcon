from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from mspage_gcon.config import load_pod_ranges
from mspage_gcon.__main__ import main, resolve_finance_actions
from mspage_gcon.msp import (
    FetchDiagnostics,
    MSP_QUERY_PARAMS,
    ParseDiagnostics,
    extract_ajax_markup,
    fetch_delta_departures_source,
    fetch_flights_page,
    has_next_page,
    is_invalid_departures_response,
    is_suspicious_parse,
    parse_departure_rows,
    parse_departure_rows_with_diagnostics,
    parse_departure_time,
    parse_destination,
    parse_flight_number,
    parse_status,
)
from mspage_gcon.pipeline import (
    DIAGNOSTICS_FILENAME,
    FinanceEntry,
    build_departures,
    build_departures_from_now,
    build_finance_entries,
    build_ops_payload,
    normalize_gate,
    read_last_success_at,
    render_finance_text,
    should_fetch_now,
    write_failure_diagnostics,
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

    def test_fetch_flights_page_requests_delta_departures_filter(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"<html></html>"

        with patch("mspage_gcon.msp.urlopen", return_value=response) as mock_urlopen:
            fetch_flights_page(page=0)

        request = mock_urlopen.call_args.args[0]
        self.assertIn("flight_type=departure", request.full_url)
        self.assertIn("airline_code=DL", request.full_url)
        self.assertEqual(MSP_QUERY_PARAMS["airline_code"], "DL")

    def test_invalid_departures_response_detects_drupal_validation_error(self) -> None:
        markup = """
        <div class="messages messages--error">
          The submitted value <em class="placeholder">departures</em> in the
          <em class="placeholder">flight_type</em> element is not allowed.
        </div>
        <div class="view-empty"><p>Sorry, no results match your search.</p></div>
        """

        self.assertTrue(is_invalid_departures_response(markup))

    def test_fetch_delta_departures_source_falls_back_to_next_contract(self) -> None:
        invalid_markup = """
        <div class="messages messages--error">
          The submitted value <em class="placeholder">departures</em> in the
          <em class="placeholder">flight_type</em> element is not allowed.
        </div>
        <div class="view-empty"><p>Sorry, no results match your search.</p></div>
        """
        valid_markup = (
            "<table><tbody>"
            "<tr>"
            '<td class="views-field views-field-scheduled-time">Mar 09 — 10:24 a.m.</td>'
            '<td class="views-field views-field-city-airport">Los Cabos (SJD)</td>'
            '<td class="views-field views-field-airline views-field-name">DeltaDL 1826</td>'
            '<td class="flight-search-results__status views-field views-field-flight-status-1">Boarding</td>'
            '<td class="views-field views-field-terminal-1 views-field-gate-1">T1G9</td>'
            "</tr>"
            "</tbody></table>"
        )
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = [invalid_markup.encode("utf-8"), valid_markup.encode("utf-8")]

        with patch("mspage_gcon.msp.urlopen", return_value=response) as mock_urlopen:
            markup, diagnostics = fetch_delta_departures_source()

        self.assertIn("T1G9", markup)
        self.assertEqual(diagnostics, FetchDiagnostics(source="page", pages_fetched=1))
        requested_urls = [call.args[0].full_url for call in mock_urlopen.call_args_list]
        self.assertIn("flight_type=departure", requested_urls[0])
        self.assertIn("flight_type=departures", requested_urls[1])

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
        self.assertEqual(gate_to_pod[9], "pod-2")
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
        self.assertEqual(len(payload["pods"]), 5)
        self.assertEqual(payload["departures"][0]["destination"], "SJD")
        self.assertEqual(payload["departures"][0]["status"], "Boarding")
        self.assertNotIn("status", payload["departures"][1])

    def test_schedule_hours_are_checked_in_chicago_time(self) -> None:
        now = datetime(2026, 3, 9, 5, 5, tzinfo=ZoneInfo("America/Chicago"))
        self.assertTrue(should_fetch_now({5, 12}, now=now))
        self.assertFalse(should_fetch_now({12}, now=now))

    def test_finance_actions_freeze_outside_snapshot_windows(self) -> None:
        morning = datetime(2026, 3, 9, 5, 5, tzinfo=ZoneInfo("America/Chicago"))
        midday = datetime(2026, 3, 9, 12, 15, tzinfo=ZoneInfo("America/Chicago"))
        off_window = datetime(2026, 3, 9, 10, 5, tzinfo=ZoneInfo("America/Chicago"))
        clear_window = datetime(2026, 3, 9, 18, 0, tzinfo=ZoneInfo("America/Chicago"))

        self.assertEqual(resolve_finance_actions(now=morning), (True, False))
        self.assertEqual(resolve_finance_actions(now=midday), (True, False))
        self.assertEqual(resolve_finance_actions(now=off_window), (False, False))
        self.assertEqual(resolve_finance_actions(now=clear_window), (False, True))

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
            self.assertNotIn("Total flights:", finance_text)
            self.assertNotIn("AM flights:", finance_text)
            self.assertNotIn("PM flights:", finance_text)

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
            self.assertNotIn("Total flights:", finance_text)

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
            diagnostics = json.loads((output_dir / DIAGNOSTICS_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(diagnostics["status"], "healthy")
            self.assertEqual(diagnostics["lastSuccessAt"], "2026-03-09T15:00:00Z")

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
            self.assertEqual(finance_text, "Flight | Gate | Time\n")

    def test_repo_finance_snapshots_do_not_include_deprecated_summary_counts(self) -> None:
        finance_paths = [ROOT / "docs" / "finance.txt", *sorted((ROOT / "docs" / "fixtures").glob("**/finance.txt"))]

        for path in finance_paths:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("Total flights:", text, path.as_posix())
            self.assertNotIn("AM flights:", text, path.as_posix())
            self.assertNotIn("PM flights:", text, path.as_posix())

    def test_local_review_assets_are_ignored_and_not_documented_for_release(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("docs/fixtures/", gitignore)
        self.assertIn("docs/preview-checkpoints.md", gitignore)
        self.assertIn("docs/review-checklist.html", gitignore)
        self.assertNotIn("preview-checkpoints", readme)
        self.assertNotIn("docs/fixtures/", readme)

    def test_write_outputs_publish_diagnostics_and_last_success(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            departures = build_departures(self.rows, self.pods)
            generated_at = datetime(2026, 3, 9, 17, 0, tzinfo=ZoneInfo("UTC"))

            write_outputs(
                output_dir=output_dir,
                departures=departures,
                pods=self.pods,
                generated_at=generated_at,
            )

            diagnostics = json.loads((output_dir / DIAGNOSTICS_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(diagnostics["status"], "healthy")
            self.assertEqual(diagnostics["lastSuccessAt"], "2026-03-09T17:00:00Z")
            self.assertEqual(read_last_success_at(output_dir), datetime(2026, 3, 9, 12, 0, tzinfo=ZoneInfo("America/Chicago")))

    def test_degraded_diagnostics_reuse_last_known_success(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_outputs(
                output_dir=output_dir,
                departures=build_departures(self.rows[:2], self.pods),
                pods=self.pods,
                generated_at=datetime(2026, 3, 9, 14, 0, tzinfo=ZoneInfo("UTC")),
            )
            diagnostics = write_failure_diagnostics(
                output_dir,
                attempted_at=datetime(2026, 3, 9, 15, 0, tzinfo=ZoneInfo("UTC")),
            )

            self.assertEqual(diagnostics.status, "degraded")
            payload = json.loads((output_dir / DIAGNOSTICS_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "degraded")
            self.assertEqual(payload["lastSuccessAt"], "2026-03-09T14:00:00Z")

    def test_failure_diagnostics_become_stale_after_threshold(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_outputs(
                output_dir=output_dir,
                departures=build_departures(self.rows[:2], self.pods),
                pods=self.pods,
                generated_at=datetime(2026, 3, 9, 14, 0, tzinfo=ZoneInfo("UTC")),
            )

            diagnostics = write_failure_diagnostics(
                output_dir,
                attempted_at=datetime(2026, 3, 9, 17, 1, tzinfo=ZoneInfo("UTC")),
            )

            self.assertEqual(diagnostics.status, "stale")
            payload = json.loads((output_dir / DIAGNOSTICS_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "stale")

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

    def test_suspicious_parse_detects_partial_degradation(self) -> None:
        diagnostics = ParseDiagnostics(
            source="page",
            pages_fetched=4,
            rows_seen=40,
            candidate_rows=12,
            rows_kept=4,
            status_rows=0,
        )

        self.assertTrue(is_suspicious_parse(diagnostics))

    def test_main_reuses_last_good_snapshot_when_refresh_fails(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            departures = build_departures(self.rows, self.pods)
            original_generated_at = datetime.now(ZoneInfo("UTC")).replace(minute=0, second=0, microsecond=0)
            write_outputs(
                output_dir=output_dir,
                departures=departures,
                pods=self.pods,
                generated_at=original_generated_at,
            )
            original_ops = (output_dir / "ops.json").read_text(encoding="utf-8")
            original_finance = (output_dir / "finance.txt").read_text(encoding="utf-8")

            with patch("mspage_gcon.__main__.fetch_delta_departures_source", side_effect=RuntimeError("boom")):
                exit_code = main(
                    [
                        "--output-dir",
                        str(output_dir),
                        "--pod-config",
                        str(ROOT / "config" / "pods.json"),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual((output_dir / "ops.json").read_text(encoding="utf-8"), original_ops)
            self.assertEqual((output_dir / "finance.txt").read_text(encoding="utf-8"), original_finance)
            diagnostics = json.loads((output_dir / DIAGNOSTICS_FILENAME).read_text(encoding="utf-8"))
            self.assertEqual(diagnostics["status"], "degraded")
            self.assertEqual(diagnostics["lastSuccessAt"], original_generated_at.isoformat().replace("+00:00", "Z"))

    def test_pod_config_rejects_overlap(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pods.json"
            path.write_text(
                json.dumps(
                    {
                        "pods": [
                            {"id": "pod-1", "label": "Pod 1", "start_gate": 1, "end_gate": 9},
                            {"id": "pod-2", "label": "Pod 2", "start_gate": 9, "end_gate": 22},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "overlaps"):
                load_pod_ranges(path)

    def test_pod_config_requires_full_coverage(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "pods.json"
            path.write_text(
                json.dumps(
                    {
                        "pods": [
                            {"id": "pod-1", "label": "Pod 1", "start_gate": 1, "end_gate": 9},
                            {"id": "pod-4", "label": "Pod 4", "start_gate": 10, "end_gate": 16},
                            {"id": "pod-5", "label": "Pod 5", "start_gate": 18, "end_gate": 22},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "missing G17"):
                load_pod_ranges(path)

    def test_pages_shell_exists(self) -> None:
        index_html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        app_js = (ROOT / "docs" / "app.js").read_text(encoding="utf-8")
        styles_css = (ROOT / "docs" / "styles.css").read_text(encoding="utf-8")
        anime_js = (ROOT / "docs" / "vendor" / "anime.iife.min.js").read_text(encoding="utf-8")

        self.assertIn("Concourse G", index_html)
        self.assertIn("pod-filters", index_html)
        self.assertIn("theme-cycle", index_html)
        self.assertIn("Board filters", index_html)
        self.assertIn("finance-plain", index_html)
        self.assertIn("finance-subpill", app_js)
        self.assertIn("Finance - Diffs", app_js)
        self.assertIn("finance-cue-particle", app_js)
        self.assertIn("finance-pill-absorb", app_js)
        self.assertIn("emitAnimeFinanceCue", app_js)
        self.assertIn("const particleCount = 10", app_js)
        self.assertIn("return !shouldHideFinanceFilter();", app_js)
        self.assertIn("syncFilterButtons", app_js)
        self.assertIn("status-line", index_html)
        self.assertIn("vendor/anime.iife.min.js", index_html)
        self.assertIn("window.anime", app_js)
        self.assertIn("./finance.txt", app_js)
        self.assertIn("./diagnostics.json", app_js)
        self.assertIn("renderFinancePlainText", app_js)
        self.assertIn('"Diffs"', app_js)
        self.assertIn("AM Review Window", app_js)
        self.assertIn("PM Review Window", app_js)
        self.assertIn("Status unavailable", app_js)
        self.assertIn("Updated ", app_js)
        self.assertIn("buildFinanceDiffRecords", app_js)
        self.assertIn("buildFinanceLayeredNodes", app_js)
        self.assertIn("animateRedAlertSweep", app_js)
        self.assertIn("diff-strike-draw", styles_css)
        self.assertIn("diff-line-prefix-added", styles_css)
        self.assertIn("diff-line-prefix-removed", styles_css)
        self.assertIn("red-alert-cell", styles_css)
        self.assertNotIn("function animateRows", app_js)
        self.assertNotIn("function animateBoardTransition", app_js)
        self.assertNotIn("function animateHeaderTransition", app_js)
        self.assertNotIn("function animateFilterPress", app_js)
        self.assertNotIn("animateFinanceDiffReveal", app_js)

    def test_finance_diff_is_static_layered_rendering(self) -> None:
        app_js = (ROOT / "docs" / "app.js").read_text(encoding="utf-8")
        styles_css = (ROOT / "docs" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("diff-line-prefix", styles_css)
        self.assertIn("finance-overlay-line-added", styles_css)
        self.assertIn("finance-overlay-line-removed", styles_css)
        self.assertIn("diff-line-content-removed", styles_css)
        self.assertIn('join(" | ")', app_js)
        self.assertIn("buildFinanceOverlayLineNode", app_js)
        self.assertIn('prefix.textContent = `${item.kind === "added" ? "+" : "-"} `;', app_js)
        self.assertNotIn("lastDiffRevealKey", app_js)
        self.assertNotIn("animateDiffPrefix", app_js)
        self.assertNotIn("animateRemovedDiffLine", app_js)
        self.assertNotIn("animateAddedDiffLine", app_js)
        self.assertNotIn("diff-token-changed", styles_css)

    def test_finance_diff_uses_layered_base_and_overlay_rows(self) -> None:
        index_html = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")
        app_js = (ROOT / "docs" / "app.js").read_text(encoding="utf-8")
        styles_css = (ROOT / "docs" / "styles.css").read_text(encoding="utf-8")

        self.assertIn('<div class="finance-plain hidden" id="finance-plain"', index_html)
        self.assertIn("finance-record-base", app_js)
        self.assertIn("finance-record-overlays", app_js)
        self.assertIn("finance-overlay-line-added", styles_css)
        self.assertIn("finance-overlay-line-removed", styles_css)


if __name__ == "__main__":
    unittest.main()

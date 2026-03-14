from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from .config import load_pod_ranges
from .msp import (
    fetch_delta_departures_source,
    is_suspicious_parse,
    parse_departure_rows_with_diagnostics,
)
from .pipeline import (
    CHICAGO,
    FINANCE_CLEAR_HOUR,
    FINANCE_SNAPSHOT_HOURS,
    build_departures_from_now,
    has_last_good_snapshot,
    read_departure_count,
    should_fetch_now,
    write_failure_diagnostics,
    write_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate latest MSP Delta T1G outputs.")
    parser.add_argument("--output-dir", default="docs", help="Directory for generated output files.")
    parser.add_argument("--pod-config", default="config/pods.json", help="Path to pod config JSON.")
    args = parser.parse_args(argv)

    generated_at = datetime.now(timezone.utc)
    chicago_now = generated_at.astimezone(CHICAGO)
    update_finance, clear_finance = resolve_finance_actions(now=chicago_now)

    output_dir = Path(args.output_dir)
    pod_config = Path(args.pod_config)
    pods = load_pod_ranges(pod_config)
    previous_departure_count = read_departure_count(output_dir / "ops.json")

    try:
        markup, fetch_diagnostics = fetch_delta_departures_source()
        rows, parse_diagnostics = parse_departure_rows_with_diagnostics(
            markup,
            now=chicago_now,
            source=fetch_diagnostics.source,
            pages_fetched=fetch_diagnostics.pages_fetched,
        )
        if is_suspicious_parse(parse_diagnostics, previous_departure_count=previous_departure_count):
            raise RuntimeError(
                "MSP parse looked suspiciously incomplete; refusing to replace the last good snapshot."
            )

        departures = build_departures_from_now(rows=rows, pods=pods, now=chicago_now)
        write_outputs(
            output_dir=output_dir,
            departures=departures,
            pods=pods,
            generated_at=generated_at,
            update_finance=update_finance,
            clear_finance=clear_finance,
        )

        print(
            "MSP diagnostics:"
            f" source={parse_diagnostics.source}"
            f" pages={parse_diagnostics.pages_fetched}"
            f" rows_seen={parse_diagnostics.rows_seen}"
            f" candidate_rows={parse_diagnostics.candidate_rows}"
            f" rows_kept={parse_diagnostics.rows_kept}"
            f" status_rows={parse_diagnostics.status_rows}"
        )
        print(f"Finance update={'yes' if update_finance else 'no'}")
        print(f"Finance clear={'yes' if clear_finance else 'no'}")
        print(f"Wrote {len(departures)} departures to {output_dir}.")
        return 0
    except Exception as error:
        diagnostics = write_failure_diagnostics(output_dir, attempted_at=generated_at)
        if not has_last_good_snapshot(output_dir):
            raise

        print(
            f"Reused last good snapshot after refresh failure: {error}"
            f" status={diagnostics.status}",
            file=sys.stderr,
        )
        return 0


def resolve_finance_actions(
    *,
    now: datetime,
) -> tuple[bool, bool]:
    update_finance = should_fetch_now(set(FINANCE_SNAPSHOT_HOURS), now=now)
    clear_finance = now.hour == FINANCE_CLEAR_HOUR
    return update_finance, clear_finance


if __name__ == "__main__":
    sys.exit(main())

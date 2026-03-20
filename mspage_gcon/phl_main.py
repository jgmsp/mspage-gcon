from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

from .phl import (
    fetch_phl_departures_source,
    is_suspicious_phl_parse,
    parse_phl_departure_rows_with_diagnostics,
)
from .phl_pipeline import (
    NEW_YORK,
    build_phl_departures,
    build_phl_ops_departures_from_now,
    has_last_good_snapshot,
    load_terminal_definitions,
    read_departure_count,
    write_failure_diagnostics,
    write_phl_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate latest PHL AA Terminal B/F draft outputs.")
    parser.add_argument("--output-dir", default="docs/phl", help="Directory for generated PHL output files.")
    parser.add_argument(
        "--terminal-config",
        default="config/phl_terminals.json",
        help="Path to PHL terminal configuration JSON.",
    )
    args = parser.parse_args(argv)

    generated_at = datetime.now(timezone.utc)
    local_now = generated_at.astimezone(NEW_YORK)
    output_dir = Path(args.output_dir)
    terminals = load_terminal_definitions(Path(args.terminal_config))
    previous_departure_count = read_departure_count(output_dir / "ops.json")

    try:
        markup, fetch_diagnostics = fetch_phl_departures_source()
        rows, parse_diagnostics = parse_phl_departure_rows_with_diagnostics(
            markup,
            now=local_now,
            source=fetch_diagnostics.source,
        )
        if is_suspicious_phl_parse(parse_diagnostics, previous_departure_count=previous_departure_count):
            raise RuntimeError(
                "PHL parse looked suspiciously incomplete; refusing to replace the last good snapshot."
            )

        all_departures = build_phl_departures(rows)
        ops_departures = build_phl_ops_departures_from_now(all_departures, now=local_now)
        write_phl_outputs(
            output_dir=output_dir,
            ops_departures=ops_departures,
            stats_departures=all_departures,
            terminals=terminals,
            generated_at=generated_at,
        )

        print(
            "PHL diagnostics:"
            f" source={parse_diagnostics.source}"
            f" rows_seen={parse_diagnostics.rows_seen}"
            f" candidate_rows={parse_diagnostics.candidate_rows}"
            f" rows_kept={parse_diagnostics.rows_kept}"
            f" status_rows={parse_diagnostics.status_rows}"
        )
        print(f"Wrote {len(ops_departures)} active departures to {output_dir}.")
        return 0
    except Exception as error:
        diagnostics = write_failure_diagnostics(output_dir, attempted_at=generated_at)
        if not has_last_good_snapshot(output_dir):
            raise

        print(
            f"Reused last good PHL snapshot after refresh failure: {error}"
            f" status={diagnostics.status}",
            file=sys.stderr,
        )
        return 0


if __name__ == "__main__":
    sys.exit(main())

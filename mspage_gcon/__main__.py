from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from .airlabs import fetch_schedules
from .config import load_pod_ranges
from .pipeline import build_departures, should_fetch_now, write_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate latest MSP G-concourse outputs.")
    parser.add_argument("--output-dir", default="docs", help="Directory for generated output files.")
    parser.add_argument("--pod-config", default="config/pods.json", help="Path to pod config JSON.")
    parser.add_argument("--airport", default="MSP", help="Departure airport IATA code.")
    parser.add_argument("--limit", type=int, default=1000, help="AirLabs result limit.")
    parser.add_argument(
        "--api-key-env",
        default="AIRLABS_API_KEY",
        help="Environment variable that contains the AirLabs key.",
    )
    parser.add_argument(
        "--respect-schedule",
        action="store_true",
        help="Skip the fetch unless the current Chicago hour matches one of --schedule-hours.",
    )
    parser.add_argument(
        "--schedule-hours",
        default="4,13",
        help="Comma-separated Chicago local hours used with --respect-schedule.",
    )
    args = parser.parse_args(argv)

    schedule_hours = _parse_schedule_hours(args.schedule_hours)
    if args.respect_schedule and not should_fetch_now(schedule_hours):
        print("Skipping fetch outside the configured Chicago schedule window.")
        return 0

    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"Missing AirLabs API key in {args.api_key_env}.")

    output_dir = Path(args.output_dir)
    pod_config = Path(args.pod_config)
    pods = load_pod_ranges(pod_config)

    payload = fetch_schedules(api_key=api_key, dep_iata=args.airport, limit=args.limit)
    rows = payload.get("response", [])
    departures = build_departures(rows=rows, pods=pods)
    generated_at = datetime.now(timezone.utc)
    write_outputs(output_dir=output_dir, departures=departures, pods=pods, generated_at=generated_at)

    print(f"Wrote {len(departures)} departures to {output_dir}.")
    return 0


def _parse_schedule_hours(raw: str) -> set[int]:
    hours: set[int] = set()
    for part in raw.split(","):
        trimmed = part.strip()
        if not trimmed:
            continue
        hour = int(trimmed)
        if not 0 <= hour <= 23:
            raise ValueError(f"Invalid schedule hour: {trimmed}")
        hours.add(hour)
    if not hours:
        raise ValueError("At least one schedule hour must be provided.")
    return hours


if __name__ == "__main__":
    sys.exit(main())

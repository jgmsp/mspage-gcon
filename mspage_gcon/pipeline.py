from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from .config import PodRange, assign_pod


CHICAGO = ZoneInfo("America/Chicago")
GATE_PATTERN = re.compile(r"(?i)\bG\s*([0-9]{1,2})\b")
DATE_PATTERNS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
)


@dataclass(frozen=True)
class DepartureRecord:
    id: str
    flight_display: str
    flight_iata: str | None
    gate_number: int
    gate_label: str
    destination: str
    pod_id: str
    pod_label: str
    time_display_ops: str
    time_display_finance: str
    sort_timestamp: int
    status: str | None


def normalize_gate(raw_gate: str | None) -> int | None:
    if raw_gate is None:
        return None

    match = GATE_PATTERN.search(raw_gate.strip())
    if not match:
        return None

    gate = int(match.group(1))
    if 1 <= gate <= 22:
        return gate
    return None


def parse_airlabs_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None

    trimmed = value.strip()
    if not trimmed:
        return None

    for pattern in DATE_PATTERNS:
        try:
            return datetime.strptime(trimmed, pattern).replace(tzinfo=CHICAGO)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(trimmed)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=CHICAGO)
    return parsed.astimezone(CHICAGO)


def parse_timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=CHICAGO)
    except (TypeError, ValueError, OSError):
        return None


def select_departure_time(row: dict) -> datetime | None:
    return (
        parse_timestamp(row.get("dep_estimated_ts"))
        or parse_airlabs_datetime(row.get("dep_estimated"))
        or parse_timestamp(row.get("dep_time_ts"))
        or parse_airlabs_datetime(row.get("dep_time"))
    )


def should_fetch_now(schedule_hours: set[int], now: datetime | None = None) -> bool:
    current = now.astimezone(CHICAGO) if now else datetime.now(CHICAGO)
    return current.hour in schedule_hours


def build_departures(rows: list[dict], pods: list[PodRange]) -> list[DepartureRecord]:
    grouped: dict[tuple[int, str, str], list[dict]] = defaultdict(list)

    for row in rows:
        gate = normalize_gate(row.get("dep_gate"))
        if gate is None:
            continue

        departure_time = select_departure_time(row)
        if departure_time is None:
            continue

        dep_key = (
            str(row.get("dep_time_ts") or "")
            or str(row.get("dep_time") or "")
            or str(row.get("dep_estimated_ts") or "")
            or str(row.get("dep_estimated") or "")
        )
        destination = _clean_string(row.get("arr_iata")) or "UNK"
        grouped[(gate, dep_key, destination)].append(row)

    departures: list[DepartureRecord] = []
    for (gate, dep_key, destination), group_rows in grouped.items():
        exemplar = _pick_exemplar(group_rows)
        departure_time = select_departure_time(exemplar)
        if departure_time is None:
            continue

        pod = assign_pod(gate, pods)
        pod_id = pod.id if pod else "unassigned"
        pod_label = pod.label if pod else "Unassigned"
        flight_display, flight_iata = _choose_operating_flight(group_rows)
        gate_label = f"G{gate}"
        status = _clean_string(exemplar.get("status"))

        departures.append(
            DepartureRecord(
                id=f"{gate_label}-{dep_key}-{destination}",
                flight_display=flight_display or "UNK",
                flight_iata=flight_iata,
                gate_number=gate,
                gate_label=gate_label,
                destination=destination,
                pod_id=pod_id,
                pod_label=pod_label,
                time_display_ops=departure_time.strftime("%H%M"),
                time_display_finance=departure_time.strftime("%I:%M").lstrip("0") or "0:00",
                sort_timestamp=int(departure_time.timestamp()),
                status=status,
            )
        )

    departures.sort(key=lambda item: (item.sort_timestamp, item.gate_number, item.destination))
    return departures


def build_ops_payload(
    departures: list[DepartureRecord],
    pods: list[PodRange],
    generated_at: datetime | None = None,
) -> dict:
    created = generated_at or datetime.now(timezone.utc)
    return {
        "airport": "MSP",
        "concourse": "G",
        "generatedAt": created.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "pods": [asdict(pod) for pod in pods],
        "departures": [
            {
                "id": departure.id,
                "flightDisplay": departure.flight_display,
                "flightIata": departure.flight_iata,
                "gateNumber": departure.gate_number,
                "gateLabel": departure.gate_label,
                "destination": departure.destination,
                "podId": departure.pod_id,
                "podLabel": departure.pod_label,
                "timeDisplayOps": departure.time_display_ops,
                "timeDisplayFinance": departure.time_display_finance,
                "sortTimestamp": departure.sort_timestamp,
                "status": departure.status,
            }
            for departure in departures
        ],
    }


def render_finance_text(departures: list[DepartureRecord]) -> str:
    headers = ("Flight", "Gate", "Time")
    rows = [
        (departure.flight_display, str(departure.gate_number), departure.time_display_finance)
        for departure in departures
    ]

    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    lines = [
        " | ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    ]
    for row in rows:
        lines.append(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))

    return "\n".join(lines) + "\n"


def write_outputs(
    output_dir: Path,
    departures: list[DepartureRecord],
    pods: list[PodRange],
    generated_at: datetime | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    ops_payload = build_ops_payload(departures=departures, pods=pods, generated_at=generated_at)
    (output_dir / "ops.json").write_text(
        json.dumps(ops_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "finance.txt").write_text(render_finance_text(departures), encoding="utf-8")


def _pick_exemplar(group_rows: list[dict]) -> dict:
    def score(row: dict) -> tuple[int, int]:
        has_estimated = int(bool(row.get("dep_estimated_ts") or row.get("dep_estimated")))
        has_codeshare = int(bool(row.get("cs_flight_iata") or row.get("cs_flight_number")))
        return (has_estimated, has_codeshare)

    return max(group_rows, key=score)


def _choose_operating_flight(group_rows: list[dict]) -> tuple[str, str | None]:
    candidates: dict[str, dict] = {}

    for row in group_rows:
        flight_iata = _clean_string(row.get("cs_flight_iata")) or _clean_string(row.get("flight_iata"))
        flight_number = (
            _clean_string(row.get("cs_flight_number"))
            or _clean_string(row.get("flight_number"))
            or _extract_digits(flight_iata)
        )

        key = flight_iata or flight_number or "UNK"
        entry = candidates.setdefault(
            key,
            {
                "count": 0,
                "flight_iata": flight_iata,
                "flight_number": flight_number,
            },
        )
        entry["count"] += 1
        if not entry["flight_iata"] and flight_iata:
            entry["flight_iata"] = flight_iata
        if not entry["flight_number"] and flight_number:
            entry["flight_number"] = flight_number

    if not candidates:
        return ("UNK", None)

    winner = max(
        candidates.values(),
        key=lambda item: (
            item["count"],
            int(bool(item["flight_number"])),
            int(bool(item["flight_iata"])),
            -len(item["flight_iata"] or ""),
        ),
    )

    display = winner["flight_number"] or _extract_digits(winner["flight_iata"]) or winner["flight_iata"] or "UNK"
    return display, winner["flight_iata"]


def _extract_digits(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(character for character in value if character.isdigit())
    return digits or None


def _clean_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None

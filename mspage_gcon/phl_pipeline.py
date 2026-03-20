from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")
STALE_THRESHOLD_MINUTES = 180
DIAGNOSTICS_FILENAME = "diagnostics.json"
OPS_FILENAME = "ops.json"
STATS_FILENAME = "stats.json"
TERMINAL_LABELS = {
    "TB": "Terminal B",
    "TC": "Terminal C",
    "TF": "Terminal F",
}


@dataclass(frozen=True)
class TerminalDefinition:
    id: str
    label: str
    venues: tuple[str, ...]


@dataclass(frozen=True)
class PHLDepartureRecord:
    id: str
    flight_display: str
    flight_iata: str
    destination: str
    gate_label: str
    terminal_id: str
    terminal_label: str
    departure_time: datetime
    time_display: str
    sort_timestamp: int
    status: str | None = None


@dataclass(frozen=True)
class PublishDiagnostics:
    status: str
    last_success_at: datetime | None


def load_terminal_definitions(path: Path) -> list[TerminalDefinition]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    terminals = payload.get("terminals")
    if not isinstance(terminals, list) or not terminals:
        raise ValueError("PHL terminal config must contain a non-empty 'terminals' list.")

    loaded: list[TerminalDefinition] = []
    seen_ids: set[str] = set()
    for index, terminal in enumerate(terminals, start=1):
        if not isinstance(terminal, dict):
            raise ValueError(f"Terminal {index} must be an object.")

        terminal_id = _require_text(terminal, "id", index)
        if terminal_id in seen_ids:
            raise ValueError(f"Duplicate terminal id: {terminal_id}")
        seen_ids.add(terminal_id)

        venues = terminal.get("venues")
        if not isinstance(venues, list) or not venues:
            raise ValueError(f"Terminal {terminal_id} must define a non-empty venues list.")

        loaded.append(
            TerminalDefinition(
                id=terminal_id,
                label=_require_text(terminal, "label", index),
                venues=tuple(_require_text({"venue": value}, "venue", index) for value in venues),
            )
        )

    return loaded


def build_phl_departures(rows: list[dict]) -> list[PHLDepartureRecord]:
    departures: list[PHLDepartureRecord] = []
    for row in rows:
        departure_time = row["departure_time"].astimezone(NEW_YORK)
        terminal_id = row["terminal_id"]
        gate_label = row["gate_label"]
        flight_display = row["flight_display"]
        flight_iata = row.get("flight_iata") or flight_display.replace(" ", "")
        sort_timestamp = int(row.get("sort_timestamp") or departure_time.timestamp())
        departures.append(
            PHLDepartureRecord(
                id=f"{flight_iata}-{gate_label}-{sort_timestamp}",
                flight_display=flight_display,
                flight_iata=flight_iata,
                destination=row["destination"],
                gate_label=gate_label,
                terminal_id=terminal_id,
                terminal_label=TERMINAL_LABELS.get(terminal_id, terminal_id),
                departure_time=departure_time,
                time_display=departure_time.strftime("%I:%M %p").lstrip("0"),
                sort_timestamp=sort_timestamp,
                status=row.get("status"),
            )
        )

    departures.sort(key=lambda item: (item.sort_timestamp, item.gate_label, item.flight_display))
    return departures


def build_phl_ops_departures_from_now(
    departures: list[PHLDepartureRecord],
    *,
    now: datetime,
) -> list[PHLDepartureRecord]:
    current = now.astimezone(NEW_YORK)
    return [
        departure
        for departure in departures
        if departure.terminal_id in {"TB", "TF"} and departure.departure_time >= current
    ]


def build_phl_ops_payload(
    *,
    departures: list[PHLDepartureRecord],
    terminals: list[TerminalDefinition],
    generated_at: datetime | None = None,
) -> dict:
    created = generated_at or datetime.now(timezone.utc)
    return {
        "airport": "PHL",
        "airline": "AA",
        "generatedAt": _isoformat_utc(created),
        "terminals": [
            {
                "id": terminal.id,
                "label": terminal.label,
                "venues": list(terminal.venues),
            }
            for terminal in terminals
        ],
        "departures": [
            {
                "id": departure.id,
                "flightDisplay": departure.flight_display,
                "flightIata": departure.flight_iata,
                "destination": departure.destination,
                "gateLabel": departure.gate_label,
                "terminalId": departure.terminal_id,
                "terminalLabel": departure.terminal_label,
                "timeDisplay": departure.time_display,
                "sortTimestamp": departure.sort_timestamp,
                **({"status": departure.status} if departure.status else {}),
            }
            for departure in departures
        ],
    }


def update_stats_snapshot(
    *,
    previous_payload: dict | None,
    departures: list[PHLDepartureRecord],
    generated_at: datetime,
) -> dict:
    created = generated_at.astimezone(timezone.utc)
    service_date = created.astimezone(NEW_YORK).date().isoformat()
    if previous_payload and previous_payload.get("serviceDate") == service_date:
        positions = dict(previous_payload.get("positions") or {})
        events = list(previous_payload.get("events") or [])
    else:
        positions = {}
        events = []

    for departure in departures:
        if departure.terminal_id not in {"TB", "TC"}:
            continue
        previous_position = positions.get(departure.flight_display)
        if previous_position and previous_position.get("terminalId") != departure.terminal_id:
            previous_terminal = previous_position.get("terminalId")
            if {previous_terminal, departure.terminal_id} == {"TB", "TC"}:
                direction = "lostToC" if previous_terminal == "TB" else "gainedFromC"
                events.append(
                    {
                        "id": f"{departure.flight_iata}-{previous_terminal}-{departure.terminal_id}-{int(created.timestamp())}",
                        "direction": direction,
                        "flightDisplay": departure.flight_display,
                        "fromTerminalId": previous_terminal,
                        "toTerminalId": departure.terminal_id,
                        "fromGateLabel": previous_position.get("gateLabel"),
                        "toGateLabel": departure.gate_label,
                        "departureTime": departure.time_display,
                        "detectedAt": _isoformat_utc(created),
                    }
                )

        positions[departure.flight_display] = {
            "terminalId": departure.terminal_id,
            "gateLabel": departure.gate_label,
            "departureTime": departure.time_display,
        }

    summary = {
        "gainedFromC": sum(1 for event in events if event.get("direction") == "gainedFromC"),
        "lostToC": sum(1 for event in events if event.get("direction") == "lostToC"),
    }
    return {
        "serviceDate": service_date,
        "generatedAt": _isoformat_utc(created),
        "summary": summary,
        "events": events,
        "positions": positions,
    }


def write_phl_outputs(
    *,
    output_dir: Path,
    ops_departures: list[PHLDepartureRecord],
    stats_departures: list[PHLDepartureRecord],
    terminals: list[TerminalDefinition],
    generated_at: datetime | None = None,
) -> None:
    created = generated_at or datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    previous_stats = _read_json(output_dir / STATS_FILENAME)
    ops_payload = build_phl_ops_payload(
        departures=ops_departures,
        terminals=terminals,
        generated_at=created,
    )
    stats_payload = update_stats_snapshot(
        previous_payload=previous_stats,
        departures=stats_departures,
        generated_at=created,
    )
    _atomic_write_text(output_dir / OPS_FILENAME, json.dumps(ops_payload, indent=2) + "\n")
    _atomic_write_text(output_dir / STATS_FILENAME, json.dumps(stats_payload, indent=2) + "\n")
    write_diagnostics(output_dir, build_publish_diagnostics(status="healthy", last_success_at=created))


def build_publish_diagnostics(*, status: str, last_success_at: datetime | None) -> PublishDiagnostics:
    return PublishDiagnostics(status=status, last_success_at=last_success_at)


def write_diagnostics(output_dir: Path, diagnostics: PublishDiagnostics) -> None:
    payload = {
        "status": diagnostics.status,
        "lastSuccessAt": _isoformat_utc(diagnostics.last_success_at) if diagnostics.last_success_at else None,
        "staleAfterMinutes": STALE_THRESHOLD_MINUTES,
    }
    _atomic_write_text(output_dir / DIAGNOSTICS_FILENAME, json.dumps(payload, indent=2) + "\n")


def write_failure_diagnostics(output_dir: Path, *, attempted_at: datetime) -> PublishDiagnostics:
    last_success_at = read_last_success_at(output_dir)
    diagnostics = build_publish_diagnostics(
        status=_failure_status(attempted_at=attempted_at, last_success_at=last_success_at),
        last_success_at=last_success_at,
    )
    write_diagnostics(output_dir, diagnostics)
    return diagnostics


def read_last_success_at(output_dir: Path) -> datetime | None:
    payload = _read_json(output_dir / DIAGNOSTICS_FILENAME)
    if payload and payload.get("lastSuccessAt"):
        return _parse_datetime_value(str(payload["lastSuccessAt"]))
    ops_payload = _read_json(output_dir / OPS_FILENAME)
    if ops_payload and ops_payload.get("generatedAt"):
        return _parse_datetime_value(str(ops_payload["generatedAt"]))
    return None


def has_last_good_snapshot(output_dir: Path) -> bool:
    return (output_dir / OPS_FILENAME).exists()


def read_departure_count(path: Path) -> int | None:
    payload = _read_json(path)
    if not payload:
        return None
    departures = payload.get("departures")
    if not isinstance(departures, list):
        return None
    return len(departures)


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _failure_status(*, attempted_at: datetime, last_success_at: datetime | None) -> str:
    if last_success_at is None:
        return "stale"
    age_minutes = int(
        (
            attempted_at.astimezone(timezone.utc)
            - last_success_at.astimezone(timezone.utc)
        ).total_seconds()
        // 60
    )
    if age_minutes > STALE_THRESHOLD_MINUTES:
        return "stale"
    return "degraded"


def _parse_datetime_value(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(NEW_YORK)


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _require_text(container: dict, key: str, index: int) -> str:
    value = container.get(key)
    if value is None:
        raise ValueError(f"Terminal {index} is missing {key}.")
    text = str(value).strip()
    if not text:
        raise ValueError(f"Terminal {index} has an empty {key}.")
    return text

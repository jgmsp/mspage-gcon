from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from zoneinfo import ZoneInfo

from .config import PodRange, assign_pod


CHICAGO = ZoneInfo("America/Chicago")
FINANCE_SNAPSHOT_HOURS = frozenset({5, 12})
STALE_THRESHOLD_MINUTES = 180
DIAGNOSTICS_FILENAME = "diagnostics.json"
GATE_PATTERN = re.compile(r"(?i)\b(?:T1)?G\s*([0-9]{1,2})\b")
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
    departure_time: datetime
    status: str | None = None


@dataclass(frozen=True)
class FinanceEntry:
    flight_display: str
    gate_number: int
    time_display_finance: str
    sort_timestamp: int

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.flight_display, self.gate_number, self.time_display_finance)


@dataclass(frozen=True)
class PublishDiagnostics:
    status: str
    last_success_at: datetime | None


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
    return _build_departures(rows=rows, pods=pods, not_before=None)


def _build_departures(
    rows: list[dict],
    pods: list[PodRange],
    not_before: datetime | None,
) -> list[DepartureRecord]:
    grouped: dict[tuple[int, str, str], list[dict]] = defaultdict(list)
    threshold_minute = _minute_epoch(not_before) if not_before else None

    for row in rows:
        gate = normalize_gate(row.get("dep_gate"))
        if gate is None:
            continue

        departure_time = select_departure_time(row)
        if departure_time is None:
            continue
        if threshold_minute is not None and _minute_epoch(departure_time) < threshold_minute:
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
                time_display_finance=departure_time.strftime("%H:%M"),
                sort_timestamp=int(departure_time.timestamp()),
                departure_time=departure_time,
                status=_choose_status(group_rows),
            )
        )

    departures.sort(key=lambda item: (item.sort_timestamp, item.gate_number, item.destination))
    return departures


def build_departures_from_now(
    rows: list[dict],
    pods: list[PodRange],
    now: datetime,
) -> list[DepartureRecord]:
    return _build_departures(rows=rows, pods=pods, not_before=now)


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
                **({"status": departure.status} if departure.status else {}),
            }
            for departure in departures
        ],
    }


def build_finance_entries(
    departures: list[DepartureRecord],
    *,
    day: datetime,
) -> list[FinanceEntry]:
    return [
        FinanceEntry(
            flight_display=departure.flight_display,
            gate_number=departure.gate_number,
            time_display_finance=departure.time_display_finance,
            sort_timestamp=departure.sort_timestamp,
        )
        for departure in departures
        if departure.departure_time.astimezone(CHICAGO).date() == day.date()
    ]


def render_finance_text(finance_entries: list[FinanceEntry]) -> str:
    headers = ("Flight", "Gate", "Time")
    rows = [
        (entry.flight_display, str(entry.gate_number), entry.time_display_finance)
        for entry in finance_entries
    ]

    widths = [len(header) for header in headers]
    for row in rows:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    lines = [" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)).rstrip()]
    for row in rows:
        lines.append(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)).rstrip())
    return "\n".join(lines) + "\n"


def build_publish_diagnostics(
    *,
    status: str,
    last_success_at: datetime | None,
) -> PublishDiagnostics:
    return PublishDiagnostics(status=status, last_success_at=last_success_at)


def build_diagnostics_payload(diagnostics: PublishDiagnostics) -> dict[str, str | None]:
    return {
        "status": diagnostics.status,
        "lastSuccessAt": _isoformat_utc(diagnostics.last_success_at) if diagnostics.last_success_at else None,
        "staleAfterMinutes": STALE_THRESHOLD_MINUTES,
    }


def write_diagnostics(
    output_dir: Path,
    diagnostics: PublishDiagnostics,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = build_diagnostics_payload(diagnostics)
    _atomic_write_text(
        output_dir / DIAGNOSTICS_FILENAME,
        json.dumps(payload, indent=2) + "\n",
    )


def write_failure_diagnostics(
    output_dir: Path,
    *,
    attempted_at: datetime,
) -> PublishDiagnostics:
    last_success_at = read_last_success_at(output_dir)
    diagnostics = build_publish_diagnostics(
        status=_failure_status(attempted_at=attempted_at, last_success_at=last_success_at),
        last_success_at=last_success_at,
    )
    write_diagnostics(output_dir, diagnostics)
    return diagnostics


def write_outputs(
    output_dir: Path,
    departures: list[DepartureRecord],
    pods: list[PodRange],
    generated_at: datetime | None = None,
    update_finance: bool = True,
    clear_finance: bool = False,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    created = generated_at or datetime.now(timezone.utc)
    chicago_now = created.astimezone(CHICAGO)
    finance_text: str | None = None
    if clear_finance:
        finance_text = render_finance_text([])
    elif update_finance:
        finance_entries = build_finance_entries(departures, day=chicago_now)
        finance_text = render_finance_text(finance_entries)

    ops_payload = build_ops_payload(departures=departures, pods=pods, generated_at=created)
    _atomic_write_text(output_dir / "ops.json", json.dumps(ops_payload, indent=2) + "\n")
    if finance_text is not None:
        _atomic_write_text(output_dir / "finance.txt", finance_text)
    write_diagnostics(
        output_dir,
        build_publish_diagnostics(status="healthy", last_success_at=created),
    )


def read_last_success_at(output_dir: Path) -> datetime | None:
    diagnostics_path = output_dir / DIAGNOSTICS_FILENAME
    diagnostics = _read_diagnostics(diagnostics_path)
    if diagnostics and diagnostics.last_success_at:
        return diagnostics.last_success_at
    return _read_existing_generated_at(output_dir / "ops.json")


def has_last_good_snapshot(output_dir: Path) -> bool:
    return (output_dir / "ops.json").exists()


def read_departure_count(path: Path) -> int | None:
    payload = _read_ops_payload(path)
    if payload is None:
        return None
    departures = payload.get("departures")
    if not isinstance(departures, list):
        return None
    return len(departures)


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


def _choose_status(group_rows: list[dict]) -> str | None:
    priorities = {
        "Cancelled": 5,
        "Delayed": 4,
        "Boarding": 3,
        "On Time": 2,
        "Departed": 1,
    }
    statuses = [_clean_string(row.get("status")) for row in group_rows]
    statuses = [status for status in statuses if status]
    if not statuses:
        return None
    return max(statuses, key=lambda status: priorities.get(status, 0))


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


def _minute_epoch(value: datetime) -> int:
    return int(value.timestamp()) // 60


def _read_existing_generated_at(path: Path) -> datetime | None:
    payload = _read_ops_payload(path)
    if payload is None:
        return None
    generated_at = payload.get("generatedAt")
    if not generated_at:
        return None
    return _parse_datetime_value(str(generated_at))


def _read_ops_payload(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _read_diagnostics(path: Path) -> PublishDiagnostics | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None

    status = _clean_string(payload.get("status"))
    if status is None:
        return None
    last_success_raw = payload.get("lastSuccessAt")
    last_success_at = _parse_datetime_value(str(last_success_raw)) if last_success_raw else None
    return PublishDiagnostics(status=status, last_success_at=last_success_at)


def _parse_datetime_value(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(CHICAGO)


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


def _failure_status(*, attempted_at: datetime, last_success_at: datetime | None) -> str:
    if last_success_at is None:
        return "stale"
    age_minutes = int((attempted_at.astimezone(timezone.utc) - last_success_at.astimezone(timezone.utc)).total_seconds() // 60)
    if age_minutes > STALE_THRESHOLD_MINUTES:
        return "stale"
    return "degraded"

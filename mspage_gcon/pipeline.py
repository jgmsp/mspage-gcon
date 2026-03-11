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
AM_START_MINUTES = 4 * 60 + 30
PM_START_MINUTES = 13 * 60
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

    totals = summarize_finance_entries(finance_entries)
    lines.extend(
        [
            "",
            f"Total flights: {totals['total']}",
            f"AM flights: {totals['am']}",
            f"PM flights: {totals['pm']}",
        ]
    )
    return "\n".join(lines) + "\n"


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
    (output_dir / "ops.json").write_text(
        json.dumps(ops_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    if finance_text is not None:
        (output_dir / "finance.txt").write_text(finance_text, encoding="utf-8")


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


def summarize_finance_entries(finance_entries: list[FinanceEntry]) -> dict[str, int]:
    total = len(finance_entries)
    am = 0
    pm = 0

    for entry in finance_entries:
        bucket = _finance_bucket(entry)
        if bucket == "am":
            am += 1
        elif bucket == "pm":
            pm += 1

    return {"total": total, "am": am, "pm": pm}


def parse_finance_text(
    text: str,
    *,
    day: datetime,
) -> list[FinanceEntry]:
    entries: list[FinanceEntry] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if (
            not line
            or line in {"AM", "PM"}
            or line.startswith("Flight |")
            or line.startswith("Total flights:")
            or line.startswith("AM flights:")
            or line.startswith("PM flights:")
        ):
            continue

        parts = [part.strip() for part in raw_line.split("|")]
        if len(parts) != 3:
            continue

        flight_display, gate_text, time_text = parts
        if not gate_text.isdigit():
            continue
        try:
            sort_timestamp = _finance_sort_timestamp(day=day, time_display=time_text)
        except ValueError:
            continue

        entries.append(
            FinanceEntry(
                flight_display=flight_display,
                gate_number=int(gate_text),
                time_display_finance=time_text,
                sort_timestamp=sort_timestamp,
            )
        )

    entries.sort(key=lambda entry: (entry.sort_timestamp, entry.gate_number, entry.flight_display))
    return entries


def _merge_finance_entries(
    output_dir: Path,
    new_entries: list[FinanceEntry],
    generated_at: datetime,
) -> list[FinanceEntry]:
    merged: dict[tuple[str, int, str], FinanceEntry] = {}

    existing_generated_at = _read_existing_generated_at(output_dir / "ops.json")
    if existing_generated_at and existing_generated_at.date() == generated_at.date():
        existing_text = (output_dir / "finance.txt").read_text(encoding="utf-8") if (output_dir / "finance.txt").exists() else ""
        for entry in parse_finance_text(existing_text, day=generated_at):
            merged[entry.key] = entry

    for entry in new_entries:
        merged[entry.key] = entry

    return sorted(merged.values(), key=lambda entry: (entry.sort_timestamp, entry.gate_number, entry.flight_display))


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
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        generated_at = payload.get("generatedAt")
    except (json.JSONDecodeError, OSError, AttributeError):
        return None

    if not generated_at:
        return None

    try:
        parsed = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(CHICAGO)


def _parse_finance_time(value: str) -> tuple[int, int]:
    hour_text, minute_text = value.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid finance time: {value}")
    return hour, minute


def _finance_sort_timestamp(*, day: datetime, time_display: str) -> int:
    hour, minute = _parse_finance_time(time_display)
    parsed = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return int(parsed.timestamp())


def _finance_bucket(entry: FinanceEntry) -> str | None:
    hour, minute = _parse_finance_time(entry.time_display_finance)
    total_minutes = hour * 60 + minute
    if AM_START_MINUTES <= total_minutes < PM_START_MINUTES:
        return "am"
    if total_minutes >= PM_START_MINUTES:
        return "pm"
    return None

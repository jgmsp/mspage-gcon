from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
import re
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")
PHL_FLIGHTS_URL = "https://www.phl.org/flights"
PHL_HEADERS = {"User-Agent": "mspage-gcon/0.1"}
DEPARTURES_TABLE_PATTERN = re.compile(
    r'<table[^>]*id="flight_feed_departures_table"[^>]*>(.*?)</table>',
    re.IGNORECASE | re.DOTALL,
)
ROW_PATTERN = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL_PATTERN = re.compile(r"<td\b([^>]*)>(.*?)</td>", re.IGNORECASE | re.DOTALL)
ATTR_PATTERN = re.compile(r'([a-zA-Z0-9_-]+)="([^"]*)"')
TAG_PATTERN = re.compile(r"<[^>]+>")
FLIGHT_NUMBER_PATTERN = re.compile(
    r'<div[^>]*class="[^"]*flight-number[^"]*"[^>]*>(.*?)</div>',
    re.IGNORECASE | re.DOTALL,
)
AIRPORT_NAME_PATTERN = re.compile(
    r'<span[^>]*class="[^"]*airport-name[^"]*"[^>]*>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)
AIRLINE_NAME_PATTERN = re.compile(
    r'<a[^>]*class="[^"]*airline-name[^"]*"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
GATE_PATTERN = re.compile(r"\b([BCF])\s*([0-9]{1,2})\b", re.IGNORECASE)
TIME_PATTERN = re.compile(r"(?i)\b(\d{1,2}):(\d{2})\s*([ap])m\b")
TERMINAL_PREFIXES = {"B": "TB", "C": "TC", "F": "TF"}


@dataclass(frozen=True)
class PHLFetchDiagnostics:
    source: str


@dataclass(frozen=True)
class PHLParseDiagnostics:
    source: str
    rows_seen: int
    candidate_rows: int
    rows_kept: int
    status_rows: int


def fetch_phl_departures_source(timeout: float = 20.0) -> tuple[str, PHLFetchDiagnostics]:
    request = Request(PHL_FLIGHTS_URL, headers=PHL_HEADERS)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace"), PHLFetchDiagnostics(source="page")


def parse_phl_departure_rows(markup: str, now: datetime | None = None) -> list[dict]:
    rows, _ = parse_phl_departure_rows_with_diagnostics(markup, now=now)
    return rows


def parse_phl_departure_rows_with_diagnostics(
    markup: str,
    now: datetime | None = None,
    *,
    source: str = "page",
) -> tuple[list[dict], PHLParseDiagnostics]:
    current = now.astimezone(NEW_YORK) if now else datetime.now(NEW_YORK)
    table_markup = _extract_departures_table(markup)
    rows_seen = 0
    candidate_rows = 0
    status_rows = 0
    rows: list[dict] = []

    for row_html in ROW_PATTERN.findall(table_markup):
        cells = CELL_PATTERN.findall(row_html)
        if len(cells) < 5:
            continue

        rows_seen += 1
        time_attrs, time_html = cells[0]
        detail_attrs, detail_html = cells[1]
        _, status_html = cells[2]
        _, airline_html = cells[3]
        gate_attrs, gate_html = cells[4]

        airline = _extract_airline(airline_html)
        gate_label = _extract_gate(gate_attrs, gate_html)
        terminal_id = _terminal_id_for_gate(gate_label)
        flight_display = _extract_flight_display(detail_html)
        if airline == "American Airlines" and terminal_id and flight_display:
            candidate_rows += 1

        if airline != "American Airlines" or terminal_id is None or flight_display is None:
            continue

        departure_time = _extract_departure_time(time_attrs, time_html, now=current)
        if departure_time is None:
            continue

        status = parse_phl_status(_clean_text(status_html))
        if status:
            status_rows += 1

        rows.append(
            {
                "flight_display": flight_display,
                "flight_iata": flight_display.replace(" ", ""),
                "destination": _extract_destination(detail_html) or "Unknown",
                "gate_label": gate_label,
                "terminal_id": terminal_id,
                "departure_time": departure_time,
                "sort_timestamp": int(departure_time.timestamp()),
                "status": status,
            }
        )

    rows.sort(key=lambda item: (item["sort_timestamp"], item["gate_label"], item["flight_display"]))
    diagnostics = PHLParseDiagnostics(
        source=source,
        rows_seen=rows_seen,
        candidate_rows=candidate_rows,
        rows_kept=len(rows),
        status_rows=status_rows,
    )
    return rows, diagnostics


def is_suspicious_phl_parse(
    diagnostics: PHLParseDiagnostics,
    previous_departure_count: int | None = None,
) -> bool:
    if diagnostics.rows_seen == 0 or diagnostics.candidate_rows == 0 or diagnostics.rows_kept == 0:
        return True
    if previous_departure_count and diagnostics.rows_kept < max(2, previous_departure_count // 3):
        return True
    return False


def parse_phl_status(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    return cleaned or None


def _extract_departures_table(markup: str) -> str:
    match = DEPARTURES_TABLE_PATTERN.search(markup)
    return match.group(1) if match else ""


def _extract_airline(markup: str) -> str | None:
    match = AIRLINE_NAME_PATTERN.search(markup)
    return _clean_text(match.group(1)) if match else _clean_text(markup)


def _extract_destination(markup: str) -> str | None:
    match = AIRPORT_NAME_PATTERN.search(markup)
    return _clean_text(match.group(1)) if match else None


def _extract_flight_display(markup: str) -> str | None:
    match = FLIGHT_NUMBER_PATTERN.search(markup)
    return _clean_text(match.group(1)) if match else None


def _extract_gate(attrs_text: str, markup: str) -> str | None:
    attrs = dict(ATTR_PATTERN.findall(attrs_text))
    candidate = attrs.get("data-order") or _clean_text(markup)
    if not candidate:
        return None
    match = GATE_PATTERN.search(candidate)
    if not match:
        return None
    return f"{match.group(1).upper()}{int(match.group(2))}"


def _terminal_id_for_gate(gate_label: str | None) -> str | None:
    if not gate_label:
        return None
    return TERMINAL_PREFIXES.get(gate_label[0].upper())


def _extract_departure_time(attrs_text: str, markup: str, *, now: datetime) -> datetime | None:
    attrs = dict(ATTR_PATTERN.findall(attrs_text))
    data_order = attrs.get("data-order", "").strip()
    if data_order.isdigit():
        try:
            return datetime.fromtimestamp(int(data_order), tz=NEW_YORK)
        except (ValueError, OSError):
            pass

    text = _clean_text(markup)
    if not text:
        return None
    match = TIME_PATTERN.search(text)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    meridiem = match.group(3).lower()
    if meridiem == "p" and hour != 12:
        hour += 12
    if meridiem == "a" and hour == 12:
        hour = 0

    parsed = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if parsed - now > timedelta(hours=18):
        return parsed - timedelta(days=1)
    if now - parsed > timedelta(hours=18):
        return parsed + timedelta(days=1)
    return parsed


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = TAG_PATTERN.sub(" ", unescape(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text or None

from __future__ import annotations

from datetime import datetime, timedelta
from html import unescape
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .pipeline import CHICAGO


MSP_AJAX_URL = "https://www.mspairport.com/views/ajax"
MSP_FLIGHTS_URL = "https://www.mspairport.com/flights-and-airlines/flights"
MSP_VIEW_PARAMS = {
    "view_name": "flights",
    "view_display_id": "default",
    "view_args": "",
    "view_path": "/node/1391",
    "view_base_path": "flights-and-airlines/flights",
    "view_dom_id": "ad37adf97e60a1ba08e197e0c47820b03846c9d7d3b0b31eb11758e648374ed2",
    "pager_element": "0",
    "_drupal_ajax": "1",
    "flight_type": "departures",
    "text": "",
}
MSP_QUERY_PARAMS = {
    "flight_type": "departures",
    "text": "",
}
MSP_HEADERS = {
    "User-Agent": "mspage-gcon/0.1",
    "Referer": f"{MSP_FLIGHTS_URL}?{urlencode(MSP_QUERY_PARAMS)}",
}
AJAX_HEADERS = {
    **MSP_HEADERS,
    "X-Requested-With": "XMLHttpRequest",
}

ROW_PATTERN = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
CELL_TEMPLATE = r'<td[^>]*class="[^"]*{marker}[^"]*"[^>]*>(.*?)</td>'
RAW_GATE_PATTERN = re.compile(r"(?i)\bT1G([1-9]|1\d|2[0-2])\b")
DESTINATION_CODE_PATTERN = re.compile(r"\(([A-Z0-9]{2,4})\)")
FLIGHT_NUMBER_PATTERN = re.compile(r"(?:Delta)?DL\s*([0-9]{1,4})\b", re.IGNORECASE)
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
TIME_PATTERN = re.compile(
    r"(?i)\b([A-Za-z]{3})\s+(\d{1,2})\s*[—-]\s*(\d{1,2}):(\d{2})\s*([ap])\.m\."
)
NEXT_PAGE_PATTERN = re.compile(r"[?&]page=(\d+)")
MAX_PAGES = 6


def fetch_delta_departures_html(timeout: float = 20.0) -> str:
    pages: list[str] = []
    for page in range(MAX_PAGES):
        html = fetch_flights_page(page=page, timeout=timeout)
        pages.append(html)
        if not has_next_page(html, page):
            break
    return "\n".join(pages)


def fetch_flights_ajax(timeout: float = 20.0) -> list[dict]:
    request = Request(
        f"{MSP_AJAX_URL}?{urlencode(MSP_VIEW_PARAMS)}",
        headers=AJAX_HEADERS,
    )
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)

    if not isinstance(payload, list):
        raise RuntimeError("MSP AJAX response was not a JSON array.")
    return payload


def extract_ajax_markup(commands: list[dict]) -> str:
    insert_payloads = [
        command.get("data", "")
        for command in commands
        if isinstance(command, dict)
        and command.get("command") == "insert"
        and isinstance(command.get("data"), str)
    ]
    if not insert_payloads:
        return ""

    ranked = sorted(insert_payloads, key=lambda item: (has_gate_rows(item), len(item)), reverse=True)
    return ranked[0]


def fetch_flights_page(page: int = 0, timeout: float = 20.0) -> str:
    params = dict(MSP_QUERY_PARAMS)
    params["page"] = str(page)
    request = Request(
        f"{MSP_FLIGHTS_URL}?{urlencode(params)}",
        headers=MSP_HEADERS,
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_departure_rows(markup: str, now: datetime | None = None) -> list[dict]:
    current = now.astimezone(CHICAGO) if now else datetime.now(CHICAGO)
    rows: list[dict] = []

    for row_html in ROW_PATTERN.findall(markup):
        raw_gate = _extract_raw_gate(row_html)
        if raw_gate is None:
            continue

        departure_time_text = _extract_cell_text(row_html, "views-field-scheduled-time")
        destination_text = _extract_cell_text(row_html, "views-field-city-airport")
        flight_text = _extract_cell_text(row_html, "views-field-airline")
        if not departure_time_text or not destination_text or not flight_text:
            continue

        if parse_flight_number(flight_text) is None:
            continue

        departure_time = parse_departure_time(departure_time_text, now=current)
        flight_number = parse_flight_number(flight_text)
        if departure_time is None or flight_number is None:
            continue

        destination = parse_destination(destination_text)
        rows.append(
            {
                "dep_gate": raw_gate,
                "dep_time": departure_time.strftime("%Y-%m-%d %H:%M"),
                "dep_time_ts": int(departure_time.timestamp()),
                "arr_iata": destination,
                "flight_iata": f"DL{flight_number}",
                "flight_number": flight_number,
            }
        )

    return rows


def has_gate_rows(markup: str) -> bool:
    return bool(RAW_GATE_PATTERN.search(markup))


def has_next_page(markup: str, current_page: int) -> bool:
    matches = [int(value) for value in NEXT_PAGE_PATTERN.findall(unescape(markup))]
    return any(page > current_page for page in matches)


def parse_departure_time(value: str, now: datetime | None = None) -> datetime | None:
    current = now.astimezone(CHICAGO) if now else datetime.now(CHICAGO)
    match = TIME_PATTERN.search(value)
    if not match:
        return None

    month_text, day_text, hour_text, minute_text, meridiem = match.groups()
    month = MONTHS.get(month_text.lower())
    if month is None:
        return None

    hour = int(hour_text)
    if meridiem.lower() == "p" and hour != 12:
        hour += 12
    if meridiem.lower() == "a" and hour == 12:
        hour = 0

    parsed = datetime(
        current.year,
        month,
        int(day_text),
        hour,
        int(minute_text),
        tzinfo=CHICAGO,
    )

    if parsed - current > timedelta(days=330):
        return parsed.replace(year=parsed.year - 1)
    if current - parsed > timedelta(days=35):
        return parsed.replace(year=parsed.year + 1)
    return parsed


def parse_destination(value: str) -> str:
    cleaned = _clean_text(value)
    match = DESTINATION_CODE_PATTERN.search(cleaned)
    if match:
        return match.group(1)
    return cleaned or "UNK"


def parse_flight_number(value: str) -> str | None:
    cleaned = _clean_text(value)
    match = FLIGHT_NUMBER_PATTERN.search(cleaned)
    if match:
        return match.group(1)
    return None


def _extract_raw_gate(row_html: str) -> str | None:
    match = RAW_GATE_PATTERN.search(_clean_text(row_html))
    if match:
        return f"T1G{match.group(1)}"
    return None


def _extract_cell_text(row_html: str, marker: str) -> str | None:
    match = re.search(CELL_TEMPLATE.format(marker=re.escape(marker)), row_html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return _clean_text(match.group(1))


def _clean_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


AIRLABS_URL = "https://airlabs.co/api/v9/schedules"
AIRLABS_FIELDS = [
    "dep_gate",
    "dep_time",
    "dep_time_ts",
    "dep_estimated",
    "dep_estimated_ts",
    "arr_iata",
    "status",
    "flight_iata",
    "flight_number",
    "airline_iata",
    "cs_flight_iata",
    "cs_flight_number",
    "cs_airline_iata",
]


def build_schedules_url(api_key: str, dep_iata: str = "MSP", limit: int = 1000) -> str:
    query = urlencode(
        {
            "dep_iata": dep_iata,
            "limit": str(limit),
            "_fields": ",".join(AIRLABS_FIELDS),
            "api_key": api_key,
        }
    )
    return f"{AIRLABS_URL}?{query}"


def fetch_schedules(api_key: str, dep_iata: str = "MSP", limit: int = 1000, timeout: float = 20.0) -> dict:
    request = Request(
        build_schedules_url(api_key=api_key, dep_iata=dep_iata, limit=limit),
        headers={"User-Agent": "mspage-gcon/0.1"},
    )

    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)

    if not isinstance(payload, dict):
        raise RuntimeError("AirLabs response was not a JSON object.")

    error_message = _extract_error(payload)
    if error_message:
        raise RuntimeError(f"AirLabs error: {error_message}")

    rows = payload.get("response")
    if not isinstance(rows, list):
        raise RuntimeError("AirLabs response did not contain a 'response' list.")

    return payload


def _extract_error(payload: dict) -> str | None:
    message = payload.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()

    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        return error.strip()
    if isinstance(error, dict):
        nested = error.get("message")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()

    return None

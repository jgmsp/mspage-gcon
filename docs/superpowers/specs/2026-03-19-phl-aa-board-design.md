# PHL AA Board Draft Design

## Goal

Add a PHL-specific draft board alongside the existing MSP app without changing MSP behavior. The draft focuses on American Airlines departures currently assigned to Terminal B or Terminal F, plus a separate Stats tab that records same-day gate moves between Terminal B and Terminal C.

## Product Behavior

- The PHL draft lives under `docs/phl/` as a separate static app.
- The Ops view shows only current AA departures whose gates begin with `B` or `F`.
- A top-level terminal toggle switches the live board between `TB` and `TF`.
- The venue panel follows the selected terminal:
  - `TB` shows the Terminal B venue list.
  - `TF` shows the Terminal F venue list.
- Stats is a separate tab, not tied to the terminal toggle.
- Stats only tracks `TB <-> TC` movement.
- A movement is recorded when the same AA flight number is observed on the same Chicago calendar day with a prior terminal in `B` or `C` and a current terminal in the other one.

## Data Model

- `docs/phl/ops.json`
  - current AA departures filtered to terminals `B` and `F`
  - terminal definitions and venue metadata used by the frontend
- `docs/phl/stats.json`
  - service date
  - summary counts for `gainedFromC` and `lostToC`
  - same-day event log including flight number, previous gate, current gate, scheduled departure time, and detection timestamp
  - current flight-position ledger used to avoid double-counting repeated snapshots
- `docs/phl/diagnostics.json`
  - same freshness contract as MSP

## Fetch and Parse

- Source page: `https://www.phl.org/flights`
- Parse the server-rendered departures table `#flight_feed_departures_table`.
- Ignore client-side airline filters and DataTables behavior; the generator fetches full departures HTML and filters rows in Python.
- Keep only `American Airlines` rows with gate prefixes `B`, `C`, or `F`.
- Ops output keeps only `B` and `F`.
- Stats comparison keeps `B` and `C`.

## State and Logging

- Stats state resets when the local Chicago service date changes.
- Flight identity for the draft is the AA flight display value, for example `AA 1809`.
- Each event is appended once per distinct terminal transition so repeated hourly snapshots do not duplicate the same move.

## Failure Handling

- If the PHL fetch or parse fails, preserve the last good PHL outputs.
- If a parse returns suspiciously few AA terminal rows compared with the previous snapshot, write degraded diagnostics and keep the last good files.
- MSP outputs and MSP code paths remain untouched by PHL failures.

## Testing

- Add parser tests for PHL departures HTML.
- Add pipeline tests for:
  - filtering to `TB` and `TF`
  - building the venue-aware ops payload
  - detecting `TB -> TC` and `TC -> TB` moves once per day
  - resetting stats state on a new day
- Add a smoke test that the PHL app shell can render from its JSON artifacts.

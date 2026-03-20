# mspage-gcon

MSP Terminal 1 Concourse G departures for in-house operations and finance.

This project is intentionally small. It turns public MSP Delta departure data into a single canonical site payload plus one frozen finance snapshot used as a foot-traffic planning signal.

## Canonical Contract

- `docs/ops.json` is the canonical source of truth.
- `docs/finance.txt` is the official frozen finance snapshot rendered from the same canonical departures model.
- `docs/diagnostics.json` publishes minimal freshness data used by the site footer:
  - current health status
  - last successful publish time
  - stale threshold in minutes
- The site is a live operations board.
- The finance view is a frozen planning artifact, not a continuously updating live report.

## Data Scope

- Source: MSP public flights page
- Airline: `DL`
- Concourse scope: `T1G1` through `T1G22`
- Pod mapping: `config/pods.json`

## Publish Rules

GitHub Actions runs hourly at `:50` in UTC. The generator always refreshes the canonical ops payload on each run.

Finance follows fixed America/Chicago rules:

- `5:50 AM` local: publish the AM finance snapshot
- `12:50 PM` local: publish the PM finance snapshot
- `6:50 PM` local: clear/hide finance for the rest of the day

Manual workflow dispatch follows the same finance rules:

- ops refreshes immediately
- finance changes only at `5:50 AM`, `12:50 PM`, or `6:50 PM` local

## Failure Handling

- If fetch or parse fails, the project keeps the last known good published outputs.
- A failed refresh updates diagnostics so the site can show degraded or stale state.
- The site warns on stale data after `180 minutes` without a successful publish.
- Suspiciously incomplete parses are rejected instead of replacing the last good snapshot.

## Finance Review Tool

The site includes a finance compare tool inside the Finance view.

- Trigger: `Check for diffs`
- Availability: visible whenever the Finance view is visible
- Behavior: refetch the latest `ops.json`, derive a candidate finance view, and compare it against the official frozen finance snapshot
- Diff mode is read-only
- The browser does not publish or rewrite `finance.txt`

### Diff Contract

The finance diff is layered on top of the official frozen finance snapshot.

- Base layer: unchanged official `finance.txt` rows remain plain and visible.
- Green means the current flights run has a new truth not present in the official snapshot.
  - new flight
  - moved flight replacement row
  - changed gate/time replacement row
- Red means the official snapshot contains a truth that is no longer current.
  - removed flight
  - cancelled flight
  - old gate/time row being replaced
- Changed gate or time: render the official row as the base, then attach:
  - one red overlay row for the old value
  - one green overlay row for the new value
- Diff mode stays static and red/green only. It does not use inline token diffs, browser-side mutation, or row-reveal animation.

## Pod Configuration

`config/pods.json` must cover every gate from `G1` through `G22` exactly once.

The loader rejects:

- overlapping ranges
- duplicate pod IDs
- reversed ranges
- invalid fields
- out-of-scope gates
- incomplete coverage

Default mapping:

- Pod 1: `G1-G8`
- Pod 2: `G9-G10`
- Pod 3: `G11-G13`
- Pod 4: `G14-G16`
- Pod 5: `G17-G22`

## Local Preview

Use a simple local server from the repo root:

```bash
cd /Users/grim/p-projects/mspage-gcon
python3 -m http.server
```

Then open:

- `http://localhost:8000/docs/`
- `http://localhost:8000/docs/phl/`

## PHL Draft

The repo also includes a separate PHL draft board for American Airlines.

- App path: `docs/phl/`
- Ops scope: Terminal `B` and Terminal `F` AA departures
- Stats scope: same-day `TB <-> TC` moves by AA flight number
- Venue config: `config/phl_terminals.json`

Generate the PHL draft outputs from the repo root:

```bash
cd /Users/grim/p-projects/mspage-gcon
python3 -m mspage_gcon.phl_main
```

## Development Check

```bash
cd /Users/grim/p-projects/mspage-gcon
python3 -m unittest discover -s tests -t .
```

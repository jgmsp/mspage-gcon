# mspage-gcon

Latest-only MSP Terminal 1 Concourse G departures, 
a GitHub Pages site plus a plain-text finance export.

## What It Does

- Fetches MSP flights from the public flights view for:
  - `departures`
  - airline `DL`
- Parses returned Delta departures and keeps only `T1G1` through `T1G22`
- Assigns each gate to a configurable pod
- Publishes:
  - `docs/index.html` for operations
  - `docs/ops.json` for the site data payload
  - `docs/finance.txt` as a same-day cumulative finance log

The workflow is designed so GitHub Actions is the only scheduled source fetcher. No API key is required for the MSP public flights source.


## Pod Configuration

Edit `config/pods.json` to change gate ranges.

Default mapping:

- Pod 1: `G1-G9`
- Pod 4: `G10-G16`
- Pod 5: `G17-G22`

## Scheduling

GitHub Actions cron uses UTC, so the workflow wakes hourly at minute `17` and the generator only performs the MSP fetch when local Chicago time is inside the configured hours. Automatic refreshes currently land around:

- `3:17 AM`
- `8:17 AM`
- `1:17 PM`
- `5:17 PM`
- `8:17 PM`

Manual workflow dispatch bypasses the schedule gate.

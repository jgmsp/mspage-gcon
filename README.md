# mspage-gcon

Latest-only MSP Terminal 1 Concourse G departures, 
a GitHub Pages site plus a plain-text finance export.

## What It Does

- Fetches `MSP` departures from the AirLabs `schedules` API
- Keeps only `G1` through `G22`
- Collapses codeshares into one physical departure
- Assigns each gate to a configurable pod
- Publishes:
  - `docs/index.html` for operations
  - `docs/ops.json` for the site data payload
  - `docs/finance.txt` for finance

The workflow is designed so GitHub Actions is the only AirLabs caller. The API key stays in GitHub Secrets and never ships with the generated site.


## Pod Configuration

Edit `config/pods.json` to change gate ranges.

Default mapping:

- Pod 1: `G1-G7`
- Pod 3: `G8-G16`
- Pod 5: `G17-G22`

## Scheduling

GitHub Actions cron uses UTC, so the workflow runs hourly and the generator only performs the AirLabs fetch when local Chicago time is inside the configured hours. Defaults:

- `4:00 AM`
- `1:00 PM`

Manual workflow dispatch bypasses the schedule gate.

# PHL AA Board Draft Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a separate PHL draft board for American Airlines Terminal B and F departures, with a separate Stats tab that records same-day Terminal B to Terminal C gains and losses.

**Architecture:** Keep MSP intact and add a PHL-only generator plus static frontend under `docs/phl/`. Reuse the existing publish and diagnostics patterns, but store a dedicated `stats.json` ledger for same-day `TB <-> TC` transitions.

**Tech Stack:** Python stdlib fetch/parsing, JSON artifacts in `docs/phl/`, vanilla HTML/CSS/JS, `pytest`/`unittest`.

---

## Chunk 1: PHL Backend Contracts

### Task 1: Add failing parser and pipeline tests

**Files:**
- Create: `tests/fixtures/phl_departures_sample.html`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing tests for PHL row parsing**
- [ ] **Step 2: Run the targeted parser tests and verify they fail**
- [ ] **Step 3: Write failing tests for PHL ops payload and TB/TC movement tracking**
- [ ] **Step 4: Run the targeted pipeline tests and verify they fail**

### Task 2: Implement PHL fetch and parse modules

**Files:**
- Create: `mspage_gcon/phl.py`

- [ ] **Step 1: Implement fetch for `https://www.phl.org/flights`**
- [ ] **Step 2: Parse `#flight_feed_departures_table` rows into AA departure records**
- [ ] **Step 3: Filter rows to terminal prefixes `B`, `C`, and `F`**
- [ ] **Step 4: Run targeted parser tests and verify they pass**

### Task 3: Implement PHL pipeline and stats ledger

**Files:**
- Create: `mspage_gcon/phl_pipeline.py`

- [ ] **Step 1: Implement ops payload builder for `TB` and `TF`**
- [ ] **Step 2: Implement stats ledger load/update/write for same-day `TB <-> TC` events**
- [ ] **Step 3: Implement diagnostics and last-good fallback helpers for PHL outputs**
- [ ] **Step 4: Run targeted pipeline tests and verify they pass**

## Chunk 2: PHL Generator Entry Point

### Task 4: Add a runnable PHL generator command

**Files:**
- Create: `mspage_gcon/phl_main.py`

- [ ] **Step 1: Add a CLI entry point that writes to `docs/phl` by default**
- [ ] **Step 2: Wire fetch, parse, suspicious-parse protection, output writing, and diagnostics**
- [ ] **Step 3: Add or update tests for the CLI flow if needed**
- [ ] **Step 4: Run PHL-focused tests and verify they pass**

## Chunk 3: PHL Frontend

### Task 5: Add the static PHL app shell

**Files:**
- Create: `docs/phl/index.html`
- Create: `docs/phl/styles.css`
- Create: `docs/phl/app.js`
- Create: `docs/phl/ops.json`
- Create: `docs/phl/stats.json`
- Create: `docs/phl/diagnostics.json`

- [ ] **Step 1: Build a separate PHL page shell with `Ops` and `Stats` tabs**
- [ ] **Step 2: Add the `TB` / `TF` toggle and terminal-reactive venue panel**
- [ ] **Step 3: Add Stats summary and event log rendering from `stats.json`**
- [ ] **Step 4: Run a local smoke check against generated JSON**

### Task 6: Document the draft workflow

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Document the new PHL draft artifacts and command**
- [ ] **Step 2: Add local preview guidance for `docs/phl/`**
- [ ] **Step 3: Run the full test suite**
- [ ] **Step 4: Commit the draft implementation**

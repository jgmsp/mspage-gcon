const state = {
  payload: null,
  financeText: null,
  diagnostics: null,
  activeFilter: "all",
  activeTheme: readStorage("mspage-gcon-theme") || "light",
  lastView: null,
  diffOpen: false,
  diffLoading: false,
  diffResult: null,
  lastDiffCueState: null,
};

const params = new URLSearchParams(window.location.search);
const snapshotPath = params.get("snapshot") || "./ops.json";
const financePath = params.get("finance") || "./finance.txt";
const diagnosticsPath = params.get("diagnostics") || "./diagnostics.json";
const compareSnapshotPath = params.get("compareSnapshot") || snapshotPath;
const previewNow = readPreviewNow(params.get("previewNow"));
const animeApi = window.anime || {};
const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;

const themeCycle = document.getElementById("theme-cycle");
const departuresHead = document.getElementById("departures-head");
const departuresBody = document.getElementById("departures-body");
const podFilters = document.getElementById("pod-filters");
const heroToolbar = document.querySelector(".hero-toolbar");
const tableWrap = document.querySelector(".table-wrap");
const board = document.querySelector(".board");
const lastUpdatedInline = document.getElementById("last-updated-inline");
const visibleCount = document.getElementById("visible-count");
const emptyState = document.getElementById("empty-state");
const boardTitle = document.getElementById("board-title");
const boardNote = document.getElementById("board-note");
const financePlain = document.getElementById("finance-plain");
const financeDiff = document.getElementById("finance-diff");
const financeDiffTitle = document.getElementById("finance-diff-title");
const financeDiffMeta = document.getElementById("finance-diff-meta");
const financeDiffSummary = document.getElementById("finance-diff-summary");
const financeDiffList = document.getElementById("finance-diff-list");
const statusLine = document.getElementById("status-line");

const THEMES = [
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
  { id: "slate", label: "Slate" },
  { id: "plum", label: "Plum" },
  { id: "marine", label: "Marine" },
  { id: "olive", label: "Olive" },
  { id: "ember", label: "Ember" },
];

const THEME_ICONS = {
  light:
    '<svg viewBox="0 0 24 24" role="presentation" focusable="false"><circle cx="12" cy="12" r="3.8" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 2.8v2.4M12 18.8v2.4M21.2 12h-2.4M5.2 12H2.8M18.5 5.5l-1.7 1.7M7.2 16.8l-1.7 1.7M18.5 18.5l-1.7-1.7M7.2 7.2L5.5 5.5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/></svg>',
  dark:
    '<svg viewBox="0 0 24 24" role="presentation" focusable="false"><path d="M15.8 3.6a8.8 8.8 0 1 0 4.6 15.8a8.4 8.4 0 0 1-10.1-10.1a8.6 8.6 0 0 1 5.5-5.7Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.8"/></svg>',
  slate:
    '<svg viewBox="0 0 24 24" role="presentation" focusable="false"><path d="M5 16.5L12 12l7 4.5L12 21zM5 9.5L12 5l7 4.5L12 14z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.7"/></svg>',
  plum:
    '<svg viewBox="0 0 24 24" role="presentation" focusable="false"><path d="M12.2 5.2c2.7 0 5.8 2 5.8 6.1c0 4.8-3 7.5-6.1 7.5c-3.8 0-6.2-3.2-6.2-7.1c0-4 2.9-6.5 6.5-6.5Z" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12.1 5.4c.4-1.2 1.4-2 2.7-2.2m-2.5 2c-1.4-.1-2.6-.7-3.4-1.8" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/></svg>',
  marine:
    '<svg viewBox="0 0 24 24" role="presentation" focusable="false"><path d="M3.2 14.4c1.5-1.8 3-2.7 4.6-2.7c1.8 0 2.8 1.1 4.2 1.1c1.6 0 2.7-1.7 4.6-1.7c1.5 0 2.8.8 4.2 2.3m-17.6 4c1.5-1.8 3-2.7 4.6-2.7c1.8 0 2.8 1.1 4.2 1.1c1.6 0 2.7-1.7 4.6-1.7c1.5 0 2.8.8 4.2 2.3" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.7"/></svg>',
  olive:
    '<svg viewBox="0 0 24 24" role="presentation" focusable="false"><path d="M6.2 18.2c5.3-2 8.3-5.7 9.2-11.3c2.2 2.1 2.9 5 2.1 8.1c-.9 3.3-3.5 5.4-7 5.8c-1.6.2-3-.5-4.3-2.6Z" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M8.1 19.2c2.2-2.4 4.3-4.9 6.1-7.9" fill="none" stroke="currentColor" stroke-linecap="round" stroke-width="1.8"/></svg>',
  ember:
    '<svg viewBox="0 0 24 24" role="presentation" focusable="false"><path d="M12.2 3.8c1.1 2 1.2 3.4.2 5.1c1.9-.5 3.4-1.8 4.2-3.8c2.4 2.2 3.7 4.8 3.7 7.6c0 4.2-3.2 7.4-7.7 7.4c-4.8 0-8-3.4-8-7.8c0-3 1.4-5.7 4.2-8.2c.1 2 .8 3.4 2 4.5c1-1.2 1.4-2.8 1.4-4.8Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.7"/></svg>',
};

const FINANCE_VISIBLE_START = 5 * 60;
const FINANCE_VISIBLE_END = 18 * 60;
const FINANCE_COMPARE_WINDOWS = [
  { start: 5 * 60, end: 9 * 60, label: "AM Review Window" },
  { start: 12 * 60, end: 15 * 60, label: "PM Review Window" },
];

applyTheme(state.activeTheme);
bindEvents();
loadSnapshot().catch((error) => {
  console.error(error);
  emptyState.classList.remove("hidden");
  emptyState.textContent = "Unable to load the current snapshot.";
  renderStatusFooter();
});

setInterval(() => {
  if (!state.payload) {
    return;
  }
  render();
}, 60000);

function bindEvents() {
  themeCycle?.addEventListener("click", cycleTheme);
}

async function loadSnapshot() {
  const [snapshotResponse, financeResponse, diagnosticsResponse] = await Promise.all([
    fetchAsset(snapshotPath),
    fetchAsset(financePath),
    fetchAsset(diagnosticsPath),
  ]);

  if (!snapshotResponse.ok) {
    throw new Error(`Failed to load ops snapshot: ${snapshotResponse.status}`);
  }

  state.payload = await snapshotResponse.json();
  state.financeText = financeResponse.ok ? await financeResponse.text() : renderFinanceTextFromPayload(state.payload);
  state.diagnostics = diagnosticsResponse.ok ? await diagnosticsResponse.json() : buildFallbackDiagnostics();
  render();
}

function render() {
  board?.classList.toggle("finance-mode", isFinanceView());
  renderMeta();
  renderPodFilters();
  renderHead();
  renderRows();
  renderFinanceTools();
  renderStatusFooter();
}

function renderMeta() {
  const generatedAt = state.payload?.generatedAt;
  updateThemeControl(currentTheme());
  if (!generatedAt) {
    lastUpdatedInline.textContent = "Awaiting snapshot";
    return;
  }

  lastUpdatedInline.textContent = `Updated ${formatChicagoTime(new Date(generatedAt))} · MSP DL`;
}

function renderPodFilters() {
  const pods = state.payload?.pods ?? [];
  const includeFinance = !shouldHideFinanceFilter();
  if (!includeFinance && state.activeFilter === "finance") {
    state.activeFilter = "all";
    state.diffOpen = false;
  }

  const definitions = [
    { id: "all", label: "All" },
    ...pods.map((pod) => ({ id: pod.id, label: pod.label })),
    ...(includeFinance ? [{ id: "finance", label: "Finance" }] : []),
  ];
  syncFilterButtons(definitions);

  ensureFilterIndicator();
  updateFilterIndicator();
  animateFinancePillCue();
}

function syncFilterButtons(definitions) {
  const existing = new Map(
    Array.from(podFilters.querySelectorAll("button")).map((button) => [filterButtonKey(button), button])
  );
  const orderedButtons = definitions.map((definition) => {
    const key = `filter:${definition.id}`;
    const button = existing.get(key) || createFilterButton();
    updateFilterButton(button, definition.id, definition.label, state.activeFilter === definition.id);
    existing.delete(key);
    return button;
  });

  if (isFinanceView() && isFinanceCompareAvailable() && !state.diffOpen) {
    const subpill = existing.get("control:finance-subpill") || createFinanceSubpill();
    orderedButtons.push(subpill);
    existing.delete("control:finance-subpill");
  }

  orderedButtons.forEach((button) => podFilters.appendChild(button));
  existing.forEach((button) => button.remove());
}

function filterButtonKey(button) {
  if (button.dataset.controlId) {
    return `control:${button.dataset.controlId}`;
  }
  return `filter:${button.dataset.filterId}`;
}

function createFilterButton(id, label, active) {
  const button = document.createElement("button");
  button.type = "button";
  button.addEventListener("click", () => {
    const filterId = button.dataset.filterId;
    if (filterId === "finance" && state.activeFilter === filterId && state.diffOpen) {
      closeFinanceDiff();
      return;
    }
    if (state.activeFilter === filterId) {
      return;
    }
    state.activeFilter = filterId;
    if (filterId !== "finance") {
      state.diffOpen = false;
    }
    render();
  });
  return button;
}

function updateFilterButton(button, id, label, active) {
  button.dataset.filterId = id;
  button.dataset.controlId = "";
  button.className = active ? "pill active" : "pill";
  button.textContent = financeFilterLabel(id, label, active);
}

function financeFilterLabel(id, label, active) {
  if (id === "finance" && active && state.diffOpen) {
    return "Finance - Diffs";
  }
  return label;
}

function renderHead() {
  const financeView = isFinanceView();
  const nextView = financeView ? "finance" : "ops";
  boardTitle.textContent = financeView ? "Finance View" : "Operations View";

  if (financeView) {
    setFinanceHeading(financeBoardNote());
    boardNote.classList.add("hidden");
    visibleCount.classList.add("hidden");
    departuresHead.replaceChildren();
    state.lastView = nextView;
    return;
  }

  visibleCount.classList.remove("hidden");
  const tr = document.createElement("tr");
  ["Time", "Gate", "Dest"].forEach((header) => {
    const th = document.createElement("th");
    th.textContent = header;
    tr.appendChild(th);
  });
  departuresHead.replaceChildren(tr);
  state.lastView = nextView;
}

function renderRows() {
  const departures = getVisibleDepartures();
  if (isFinanceView()) {
    renderFinancePlainText();
    return;
  }

  financePlain.classList.add("hidden");
  financeDiff.classList.add("hidden");
  tableWrap.classList.remove("hidden");

  const existingRows = new Map(
    Array.from(departuresBody.querySelectorAll(".board-row")).map((row) => [row.dataset.rowKey, row])
  );

  setFlightsCount(departures.length);
  updateOpsBoardNote(departures);

  emptyState.classList.toggle("hidden", departures.length > 0);

  const fragment = document.createDocumentFragment();
  departures.forEach((departure, index) => {
    const row = existingRows.get(departure.id) || document.createElement("tr");
    row.dataset.rowKey = departure.id;
    row.dataset.rowIndex = String(index);
    row.className = "board-row";

    const urgencyBand = getUrgencyBand(departure);
    if (urgencyBand) {
      row.classList.add("is-window", `is-window-${urgencyBand}`);
    }

    updateRowContent(row, departure);
    fragment.appendChild(row);
  });

  departuresBody.replaceChildren(fragment);
  animateRedAlertSweep();
}

function renderFinancePlainText() {
  const financeText = state.financeText ?? renderFinanceTextFromPayload(state.payload);
  const officialEntries = parseFinanceRows(financeText);
  departuresBody.replaceChildren();
  emptyState.classList.add("hidden");
  tableWrap.classList.add("hidden");
  financePlain.classList.remove("hidden");
  if (state.diffOpen && !state.diffLoading && state.diffResult?.hasChanges) {
    financePlain.classList.add("is-diff");
    const nodes = buildFinanceLayeredNodes(state.diffResult.records);
    financePlain.replaceChildren(...nodes);
  } else {
    financePlain.classList.remove("is-diff");
    if (officialEntries.length) {
      financePlain.replaceChildren(...buildFinanceBaseNodes(officialEntries));
    } else {
      financePlain.textContent = financeText;
    }
  }
  renderFinanceDiff();
}

function renderFinanceTools() {
  heroToolbar?.classList.toggle("finance-toolbar", isFinanceView() && isFinanceCompareAvailable());
}

async function runFinanceDiff() {
  if (!isFinanceCompareAvailable()) {
    return;
  }

  state.diffLoading = true;
  state.diffOpen = true;
  state.diffResult = {
    title: "Checking for changes",
    meta: "Fetching the current flights run...",
    summary: [],
    records: [],
    hasChanges: false,
  };
  render();

  try {
    const response = await fetchAsset(compareSnapshotPath);
    if (!response.ok) {
      throw new Error(`Unable to refetch ops snapshot (${response.status})`);
    }

    const candidatePayload = await response.json();
    const officialEntries = parseFinanceRows(state.financeText ?? renderFinanceTextFromPayload(state.payload));
    const candidateEntries = buildFinanceEntriesFromPayload(candidatePayload);
    const diff = diffFinanceEntries(officialEntries, candidateEntries);
    const generatedAt = candidatePayload?.generatedAt ? new Date(candidatePayload.generatedAt) : null;

    state.diffResult = buildDiffResult(diff, officialEntries, candidateEntries, generatedAt);
  } catch (error) {
    state.diffResult = {
      title: "Unable to compare right now",
      meta: String(error?.message || error),
      summary: [],
      records: [],
      hasChanges: false,
      error: true,
    };
  } finally {
    state.diffLoading = false;
    render();
  }
}

function closeFinanceDiff() {
  state.diffOpen = false;
  render();
}

function createFinanceSubpill() {
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.controlId = "finance-subpill";
  button.className = state.diffOpen ? "pill finance-subpill active" : "pill finance-subpill";
  button.textContent = state.diffLoading ? "Checking..." : "Diffs";
  button.disabled = state.diffLoading;
  button.setAttribute("aria-pressed", state.diffOpen ? "true" : "false");
  button.addEventListener("click", () => {
    if (state.diffLoading) {
      return;
    }
    if (state.diffOpen) {
      closeFinanceDiff();
      return;
    }
    runFinanceDiff();
  });
  return button;
}

function renderFinanceDiff() {
  if (!state.diffOpen || (state.diffResult?.hasChanges && !state.diffResult?.error)) {
    financeDiff.classList.add("hidden");
    return;
  }

  const result =
    state.diffResult ||
    {
      title: "No changes detected",
      meta: "Official finance snapshot matches the recent flights run.",
      summary: [],
      records: [],
      hasChanges: false,
    };

  financeDiffTitle.textContent = result.title;
  financeDiffMeta.textContent = result.meta || "";
  financeDiffSummary.replaceChildren();
  financeDiffList.replaceChildren();

  financeDiff.classList.remove("hidden");
}

function buildDiffResult(diff, officialEntries, candidateEntries, generatedAt) {
  const meta = generatedAt
    ? `Recent flights run from ${formatChicagoTime(generatedAt)}`
    : "Recent flights run loaded for comparison.";

  const hasChanges = diff.changed.length + diff.added.length + diff.removed.length > 0;

  if (!hasChanges) {
    return {
      title: "No changes detected",
      meta,
      summary: [],
      records: [],
      hasChanges: false,
    };
  }

  return {
    title: "Differences found",
    meta,
    summary: [],
    records: buildFinanceDiffRecords(officialEntries, candidateEntries),
    hasChanges: true,
  };
}

function buildFinanceBaseNodes(entries) {
  const widths = measureFinanceWidths(entries);
  const header = document.createElement("span");
  header.className = "finance-table-line finance-table-line-header";
  header.textContent = formatFinanceHeader(widths);

  const rows = entries.map((entry) => {
    const row = document.createElement("span");
    row.className = "finance-table-line finance-record-base";
    row.textContent = formatFinanceLine(entry, widths);
    return row;
  });

  return [header, ...rows];
}

function buildFinanceLayeredNodes(layered) {
  const header = document.createElement("span");
  header.className = "finance-table-line finance-table-line-header";
  header.textContent = layered.headerLine;

  const rows = layered.records.map((record) => {
    const wrapper = document.createElement("div");
    wrapper.className = "finance-record";

    if (record.baseLine) {
      const base = document.createElement("span");
      base.className = "finance-record-base";
      base.textContent = record.baseLine;
      wrapper.appendChild(base);
    }

    if (record.overlays.length) {
      const overlays = document.createElement("div");
      overlays.className = "finance-record-overlays";
      record.overlays.forEach((item) => overlays.appendChild(buildFinanceOverlayLineNode(item)));
      wrapper.appendChild(overlays);
    }

    return wrapper;
  });

  return [header, ...rows];
}

function buildFinanceOverlayLineNode(item) {
  const row = document.createElement("span");
  row.className = `finance-overlay-line finance-overlay-line-${item.kind}`;

  const prefix = document.createElement("span");
  prefix.className = `diff-line-prefix diff-line-prefix-${item.kind}`;
  prefix.textContent = `${item.kind === "added" ? "+" : "-"} `;

  const content = document.createElement("span");
  content.className = `diff-line-content diff-line-content-${item.kind}`;
  const text = document.createElement("span");
  text.className = item.kind === "removed" ? "diff-line-text diff-line-text-removed" : "diff-line-text";
  text.textContent = item.line;
  content.appendChild(text);

  if (item.kind === "removed") {
    const strike = document.createElement("span");
    strike.className = "diff-strike-draw";
    strike.setAttribute("aria-hidden", "true");
    content.appendChild(strike);
  }

  row.classList.add("diff-reveal-line");
  row.dataset.diffKind = item.kind;
  row.append(prefix, content);
  return row;
}

function buildFinanceDiffRecords(officialEntries, candidateEntries) {
  const widths = measureFinanceWidths([...officialEntries, ...candidateEntries]);
  const officialMap = new Map(keyFinanceEntries(officialEntries).map((entry) => [entry.key, entry]));
  const candidateMap = new Map(keyFinanceEntries(candidateEntries).map((entry) => [entry.key, entry]));
  const records = [];
  const keys = new Set([...officialMap.keys(), ...candidateMap.keys()]);

  for (const key of keys) {
    const official = officialMap.get(key);
    const candidate = candidateMap.get(key);

    if (official && candidate) {
      if (sameFinanceEntry(official, candidate)) {
        records.push({
          sortKey: financeEntrySortKey(candidate),
          baseLine: formatFinanceLine(candidate, widths),
          overlays: [],
        });
        continue;
      }

      records.push({
        sortKey: [financeEntrySortKey(official), financeEntrySortKey(candidate)].sort()[0],
        baseLine: formatFinanceLine(official, widths),
        overlays: [
          { kind: "removed", line: formatFinanceLine(official, widths) },
          { kind: "added", line: formatFinanceLine(candidate, widths) },
        ],
      });
      continue;
    }

    if (candidate) {
      records.push({
        sortKey: financeEntrySortKey(candidate),
        baseLine: "",
        overlays: [{ kind: "added", line: formatFinanceLine(candidate, widths) }],
      });
      continue;
    }

    if (official) {
      records.push({
        sortKey: financeEntrySortKey(official),
        baseLine: formatFinanceLine(official, widths),
        overlays: [{ kind: "removed", line: formatFinanceLine(official, widths) }],
      });
    }
  }

  records.sort((left, right) => left.sortKey.localeCompare(right.sortKey));

  return {
    headerLine: formatFinanceHeader(widths),
    records,
  };
}

function measureFinanceWidths(entries) {
  const headers = ["Flight", "Gate", "Time"];
  const widths = headers.map((header) => header.length);

  entries.forEach((entry) => {
    [entry.flightDisplay, String(entry.gateNumber), entry.timeDisplayFinance].forEach((value, index) => {
      widths[index] = Math.max(widths[index], value.length);
    });
  });

  return widths;
}

function formatFinanceHeader(widths) {
  return ["Flight", "Gate", "Time"]
    .map((header, index) => header.padEnd(widths[index], " "))
    .join(" | ")
    .trimEnd();
}

function formatFinanceLine(entry, widths) {
  return [entry.flightDisplay, String(entry.gateNumber), entry.timeDisplayFinance]
    .map((value, index) => value.padEnd(widths[index], " "))
    .join(" | ")
    .trimEnd();
}

function financeEntrySortKey(entry) {
  return `${entry.timeDisplayFinance}\t${String(entry.gateNumber).padStart(2, "0")}\t${entry.flightDisplay}`;
}

function sameFinanceEntry(left, right) {
  return (
    left.flightDisplay === right.flightDisplay &&
    left.gateNumber === right.gateNumber &&
    left.timeDisplayFinance === right.timeDisplayFinance
  );
}

function diffFinanceEntries(officialEntries, candidateEntries) {
  const keyedOfficial = keyFinanceEntries(officialEntries);
  const keyedCandidate = keyFinanceEntries(candidateEntries);
  const officialMap = new Map(keyedOfficial.map((entry) => [entry.key, entry]));
  const candidateMap = new Map(keyedCandidate.map((entry) => [entry.key, entry]));

  const changed = [];
  const added = [];
  const removed = [];

  const seen = new Set([...officialMap.keys(), ...candidateMap.keys()]);
  for (const key of seen) {
    const official = officialMap.get(key);
    const candidate = candidateMap.get(key);
    if (official && candidate) {
      if (
        official.gateNumber !== candidate.gateNumber ||
        official.timeDisplayFinance !== candidate.timeDisplayFinance
      ) {
        changed.push({
          flightDisplay: official.flightDisplay,
          official,
          candidate,
        });
      }
      continue;
    }

    if (candidate) {
      added.push(candidate);
      continue;
    }

    if (official) {
      removed.push(official);
    }
  }

  return {
    changed: sortDiffItems(changed),
    added: sortFinanceEntries(added),
    removed: sortFinanceEntries(removed),
  };
}

function keyFinanceEntries(entries) {
  const counts = new Map();
  return sortFinanceEntries(entries).map((entry) => {
    const index = (counts.get(entry.flightDisplay) || 0) + 1;
    counts.set(entry.flightDisplay, index);
    return { ...entry, key: `${entry.flightDisplay}#${index}` };
  });
}

function buildFinanceEntriesFromPayload(payload) {
  const departures = sortDepartures(payload?.departures ?? []).filter((departure) => isSameChicagoFinanceDay(departure, payload));
  return departures.map((departure) => ({
    flightDisplay: departure.flightDisplay,
    gateNumber: departure.gateNumber,
    timeDisplayFinance: departure.timeDisplayFinance,
  }));
}

function parseFinanceRows(financeText) {
  const entries = [];
  financeText.split(/\r?\n/).forEach((rawLine) => {
    const line = rawLine.trim();
    if (
      !line ||
      line.startsWith("Flight |")
    ) {
      return;
    }

    const parts = rawLine.split("|").map((part) => part.trim());
    if (parts.length !== 3 || !/^\d+$/.test(parts[1])) {
      return;
    }

    entries.push({
      flightDisplay: parts[0],
      gateNumber: Number(parts[1]),
      timeDisplayFinance: parts[2],
    });
  });
  return sortFinanceEntries(entries);
}

function renderFinanceTextFromPayload(payload = state.payload) {
  const entries = buildFinanceEntriesFromPayload(payload);
  return `${formatFinanceRows(entries).join("\n")}\n`;
}

function formatFinanceRows(entries) {
  const widths = measureFinanceWidths(entries);
  return [formatFinanceHeader(widths), ...entries.map((entry) => formatFinanceLine(entry, widths))];
}

function renderStatusFooter() {
  const diagnostics = normalizeDiagnostics(state.diagnostics);
  const status = diagnostics.status || "healthy";
  const lastSuccess = diagnostics.lastSuccessAt ? new Date(diagnostics.lastSuccessAt) : null;
  const nextRefresh = formatChicagoTime(nextOpsRefreshDate());
  const relative = lastSuccess ? formatRelativeAge(lastSuccess) : null;

  if (!lastSuccess && status !== "healthy") {
    statusLine.textContent = "✖ Status unavailable";
    return;
  }

  if (status === "healthy") {
    statusLine.textContent = `● Healthy · Updated ${relative || "just now"} · Last update ${formatChicagoTime(lastSuccess)} · Next update ${nextRefresh}`;
    return;
  }

  if (status === "degraded") {
    statusLine.textContent = `▲ Some data may be delayed · Updated ${relative || "recently"} · Last update ${formatChicagoTime(lastSuccess)} · Next update ${nextRefresh}`;
    return;
  }

  statusLine.textContent = `◐ Updated ${relative || "earlier"} · Last update ${formatChicagoTime(lastSuccess)} · Next update ${nextRefresh}`;
}

function normalizeDiagnostics(diagnostics) {
  if (diagnostics && typeof diagnostics === "object" && typeof diagnostics.status === "string") {
    const normalized = { ...diagnostics };
    const lastSuccess = normalized.lastSuccessAt ? new Date(normalized.lastSuccessAt) : null;
    const staleAfterMinutes = Number(normalized.staleAfterMinutes || 180);
    if (
      normalized.status !== "degraded" &&
      lastSuccess &&
      Math.floor((currentTimeMs() - lastSuccess.getTime()) / 60000) > staleAfterMinutes
    ) {
      normalized.status = "stale";
    }
    return normalized;
  }
  return buildFallbackDiagnostics();
}

function buildFallbackDiagnostics() {
  const generatedAt = state.payload?.generatedAt;
  if (!generatedAt) {
    return { status: "critical", lastSuccessAt: null, staleAfterMinutes: 180 };
  }

  const generatedDate = new Date(generatedAt);
  const ageMinutes = Math.floor((currentTimeMs() - generatedDate.getTime()) / 60000);
  return {
    status: ageMinutes > 180 ? "stale" : "healthy",
    lastSuccessAt: generatedAt,
    staleAfterMinutes: 180,
  };
}

function formatRelativeAge(date) {
  const diffMinutes = Math.max(0, Math.floor((currentTimeMs() - date.getTime()) / 60000));
  if (diffMinutes < 1) {
    return "just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }
  const hours = Math.floor(diffMinutes / 60);
  const minutes = diffMinutes % 60;
  if (minutes === 0) {
    return `${hours}h ago`;
  }
  return `${hours}h ${minutes}m ago`;
}

function getVisibleDepartures() {
  const departures = state.payload?.departures ?? [];
  if (isFinanceView()) {
    return sortDepartures(departures);
  }

  const upcomingDepartures = departures.filter(isVisibleInOps);
  const filtered =
    state.activeFilter === "all"
      ? upcomingDepartures
      : upcomingDepartures.filter((departure) => departure.podId === state.activeFilter);

  return sortDepartures(filtered);
}

function isVisibleInOps(departure) {
  const currentMinute = Math.floor(currentTimeMs() / 60000);
  const departureMinute = Math.floor(departure.sortTimestamp / 60);
  return currentMinute <= departureMinute;
}

function sortDepartures(departures) {
  return departures
    .slice()
    .sort(
      (left, right) =>
        left.sortTimestamp - right.sortTimestamp ||
        left.gateNumber - right.gateNumber ||
        left.destination.localeCompare(right.destination)
    );
}

function sortFinanceEntries(entries) {
  return entries
    .slice()
    .sort(
      (left, right) =>
        left.timeDisplayFinance.localeCompare(right.timeDisplayFinance) ||
        left.gateNumber - right.gateNumber ||
        left.flightDisplay.localeCompare(right.flightDisplay)
    );
}

function sortDiffItems(items) {
  return items
    .slice()
    .sort(
      (left, right) =>
        left.official.timeDisplayFinance.localeCompare(right.official.timeDisplayFinance) ||
        left.official.gateNumber - right.official.gateNumber ||
        left.flightDisplay.localeCompare(right.flightDisplay)
    );
}

function updateOpsBoardNote(departures) {
  const notes = [];
  if (departures.some((departure) => !isSameChicagoFinanceDay(departure, state.payload))) {
    notes.push("Displaying next-day departures.");
  }
  boardNote.textContent = notes.join(" · ");
  boardNote.classList.toggle("hidden", !boardNote.textContent);
}

function financeBoardNote() {
  if (isFinanceCompareAvailable()) {
    return `${currentCompareWindowLabel()} Open`;
  }
  return `Next Finance Event ${formatChicagoTime(nextFinanceEventDate())}`;
}

function setFinanceHeading(note) {
  boardTitle.textContent = "Finance Review";
}

function shouldHideFinanceFilter() {
  const minutes = currentChicagoMinutes();
  return minutes < FINANCE_VISIBLE_START || minutes >= FINANCE_VISIBLE_END;
}

function isFinanceCompareAvailable() {
  return !shouldHideFinanceFilter();
}

function currentCompareWindowLabel() {
  const minutes = currentChicagoMinutes();
  const active = FINANCE_COMPARE_WINDOWS.find((window) => minutes >= window.start && minutes < window.end);
  return active?.label || "Finance Review Window";
}

function nextOpsRefreshDate() {
  const chicago = getChicagoClockParts(new Date(currentTimeMs()));
  const nextHour = chicago.hour + 1;
  const dayOffset = Math.floor(nextHour / 24);
  return chicagoDateAt(chicago, nextHour % 24, 0, dayOffset);
}

function nextFinanceEventDate() {
  const chicago = getChicagoClockParts(new Date(currentTimeMs()));
  const currentMinutes = chicago.hour * 60 + chicago.minute;
  const schedule = [
    { hour: 5, minute: 0 },
    { hour: 12, minute: 0 },
    { hour: 18, minute: 0 },
  ];

  const next = schedule.find(({ hour, minute }) => currentMinutes < hour * 60 + minute);
  if (next) {
    return chicagoDateAt(chicago, next.hour, next.minute, 0);
  }
  return chicagoDateAt(chicago, 5, 0, 1);
}

function updateRowContent(row, departure) {
  const cells = [];
  cells.push(makeCell("time-cell", departure.timeDisplayOps));

  const gateCell = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = "gate-badge";
  badge.textContent = departure.gateLabel;
  gateCell.appendChild(badge);
  cells.push(gateCell);
  cells.push(makeDestinationCell(departure));
  row.replaceChildren(...cells);
}

function makeCell(className, text) {
  const cell = document.createElement("td");
  if (className) {
    cell.className = className;
  }
  cell.textContent = text;
  return cell;
}

function makeDestinationCell(departure) {
  const cell = document.createElement("td");
  cell.className = "destination-cell";

  const wrap = document.createElement("div");
  wrap.className = "destination-wrap";

  const text = document.createElement("span");
  text.className = "destination-text";
  text.textContent = departure.destination;
  wrap.appendChild(text);

  if (departure.status) {
    const badge = document.createElement("span");
    badge.className = `status-badge status-${statusKind(departure.status)}`;
    badge.textContent = departure.status;
    wrap.appendChild(badge);
  }

  cell.appendChild(wrap);
  return cell;
}

function animateTargets(target, params) {
  if (!target) {
    return;
  }

  if (!prefersReducedMotion && typeof animeApi.animate === "function") {
    try {
      animeApi.animate([target], { duration: 240, ease: "cubic-bezier(0.2, 0.8, 0.2, 1)", ...params });
      return;
    } catch (error) {
      // Fall back to WAAPI.
    }
  }

  if (typeof target.animate !== "function") {
    return;
  }

  const frames = buildKeyframes(params);
  const animation = target.animate(frames, {
    duration: params.duration ?? 240,
    easing: params.ease || "ease-out",
    fill: "both",
  });
  if (typeof params.onComplete === "function") {
    animation.addEventListener("finish", () => params.onComplete(), { once: true });
  }
}

function buildKeyframes(params) {
  const from = {};
  const to = {};
  if (params.opacity) {
    from.opacity = params.opacity[0];
    to.opacity = params.opacity[1];
  }

  const transforms = [[], []];
  if (params.translateY) {
    transforms[0].push(`translateY(${params.translateY[0]}px)`);
    transforms[1].push(`translateY(${params.translateY[1]}px)`);
  }
  if (params.scale) {
    transforms[0].push(`scale(${params.scale[0]})`);
    transforms[1].push(`scale(${params.scale[1]})`);
  }
  if (transforms[0].length) {
    from.transform = transforms[0].join(" ");
    to.transform = transforms[1].join(" ");
  }
  return [from, to];
}

function animateRedAlertSweep() {
  if (prefersReducedMotion) {
    return;
  }

  const rows = Array.from(departuresBody.querySelectorAll(".board-row.is-window-red-4"));
  rows.forEach((row, rowIndex) => {
    const cells = Array.from(row.querySelectorAll("td"));
    cells.forEach((cell, cellIndex) => {
      cell.classList.add("red-alert-cell");
      const sweep = ensureRedAlertSweep(cell);
      animateRedAlertCell(sweep, rowIndex * 120 + cellIndex * 95);
    });
  });
}

function ensureRedAlertSweep(cell) {
  const existing = cell.querySelector(".red-alert-sweep");
  if (existing) {
    return existing;
  }

  const sweep = document.createElement("span");
  sweep.className = "red-alert-sweep";
  sweep.setAttribute("aria-hidden", "true");
  cell.appendChild(sweep);
  return sweep;
}

function animateRedAlertCell(sweep, delay) {
  if (typeof sweep.getAnimations === "function") {
    sweep.getAnimations().forEach((animation) => animation.cancel());
  }
  sweep.style.opacity = "0";
  sweep.style.transform = "translateX(-140%)";

  if (typeof animeApi.animate === "function") {
    try {
      animeApi.animate([sweep], {
        opacity: [0, 1, 0],
        translateX: ["-140%", "190%"],
        duration: 760,
        delay,
        ease: "cubic-bezier(0.22, 1, 0.36, 1)",
      });
      return;
    } catch (error) {
      // Fall through to WAAPI.
    }
  }

  if (typeof sweep.animate !== "function") {
    return;
  }

  sweep.animate(
    [
      { opacity: 0, transform: "translateX(-140%)" },
      { opacity: 1, transform: "translateX(-8%)", offset: 0.24 },
      { opacity: 0, transform: "translateX(190%)" },
    ],
    {
      duration: 760,
      delay,
      easing: "cubic-bezier(0.22, 1, 0.36, 1)",
      fill: "both",
    }
  );
}

function getUrgencyBand(departure) {
  const currentMinute = Math.floor(currentTimeMs() / 60000);
  const departureMinute = Math.floor(departure.sortTimestamp / 60);
  const delta = departureMinute - currentMinute;
  if (delta < 0 || delta > 180) {
    return null;
  }
  if (delta <= 10) {
    return "red-4";
  }
  if (delta <= 25) {
    return "red-3";
  }
  if (delta <= 45) {
    return "red-2";
  }
  if (delta <= 60) {
    return "red-1";
  }
  if (delta <= 90) {
    return "yellow-3";
  }
  if (delta <= 135) {
    return "yellow-2";
  }
  return "yellow-1";
}

function setFlightsCount(count) {
  visibleCount.textContent = `Flights: ${count}`;
}

function isSameChicagoFinanceDay(departure, payload = state.payload) {
  if (!payload?.generatedAt) {
    return true;
  }

  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const generatedDay = formatter.format(new Date(payload.generatedAt));
  const departureDay = formatter.format(new Date(departure.sortTimestamp * 1000));
  return generatedDay === departureDay;
}

function cycleTheme() {
  const currentIndex = THEMES.findIndex((theme) => theme.id === state.activeTheme);
  const nextTheme = THEMES[(currentIndex + 1) % THEMES.length];
  state.activeTheme = nextTheme.id;
  writeStorage("mspage-gcon-theme", nextTheme.id);
  applyTheme(nextTheme.id);
  updateThemeControl(nextTheme);
}

function applyTheme(themeId) {
  document.documentElement.dataset.theme = themeId;
}

function currentTheme() {
  return THEMES.find((theme) => theme.id === state.activeTheme) || THEMES[0];
}

function updateThemeControl(theme) {
  themeCycle.innerHTML = THEME_ICONS[theme.id] || THEME_ICONS.light;
  themeCycle.title = `Cycle theme. Current theme: ${theme.label}`;
  themeCycle.setAttribute("aria-label", `Cycle theme. Current theme: ${theme.label}`);
}

function ensureFilterIndicator() {
  if (podFilters.querySelector(".filter-indicator")) {
    return;
  }
  const indicator = document.createElement("span");
  indicator.className = "filter-indicator";
  indicator.setAttribute("aria-hidden", "true");
  podFilters.prepend(indicator);
}

function updateFilterIndicator() {
  const indicator = podFilters.querySelector(".filter-indicator");
  const activeButton = podFilters.querySelector(".pill.active");
  if (!indicator || !activeButton) {
    return;
  }

  const containerRect = podFilters.getBoundingClientRect();
  const buttonRect = activeButton.getBoundingClientRect();
  indicator.style.width = `${buttonRect.width}px`;
  indicator.style.height = `${buttonRect.height}px`;
  indicator.style.transform = `translate(${buttonRect.left - containerRect.left}px, ${buttonRect.top - containerRect.top}px)`;
}

function animateFinancePillCue() {
  if (!isFinanceView()) {
    state.lastDiffCueState = null;
    return;
  }

  const activeFinanceButton = podFilters.querySelector('[data-filter-id="finance"].pill.active');
  if (!activeFinanceButton) {
    state.lastDiffCueState = state.diffOpen;
    return;
  }

  if (state.lastDiffCueState == null) {
    state.lastDiffCueState = state.diffOpen;
    return;
  }

  if (state.lastDiffCueState === state.diffOpen) {
    return;
  }

  const enteringDiff = state.diffOpen;
  state.lastDiffCueState = state.diffOpen;
  activeFinanceButton.classList.remove("finance-pill-pop");
  activeFinanceButton.classList.remove("finance-pill-absorb");
  void activeFinanceButton.offsetWidth;
  emitAnimeFinanceCue(activeFinanceButton, enteringDiff ? "open" : "close");
  window.setTimeout(() => {
    activeFinanceButton.classList.remove("finance-pill-pop");
    activeFinanceButton.classList.remove("finance-pill-absorb");
  }, 620);
}

function emitAnimeFinanceCue(button, mode) {
  const opening = mode === "open";
  button.classList.add(opening ? "finance-pill-pop" : "finance-pill-absorb");
  animateTargets(button, {
    scale: opening ? [0.98, 1.06, 1] : [1.02, 0.98, 1],
    duration: 260,
  });
  if (typeof animeApi.animate === "function") {
    try {
      animeApi.animate([button], {
        scaleX: opening ? [0.98, 1.08, 1] : [1.02, 0.98, 1],
        scaleY: opening ? [0.99, 1.03, 1] : [1.01, 0.99, 1],
        duration: 260,
        ease: "cubic-bezier(0.16, 1, 0.3, 1)",
      });
    } catch (error) {
      // Base animation already applied above.
    }
  }
  emitFinanceCueParticles(button, opening ? "out" : "in");
}

function emitFinanceCueParticles(button, mode) {
  if (prefersReducedMotion) {
    return;
  }

  const rect = button.getBoundingClientRect();
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  const palette = [
    "var(--accent)",
    "var(--accent-strong)",
    "rgba(15, 118, 110, 0.62)",
    "rgba(21, 94, 117, 0.48)",
  ];
  const particles = [];
  const particleCount = 10;

  for (let index = 0; index < particleCount; index += 1) {
    const particle = document.createElement("span");
    particle.className = "finance-cue-particle";
    particle.style.left = `${centerX}px`;
    particle.style.top = `${centerY}px`;
    particle.style.background = palette[index % palette.length];
    particle.style.setProperty("--finance-cue-x", `${Math.cos((Math.PI * 2 * index) / particleCount) * 42}px`);
    particle.style.setProperty("--finance-cue-y", `${Math.sin((Math.PI * 2 * index) / particleCount) * 22}px`);
    particle.style.setProperty("--finance-cue-rotation", `${index % 2 === 0 ? 18 : -18}deg`);
    if (mode === "in") {
      particle.classList.add("finance-cue-particle-in");
    }
    document.body.appendChild(particle);
    particles.push(particle);
    window.setTimeout(() => particle.remove(), 320);
  }

  if (typeof animeApi.animate === "function") {
    try {
      animeApi.animate(particles, {
        opacity: mode === "in" ? [0, 1, 0] : [0, 1, 0],
        scale: mode === "in" ? [1.08, 1, 0.42] : [0.72, 1.08, 0.92],
        translateX: (_, index) => {
          const direction = Math.cos((Math.PI * 2 * index) / particles.length) * 44;
          return mode === "in" ? [direction, 0] : [0, direction];
        },
        translateY: (_, index) => {
          const direction = Math.sin((Math.PI * 2 * index) / particles.length) * 24;
          return mode === "in" ? [direction, 0] : [0, direction];
        },
        rotate: (_, index) => (mode === "in" ? [index % 2 === 0 ? 18 : -18, 0] : [0, index % 2 === 0 ? 18 : -18]),
        delay: (_, index) => index * 3,
        duration: 260,
        ease: "cubic-bezier(0.2, 0.8, 0.2, 1)",
      });
    } catch (error) {
      // CSS keyframes remain as fallback.
    }
  }
}

function isFinanceView() {
  return state.activeFilter === "finance";
}

function fetchAsset(path) {
  return fetch(withCacheBust(resolveAssetPath(path)), { cache: "no-store" });
}

function resolveAssetPath(path) {
  if (/^(https?:)?\/\//.test(path) || path.startsWith("/")) {
    return path;
  }
  return `./${path.replace(/^\.\//, "")}`;
}

function withCacheBust(path) {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}ts=${Date.now()}`;
}

function formatChicagoTime(date) {
  return new Intl.DateTimeFormat("en-US", {
    timeStyle: "short",
    timeZone: "America/Chicago",
  }).format(date);
}

function formatChicagoDateTime(date) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Chicago",
  }).format(date);
}

function currentChicagoMinutes() {
  const parts = getChicagoClockParts(new Date(currentTimeMs()));
  return parts.hour * 60 + parts.minute;
}

function getChicagoClockParts(date) {
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Chicago",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const parts = formatter.formatToParts(date);
  return {
    year: Number(parts.find((part) => part.type === "year")?.value || "0"),
    month: Number(parts.find((part) => part.type === "month")?.value || "1"),
    day: Number(parts.find((part) => part.type === "day")?.value || "1"),
    hour: Number(parts.find((part) => part.type === "hour")?.value || "0"),
    minute: Number(parts.find((part) => part.type === "minute")?.value || "0"),
    second: Number(parts.find((part) => part.type === "second")?.value || "0"),
  };
}

function chicagoDateAt(parts, hour, minute, dayOffset) {
  const utcGuess = new Date(Date.UTC(parts.year, parts.month - 1, parts.day + dayOffset, hour + 6, minute, 0));
  const corrected = getChicagoClockParts(utcGuess);
  const offsetMinutes =
    (corrected.hour * 60 + corrected.minute) - (hour * 60 + minute) + (corrected.day - (parts.day + dayOffset)) * 1440;
  return new Date(utcGuess.getTime() - offsetMinutes * 60000);
}

function statusKind(status) {
  const normalized = String(status || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-");
  if (normalized.includes("cancel")) {
    return "cancelled";
  }
  if (normalized.includes("delay")) {
    return "delayed";
  }
  if (normalized.includes("board")) {
    return "boarding";
  }
  if (normalized.includes("depart")) {
    return "departed";
  }
  if (normalized.includes("on-time")) {
    return "ontime";
  }
  return "default";
}

function readStorage(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (error) {
    return null;
  }
}

function writeStorage(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch (error) {
    console.warn("Unable to persist preference.", error);
  }
}

function currentTimeMs() {
  return previewNow ?? Date.now();
}

function readPreviewNow(rawValue) {
  if (!rawValue) {
    return null;
  }

  const parsedNumber = Number(rawValue);
  if (Number.isFinite(parsedNumber) && parsedNumber > 0) {
    return parsedNumber;
  }

  const parsedDate = Date.parse(rawValue);
  if (Number.isFinite(parsedDate)) {
    return parsedDate;
  }

  return null;
}

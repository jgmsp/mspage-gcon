const state = {
  ops: null,
  stats: null,
  diagnostics: null,
  activeTab: "ops",
  activeTerminal: "TB",
};

const lastUpdated = document.getElementById("last-updated");
const tabbar = document.getElementById("tabbar");
const terminalToggle = document.getElementById("terminal-toggle");
const departuresBody = document.getElementById("departures-body");
const opsEmpty = document.getElementById("ops-empty");
const venueTitle = document.getElementById("venue-title");
const venueCount = document.getElementById("venue-count");
const venueList = document.getElementById("venue-list");
const statusLine = document.getElementById("status-line");
const opsView = document.getElementById("ops-view");
const statsView = document.getElementById("stats-view");
const serviceDate = document.getElementById("service-date");
const lostCount = document.getElementById("lost-count");
const gainedCount = document.getElementById("gained-count");
const lostList = document.getElementById("lost-list");
const gainedList = document.getElementById("gained-list");

bindEvents();
loadData().catch((error) => {
  console.error(error);
  statusLine.textContent = "Status: Unable to load PHL draft data";
});

function bindEvents() {
  tabbar?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-tab]");
    if (!button) {
      return;
    }
    state.activeTab = button.dataset.tab;
    render();
  });
}

async function loadData() {
  const [opsResponse, statsResponse, diagnosticsResponse] = await Promise.all([
    fetch("./ops.json"),
    fetch("./stats.json"),
    fetch("./diagnostics.json"),
  ]);

  if (!opsResponse.ok) {
    throw new Error(`Failed to load ops.json: ${opsResponse.status}`);
  }

  state.ops = await opsResponse.json();
  state.stats = statsResponse.ok ? await statsResponse.json() : fallbackStats();
  state.diagnostics = diagnosticsResponse.ok ? await diagnosticsResponse.json() : fallbackDiagnostics();
  if (!findTerminal(state.activeTerminal)) {
    state.activeTerminal = state.ops.terminals?.[0]?.id || "TB";
  }
  render();
}

function render() {
  renderTabs();
  renderMeta();
  renderStatus();
  renderTerminalToggle();
  renderOps();
  renderVenues();
  renderStats();
}

function renderTabs() {
  Array.from(tabbar.querySelectorAll("[data-tab]")).forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === state.activeTab);
  });
  opsView.classList.toggle("hidden", state.activeTab !== "ops");
  statsView.classList.toggle("hidden", state.activeTab !== "stats");
}

function renderMeta() {
  const generatedAt = state.ops?.generatedAt;
  if (!generatedAt) {
    lastUpdated.textContent = "Awaiting snapshot";
    return;
  }
  lastUpdated.textContent = formatDateTime(generatedAt);
}

function renderStatus() {
  const status = state.diagnostics?.status || "unknown";
  statusLine.textContent = `Status: ${capitalize(status)}`;
}

function renderTerminalToggle() {
  const terminals = state.ops?.terminals || [];
  terminalToggle.replaceChildren(
    ...terminals.map((terminal) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = terminal.id === state.activeTerminal ? "terminal-pill active" : "terminal-pill";
      button.textContent = terminal.id;
      button.addEventListener("click", () => {
        if (state.activeTerminal === terminal.id) {
          return;
        }
        state.activeTerminal = terminal.id;
        render();
      });
      return button;
    })
  );
}

function renderOps() {
  const departures = (state.ops?.departures || []).filter((item) => item.terminalId === state.activeTerminal);
  departuresBody.replaceChildren(
    ...departures.map((departure) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${escapeHtml(departure.timeDisplay)}</td>
        <td>${escapeHtml(departure.gateLabel)}</td>
        <td class="flight-cell">${escapeHtml(departure.flightDisplay)}</td>
        <td>${escapeHtml(departure.destination)}</td>
        <td>${renderStatusBadge(departure.status || "Unknown")}</td>
      `;
      return row;
    })
  );
  opsEmpty.classList.toggle("hidden", departures.length > 0);
}

function renderVenues() {
  const terminal = findTerminal(state.activeTerminal);
  venueTitle.textContent = terminal ? `${terminal.label} venues` : "Terminal venues";
  const venues = terminal?.venues || [];
  venueCount.textContent = `${venues.length} venue${venues.length === 1 ? "" : "s"}`;
  venueList.replaceChildren(
    ...venues.map((venue) => {
      const item = document.createElement("li");
      item.textContent = venue;
      return item;
    })
  );
}

function renderStats() {
  const stats = state.stats || fallbackStats();
  serviceDate.textContent = stats.serviceDate ? `Service day ${stats.serviceDate}` : "Service day pending";
  lostCount.textContent = String(stats.summary?.lostToC || 0);
  gainedCount.textContent = String(stats.summary?.gainedFromC || 0);
  renderLedgerList(lostList, stats.events?.filter((event) => event.direction === "lostToC") || [], "No losses logged.");
  renderLedgerList(gainedList, stats.events?.filter((event) => event.direction === "gainedFromC") || [], "No gains logged.");
}

function renderLedgerList(container, events, emptyMessage) {
  if (events.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = emptyMessage;
    container.replaceChildren(empty);
    return;
  }

  container.replaceChildren(
    ...events
      .slice()
      .reverse()
      .map((event) => {
        const item = document.createElement("article");
        item.className = "ledger-item";
        item.innerHTML = `
          <div class="ledger-title">
            <span>${escapeHtml(event.flightDisplay)}</span>
            <span class="ledger-direction">${escapeHtml(labelForDirection(event.direction))}</span>
          </div>
          <div class="ledger-meta">${escapeHtml(event.fromGateLabel || "--")} -> ${escapeHtml(event.toGateLabel || "--")}</div>
          <div class="ledger-meta">Departure ${escapeHtml(event.departureTime || "--")}</div>
          <div class="ledger-meta">Logged ${escapeHtml(formatDateTime(event.detectedAt))}</div>
        `;
        return item;
      })
  );
}

function labelForDirection(direction) {
  return direction === "lostToC" ? "TB -> TC" : "TC -> TB";
}

function findTerminal(id) {
  return (state.ops?.terminals || []).find((terminal) => terminal.id === id) || null;
}

function renderStatusBadge(status) {
  const normalized = status.toLowerCase();
  const klass = normalized.includes("delay") ? "status-badge delayed" : normalized.includes("board") ? "status-badge boarding" : "status-badge";
  return `<span class="${klass}">${escapeHtml(status)}</span>`;
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/New_York",
  }).format(date);
}

function fallbackStats() {
  return {
    serviceDate: "",
    summary: { lostToC: 0, gainedFromC: 0 },
    events: [],
  };
}

function fallbackDiagnostics() {
  return { status: "unknown" };
}

function capitalize(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

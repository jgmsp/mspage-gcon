const state = {
  payload: null,
  activePod: "all",
  activeView: readStorage("mspage-gcon-view") || "ops",
  activeTheme: readStorage("mspage-gcon-theme") || "light",
  opsOnlyMode: readStorage("mspage-gcon-ops-only") === "true",
};

const themeSwitch = document.getElementById("theme-switch");
const viewSwitch = document.getElementById("view-switch");
const departuresHead = document.getElementById("departures-head");
const departuresBody = document.getElementById("departures-body");
const podFilters = document.getElementById("pod-filters");
const lastUpdated = document.getElementById("last-updated");
const visibleCount = document.getElementById("visible-count");
const emptyState = document.getElementById("empty-state");
const boardTitle = document.getElementById("board-title");
const boardCaption = document.getElementById("board-caption");
const boardNote = document.getElementById("board-note");
const activeViewLabel = document.getElementById("active-view-label");
const podCopy = document.getElementById("pod-copy");
const opsOnlyToggle = document.getElementById("ops-only-toggle");
const financeDownload = document.getElementById("finance-download");

const THEMES = [
  {
    id: "light",
    label: "Light",
    preview: ["#f6f2e9", "#0f766e", "#1e2b24"],
  },
  {
    id: "dark",
    label: "Dark",
    preview: ["#19212b", "#6d97b5", "#f0f2f4"],
  },
  {
    id: "slate",
    label: "Slate",
    preview: ["#0c1014", "#2aa886", "#99d1ce"],
  },
  {
    id: "plum",
    label: "Plum",
    preview: ["#1e1f29", "#bd93f9", "#f8f8f2"],
  },
  {
    id: "marine",
    label: "Marine",
    preview: ["#0e1920", "#6196b8", "#c5cdd3"],
  },
  {
    id: "olive",
    label: "Olive",
    preview: ["#0e101a", "#de8e00", "#ebefc0"],
  },
  {
    id: "ember",
    label: "Ember",
    preview: ["#0d0024", "#c46a43", "#4fd478"],
  },
];

const VIEW_CONFIG = {
  ops: {
    label: "Operations",
    title: "Operations Board",
    caption: "Time | Gate | Dest",
    note: "Flights stay visible through their ETD minute, then drop off the ops board.",
    headers: ["Time", "Gate", "Dest"],
  },
  finance: {
    label: "Finance",
    title: "Finance View",
    caption: "Flight | Gate | Time",
    note: "Finance mirrors the same snapshot as the text export.",
    headers: ["Flight", "Gate", "Time"],
  },
};

applyTheme(state.activeTheme);
syncOpsOnlyPreference();

async function loadSnapshot() {
  const response = await fetch(`./ops.json?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ops snapshot: ${response.status}`);
  }
  state.payload = await response.json();
  render();
}

function render() {
  renderMeta();
  renderThemeSwitch();
  renderViewSwitch();
  renderPodFilters();
  renderHead();
  renderRows();
}

function renderMeta() {
  activeViewLabel.textContent = state.opsOnlyMode ? "Ops Only" : VIEW_CONFIG[state.activeView].label;

  const generatedAt = state.payload?.generatedAt;
  if (!generatedAt) {
    lastUpdated.textContent = "Awaiting snapshot";
    return;
  }

  const formatter = new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "America/Chicago",
  });
  lastUpdated.textContent = formatter.format(new Date(generatedAt));
}

function renderThemeSwitch() {
  const buttons = THEMES.map((theme) => createThemeButton(theme, state.activeTheme === theme.id));
  themeSwitch.replaceChildren(...buttons);
}

function createThemeButton(theme, active) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = active ? "theme-chip active" : "theme-chip";
  button.setAttribute("aria-pressed", active ? "true" : "false");
  button.addEventListener("click", () => {
    state.activeTheme = theme.id;
    writeStorage("mspage-gcon-theme", theme.id);
    applyTheme(theme.id);
    renderThemeSwitch();
  });

  const swatch = document.createElement("span");
  swatch.className = "theme-swatch";
  theme.preview.forEach((color) => {
    const dot = document.createElement("span");
    dot.className = "theme-dot";
    dot.style.backgroundColor = color;
    swatch.appendChild(dot);
  });

  const label = document.createElement("span");
  label.className = "theme-label";
  label.textContent = theme.label;

  button.append(swatch, label);
  return button;
}

function renderViewSwitch() {
  const buttons = state.opsOnlyMode
    ? [createViewButton("ops", "Ops Only", true)]
    : [
        createViewButton("ops", "Ops", state.activeView === "ops"),
        createViewButton("finance", "Finance", state.activeView === "finance"),
      ];

  viewSwitch.replaceChildren(...buttons);
  financeDownload.hidden = state.opsOnlyMode;
}

function createViewButton(id, label, active) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = active ? "pill active" : "pill";
  button.textContent = label;
  button.addEventListener("click", () => {
    if (state.opsOnlyMode && id !== "ops") {
      return;
    }
    state.activeView = id;
    writeStorage("mspage-gcon-view", id);
    render();
  });
  return button;
}

function renderPodFilters() {
  const pods = state.payload?.pods ?? [];
  const financeMode = state.activeView === "finance";

  podFilters.classList.toggle("disabled", financeMode);
  podFilters.setAttribute("aria-disabled", financeMode ? "true" : "false");
  podCopy.textContent = financeMode
    ? "Finance shows the full departure list. Pod filters stay available for ops."
    : "Filter by pod or full list.";

  const buttons = [
    createFilterButton("all", "All Pods", state.activePod === "all"),
    ...pods.map((pod) => createFilterButton(pod.id, pod.label, state.activePod === pod.id)),
  ];

  podFilters.replaceChildren(...buttons);
}

function createFilterButton(id, label, active) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = active ? "pill active" : "pill";
  button.textContent = label;
  button.addEventListener("click", () => {
    if (state.activeView === "finance") {
      return;
    }
    state.activePod = id;
    render();
  });
  return button;
}

function renderHead() {
  const config = VIEW_CONFIG[state.activeView];
  boardTitle.textContent = config.title;
  boardCaption.textContent = config.caption;
  boardNote.textContent = state.opsOnlyMode && state.activeView === "ops"
    ? "Ops-only mode is saved locally on this browser."
    : config.note;

  const tr = document.createElement("tr");
  config.headers.forEach((header) => {
    const th = document.createElement("th");
    th.textContent = header;
    tr.appendChild(th);
  });
  departuresHead.replaceChildren(tr);
}

function renderRows() {
  const departures = getVisibleDepartures();
  visibleCount.textContent = String(departures.length);

  if (departures.length === 0) {
    departuresBody.replaceChildren();
    emptyState.classList.remove("hidden");
    return;
  }

  emptyState.classList.add("hidden");
  const rows = departures.map((departure) => {
    const tr = document.createElement("tr");

    if (state.activeView === "finance") {
      const flightCell = document.createElement("td");
      flightCell.className = "time-cell";
      flightCell.textContent = departure.flightDisplay;

      const gateCell = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = "gate-badge";
      badge.textContent = departure.gateNumber;
      gateCell.appendChild(badge);

      const timeCell = document.createElement("td");
      timeCell.className = "time-cell";
      timeCell.textContent = departure.timeDisplayFinance;

      tr.append(flightCell, gateCell, timeCell);
    } else {
      const timeCell = document.createElement("td");
      timeCell.className = "time-cell";
      timeCell.textContent = departure.timeDisplayOps;

      const gateCell = document.createElement("td");
      const badge = document.createElement("span");
      badge.className = "gate-badge";
      badge.textContent = departure.gateLabel;
      gateCell.appendChild(badge);

      const destinationCell = document.createElement("td");
      destinationCell.textContent = departure.destination;

      tr.append(timeCell, gateCell, destinationCell);
    }

    return tr;
  });

  departuresBody.replaceChildren(...rows);
}

function getVisibleDepartures() {
  const departures = state.payload?.departures ?? [];
  if (state.activeView === "finance") {
    return departures;
  }

  const upcomingDepartures = departures.filter(isVisibleInOps);
  if (state.activePod === "all") {
    return upcomingDepartures;
  }
  return upcomingDepartures.filter((departure) => departure.podId === state.activePod);
}

function isVisibleInOps(departure) {
  const currentMinute = Math.floor(Date.now() / 60000);
  const departureMinute = Math.floor(departure.sortTimestamp / 60);
  return currentMinute <= departureMinute;
}

opsOnlyToggle.addEventListener("change", () => {
  state.opsOnlyMode = opsOnlyToggle.checked;
  syncOpsOnlyPreference();
  render();
});

setInterval(() => {
  if (state.payload) {
    renderRows();
  }
}, 60000);

loadSnapshot().catch((error) => {
  console.error(error);
  emptyState.classList.remove("hidden");
  emptyState.textContent = "Unable to load the current snapshot.";
});

function syncOpsOnlyPreference() {
  opsOnlyToggle.checked = state.opsOnlyMode;
  document.body.classList.toggle("ops-only-mode", state.opsOnlyMode);
  if (state.opsOnlyMode) {
    state.activeView = "ops";
    writeStorage("mspage-gcon-view", "ops");
  }
  writeStorage("mspage-gcon-ops-only", String(state.opsOnlyMode));
}

function applyTheme(themeId) {
  document.documentElement.dataset.theme = themeId;
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

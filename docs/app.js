const state = {
  payload: null,
  activeFilter: "all",
  activeTheme: readStorage("mspage-gcon-theme") || "light",
  lastView: null,
};

const params = new URLSearchParams(window.location.search);
const snapshotPath = params.get("snapshot") || "ops.json";
const previewNow = readPreviewNow(params.get("previewNow"));

const themeCycle = document.getElementById("theme-cycle");
const departuresHead = document.getElementById("departures-head");
const departuresBody = document.getElementById("departures-body");
const podFilters = document.getElementById("pod-filters");
const tableWrap = document.querySelector(".table-wrap");
const lastUpdatedInline = document.getElementById("last-updated-inline");
const visibleCount = document.getElementById("visible-count");
const emptyState = document.getElementById("empty-state");
const boardTitle = document.getElementById("board-title");
const boardNote = document.getElementById("board-note");

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

applyTheme(state.activeTheme);

async function loadSnapshot() {
  const response = await fetch(`./${snapshotPath}?ts=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load ops snapshot: ${response.status}`);
  }
  state.payload = await response.json();
  render();
}

function render() {
  animateBoardTransition();
  renderMeta();
  renderPodFilters();
  renderHead();
  renderRows();
}

function renderMeta() {
  const generatedAt = state.payload?.generatedAt;
  updateThemeControl(currentTheme());
  if (!generatedAt) {
    lastUpdatedInline.textContent = "Awaiting snapshot";
    return;
  }

  const formatter = new Intl.DateTimeFormat("en-US", {
    timeStyle: "short",
    timeZone: "America/Chicago",
  });
  lastUpdatedInline.textContent = `Updated ${formatter.format(new Date(generatedAt))}`;
}

function renderPodFilters() {
  const pods = state.payload?.pods ?? [];
  const definitions = [
    { id: "all", label: "All" },
    ...pods.map((pod) => ({ id: pod.id, label: pod.label })),
    { id: "finance", label: "Finance" },
  ];

  const existingButtons = Array.from(podFilters.querySelectorAll("button"));
  if (existingButtons.length !== definitions.length) {
    podFilters.replaceChildren(
      ...definitions.map((definition) =>
        createFilterButton(definition.id, definition.label, state.activeFilter === definition.id)
      )
    );
  } else {
    existingButtons.forEach((button, index) => {
      const definition = definitions[index];
      button.textContent = definition.label;
      button.dataset.filterId = definition.id;
      button.className = state.activeFilter === definition.id ? "pill active" : "pill";
    });
  }
  ensureFilterIndicator();
  updateFilterIndicator();
}

function createFilterButton(id, label, active) {
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.filterId = id;
  button.className = active ? "pill active" : "pill";
  button.textContent = label;
  button.addEventListener("click", () => {
    if (state.activeFilter === id) {
      return;
    }
    state.activeFilter = id;
    render();
  });
  return button;
}

function renderHead() {
  const financeView = isFinanceView();
  boardTitle.textContent = financeView ? "Finance View" : "Operations View";
  boardNote.textContent = "";
  boardNote.classList.add("hidden");

  const tr = document.createElement("tr");
  const headers = financeView ? ["Flight", "Gate", "Time", "Dest"] : ["Time", "Gate", "Dest"];
  headers.forEach((header) => {
    const th = document.createElement("th");
    th.textContent = header;
    tr.appendChild(th);
  });
  departuresHead.replaceChildren(tr);
  animateHeaderTransition(state.lastView, financeView ? "finance" : "ops");
  state.lastView = financeView ? "finance" : "ops";
}

function renderRows() {
  const departures = getVisibleDepartures();
  setFlightsCount(departures.length);

  if (departures.length === 0) {
    for (const row of Array.from(departuresBody.children)) {
      row.remove();
    }
    emptyState.classList.remove("hidden");
    return;
  }

  emptyState.classList.add("hidden");
  const financeView = isFinanceView();
  const oldPositions = new Map(
    Array.from(departuresBody.children).map((row) => [row.dataset.rowKey, row.getBoundingClientRect().top])
  );
  const existingRows = new Map(Array.from(departuresBody.children).map((row) => [row.dataset.rowKey, row]));
  const desiredKeys = new Set(departures.map((departure) => rowKeyFor(departure, financeView)));

  for (const [key, row] of existingRows.entries()) {
    if (!desiredKeys.has(key)) {
      animateRowExit(row);
      existingRows.delete(key);
    }
  }

  const fragment = document.createDocumentFragment();
  departures.forEach((departure, index) => {
    const key = rowKeyFor(departure, financeView);
    const row = existingRows.get(key) || document.createElement("tr");
    row.dataset.rowKey = key;
    row.style.setProperty("--row-delay", `${Math.min(index, 7) * 24}ms`);
    row.className = "";
    row.classList.add("board-row");

    const urgencyBand = financeView ? null : getUrgencyBand(departure);
    if (urgencyBand) {
      row.classList.add("is-window", `is-window-${urgencyBand}`);
    }

    updateRowContent(row, departure, financeView);
    fragment.appendChild(row);

    if (!existingRows.has(key)) {
      row.classList.add("is-entering");
    }
  });

  departuresBody.replaceChildren(fragment);
  animateRowMoves(oldPositions);
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

function isUrgent(departure) {
  return getUrgencyBand(departure) !== null;
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

function applyTheme(themeId) {
  document.documentElement.dataset.theme = themeId;
}

themeCycle.addEventListener("click", () => {
  const currentIndex = THEMES.findIndex((theme) => theme.id === state.activeTheme);
  const nextTheme = THEMES[(currentIndex + 1) % THEMES.length];
  state.activeTheme = nextTheme.id;
  writeStorage("mspage-gcon-theme", nextTheme.id);
  applyTheme(nextTheme.id);
  themeCycle.classList.remove("is-spinning");
  void themeCycle.offsetWidth;
  themeCycle.classList.add("is-spinning");
  updateThemeControl(nextTheme);
});

function currentTheme() {
  return THEMES.find((theme) => theme.id === state.activeTheme) || THEMES[0];
}

function isFinanceView() {
  return state.activeFilter === "finance";
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

function animateBoardTransition() {
  if (!tableWrap) {
    return;
  }
  tableWrap.classList.remove("is-refreshing");
  void tableWrap.offsetWidth;
  tableWrap.classList.add("is-refreshing");
}

function rowKeyFor(departure, financeView) {
  return `${financeView ? "finance" : "ops"}:${departure.id}`;
}

function updateRowContent(row, departure, financeView) {
  const cells = [];

  if (financeView) {
    cells.push(makeCell("flight-cell", departure.flightDisplay));
    cells.push(makeCell("gate-number-cell", String(departure.gateNumber)));
    cells.push(makeCell("time-cell", departure.timeDisplayFinance));
    cells.push(makeCell("", departure.destination));
  } else {
    cells.push(makeCell("time-cell", departure.timeDisplayOps));

    const gateCell = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = "gate-badge";
    badge.textContent = departure.gateLabel;
    gateCell.appendChild(badge);
    cells.push(gateCell);

    cells.push(makeCell("", departure.destination));
  }

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

function animateRowMoves(oldPositions) {
  for (const row of Array.from(departuresBody.children)) {
    const key = row.dataset.rowKey;
    const previousTop = oldPositions.get(key);
    const nextTop = row.getBoundingClientRect().top;

    if (previousTop == null) {
      row.animate(
        [
          { opacity: 0, transform: "translateY(10px) scale(0.985)" },
          { opacity: 1, transform: "translateY(0) scale(1)" },
        ],
        { duration: 700, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)" }
      );
      continue;
    }

    const delta = previousTop - nextTop;
    if (Math.abs(delta) < 1) {
      continue;
    }

    row.animate(
      [
        { transform: `translateY(${delta}px)` },
        { transform: "translateY(0)" },
      ],
      { duration: 860, easing: "cubic-bezier(0.2, 0.8, 0.2, 1)" }
    );
  }
}

function animateRowExit(row) {
  row.animate(
    [
      { opacity: 1, transform: "translateY(0) scale(1)" },
      { opacity: 0, transform: "translateY(-8px) scale(0.985)" },
    ],
    { duration: 500, easing: "ease-out" }
  );
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

function animateHeaderTransition(previousView, nextView) {
  const headers = Array.from(departuresHead.querySelectorAll("th"));
  headers.forEach((header, index) => {
    header.animate(
      [
        { opacity: previousView && previousView !== nextView ? 0.4 : 0, transform: "translateY(-10px)" },
        { opacity: 1, transform: "translateY(0)" },
      ],
      {
        duration: previousView && previousView !== nextView ? 340 : 220,
        delay: index * 28,
        easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
        fill: "both",
      }
    );
  });
}

function setFlightsCount(count) {
  visibleCount.textContent = `Flights: ${count}`;
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

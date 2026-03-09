const state = {
  payload: null,
  activeFilter: "all",
  activeTheme: readStorage("mspage-gcon-theme") || "light",
  lastView: null,
};

const params = new URLSearchParams(window.location.search);
const snapshotPath = params.get("snapshot") || "ops.json";
const previewNow = readPreviewNow(params.get("previewNow"));
const animeApi = window.anime || {};
const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;

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
  lastUpdatedInline.textContent = `Updated ${formatter.format(new Date(generatedAt))} · MSP DL`;
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
    animateFilterPress(button);
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
  const financeView = isFinanceView();
  const previousRows = Array.from(departuresBody.querySelectorAll(".board-row"));
  const oldPositions = new Map(previousRows.map((row) => [row.dataset.rowKey, row.getBoundingClientRect().top]));
  const existingRows = new Map(previousRows.map((row) => [row.dataset.rowKey, row]));
  const desiredKeys = new Set(departures.map((departure) => rowKeyFor(departure, financeView)));
  const exitingRows = previousRows.filter((row) => !desiredKeys.has(row.dataset.rowKey));

  setFlightsCount(departures.length);

  if (departures.length === 0) {
    emptyState.classList.remove("hidden");
  } else {
    emptyState.classList.add("hidden");
  }

  const fragment = document.createDocumentFragment();
  departures.forEach((departure, index) => {
    const key = rowKeyFor(departure, financeView);
    const row = existingRows.get(key) || document.createElement("tr");
    row.dataset.rowKey = key;
    row.dataset.rowIndex = String(index);
    row.className = "board-row";

    const urgencyBand = financeView ? null : getUrgencyBand(departure);
    if (urgencyBand) {
      row.classList.add("is-window", `is-window-${urgencyBand}`);
    }

    updateRowContent(row, departure, financeView);
    fragment.appendChild(row);
  });

  departuresBody.replaceChildren(fragment, ...exitingRows);
  animateRows(departures, financeView, oldPositions, existingRows, exitingRows);
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
  animateThemeCycle();
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

  stopAnimations(tableWrap);
  animateTargets(tableWrap, {
    opacity: [0.84, 1],
    translateY: [6, 0],
    duration: 320,
    ease: "cubic-bezier(0.2, 0.8, 0.2, 1)",
  });
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

function animateRows(departures, financeView, oldPositions, existingRows, exitingRows) {
  const stagger = createStagger(28, 0);
  const rows = Array.from(departuresBody.querySelectorAll(".board-row")).filter(
    (row) => !exitingRows.includes(row)
  );

  rows.forEach((row, index) => {
    const key = row.dataset.rowKey;
    const previousTop = oldPositions.get(key);
    const nextTop = row.getBoundingClientRect().top;
    const isExisting = existingRows.has(key);

    stopAnimations(row);

    if (!isExisting) {
      animateTargets(row, {
        opacity: [0, 1],
        translateY: [14, 0],
        scale: [0.985, 1],
        duration: 560,
        delay: stagger(index),
        ease: "cubic-bezier(0.2, 0.8, 0.2, 1)",
      });
      return;
    }

    if (previousTop == null) {
      return;
    }

    const delta = previousTop - nextTop;
    if (Math.abs(delta) < 1) {
      return;
    }

    animateTargets(row, {
      translateY: [delta, 0],
      duration: 900,
      delay: Math.min(index, 5) * 24,
      ease: "cubic-bezier(0.16, 1, 0.3, 1)",
    });
  });

  exitingRows.forEach((row) => {
    row.classList.add("is-exiting");
    stopAnimations(row);
    animateTargets(row, {
      opacity: [1, 0],
      translateY: [0, -10],
      scale: [1, 0.985],
      duration: 420,
      ease: "cubic-bezier(0.4, 0, 0.2, 1)",
      onComplete: () => row.remove(),
    });
  });

  if (!financeView && rows.length) {
    const criticalRows = rows.filter((row) => row.classList.contains("is-window-red-4"));
    criticalRows.forEach((row) => {
      animateCriticalRow(row);
    });
  }
}

function animateThemeCycle() {
  themeCycle.classList.add("is-spinning");
  const icon = themeCycle.querySelector("svg");
  if (icon) {
    stopAnimations(icon);
    animateTargets(icon, {
      rotate: [-24, 0],
      scale: [0.86, 1],
      duration: 440,
      ease: "cubic-bezier(0.16, 1, 0.3, 1)",
      onComplete: () => themeCycle.classList.remove("is-spinning"),
    });
  }
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

function updateFilterIndicator(instant = false) {
  const indicator = podFilters.querySelector(".filter-indicator");
  const activeButton = podFilters.querySelector(".pill.active");
  if (!indicator || !activeButton) {
    return;
  }

  const containerRect = podFilters.getBoundingClientRect();
  const buttonRect = activeButton.getBoundingClientRect();
  const left = buttonRect.left - containerRect.left;
  const top = buttonRect.top - containerRect.top;

  if (!indicator.dataset.ready || instant || prefersReducedMotion) {
    indicator.style.width = `${buttonRect.width}px`;
    indicator.style.height = `${buttonRect.height}px`;
    indicator.style.transform = `translate(${left}px, ${top}px)`;
    indicator.dataset.ready = "true";
    return;
  }

  stopAnimations(indicator);
  animateTargets(indicator, {
    width: [indicator.offsetWidth, buttonRect.width],
    height: [indicator.offsetHeight, buttonRect.height],
    translateX: [getTranslateAxis(indicator, "x"), left],
    translateY: [getTranslateAxis(indicator, "y"), top],
    duration: 540,
    ease: "cubic-bezier(0.16, 1, 0.3, 1)",
    onComplete: () => {
      indicator.style.width = `${buttonRect.width}px`;
      indicator.style.height = `${buttonRect.height}px`;
      indicator.style.transform = `translate(${left}px, ${top}px)`;
    },
  });
}

function animateHeaderTransition(previousView, nextView) {
  const headers = Array.from(departuresHead.querySelectorAll("th"));
  headers.forEach((header, index) => {
    stopAnimations(header);
    animateTargets(header, {
      opacity: [previousView && previousView !== nextView ? 0.3 : 0, 1],
      translateY: [previousView && previousView !== nextView ? -12 : -6, 0],
      duration: previousView && previousView !== nextView ? 360 : 240,
      delay: index * 36,
      ease: "cubic-bezier(0.2, 0.8, 0.2, 1)",
    });
  });
}

function animateFilterPress(button) {
  stopAnimations(button);
  animateTargets(button, {
    scale: [1, 0.96, 1],
    duration: 260,
    ease: "cubic-bezier(0.2, 0.8, 0.2, 1)",
  });
}

function animateCriticalRow(row) {
  const cells = Array.from(row.children);
  if (!cells.length || prefersReducedMotion) {
    return;
  }

  cells.forEach((cell) => {
    stopAnimations(cell);
    animateTargets(cell, {
      backgroundPositionX: ["130%", "-20%"],
      duration: 760,
      ease: "linear",
      loop: true,
    });
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

function animateTargets(targets, params) {
  const items = Array.isArray(targets) ? targets : [targets];
  if (!items.length) {
    return null;
  }

  if (!prefersReducedMotion && typeof animeApi.animate === "function") {
    try {
      return animeApi.animate(items, params);
    } catch (error) {
      try {
        return animeApi.animate({ targets: items, ...params });
      } catch (fallbackError) {
        return animateFallback(items, params);
      }
    }
  }

  return animateFallback(items, params);
}

function animateFallback(targets, params) {
  const duration = params.duration ?? 0;
  const delayValue = params.delay;
  const easing = params.ease || "ease-out";
  const loop = Boolean(params.loop);

  targets.forEach((target, index) => {
    const delay = typeof delayValue === "function" ? delayValue(index, target, targets) : delayValue || 0;
    const keyframes = buildKeyframesFromParams(params, target);
    if (!keyframes.length) {
      return;
    }

    const animation = target.animate(keyframes, {
      duration,
      delay,
      easing,
      iterations: loop ? Number.POSITIVE_INFINITY : 1,
      fill: "both",
    });

    if (typeof params.onComplete === "function" && !loop) {
      animation.addEventListener("finish", () => params.onComplete());
    }
  });

  return null;
}

function buildKeyframesFromParams(params, target) {
  const frames = [{}, {}];
  let hasFrame = false;

  for (const [key, value] of Object.entries(params)) {
    if (["duration", "delay", "ease", "loop", "onComplete", "onUpdate"].includes(key)) {
      continue;
    }

    const values = Array.isArray(value) ? value : [null, value];
    const start = values[0];
    const end = values[values.length - 1];

    if (key === "translateY") {
      frames[0].transform = mergeTransform(frames[0].transform, `translateY(${asUnit(start || 0, "px")})`);
      frames[1].transform = mergeTransform(frames[1].transform, `translateY(${asUnit(end || 0, "px")})`);
      hasFrame = true;
      continue;
    }

    if (key === "translateX") {
      frames[0].transform = mergeTransform(frames[0].transform, `translateX(${asUnit(start || 0, "px")})`);
      frames[1].transform = mergeTransform(frames[1].transform, `translateX(${asUnit(end || 0, "px")})`);
      hasFrame = true;
      continue;
    }

    if (key === "scale") {
      frames[0].transform = mergeTransform(frames[0].transform, `scale(${start ?? 1})`);
      frames[1].transform = mergeTransform(frames[1].transform, `scale(${end ?? 1})`);
      hasFrame = true;
      continue;
    }

    if (key === "rotate") {
      frames[0].transform = mergeTransform(frames[0].transform, `rotate(${asUnit(start || 0, "deg")})`);
      frames[1].transform = mergeTransform(frames[1].transform, `rotate(${asUnit(end || 0, "deg")})`);
      hasFrame = true;
      continue;
    }

    if (key === "backgroundPositionX") {
      frames[0].backgroundPositionX = start ?? getComputedStyle(target).backgroundPositionX;
      frames[1].backgroundPositionX = end ?? getComputedStyle(target).backgroundPositionX;
      hasFrame = true;
      continue;
    }

    frames[0][key] = start;
    frames[1][key] = end;
    hasFrame = true;
  }

  return hasFrame ? frames : [];
}

function stopAnimations(target) {
  if (typeof animeApi.remove === "function") {
    try {
      animeApi.remove(target);
    } catch (error) {
      // Ignore; fallback animations are handled by WAAPI below.
    }
  }

  if (typeof target.getAnimations === "function") {
    target.getAnimations().forEach((animation) => animation.cancel());
  }
}

function createStagger(step, start) {
  if (!prefersReducedMotion && typeof animeApi.stagger === "function") {
    try {
      return animeApi.stagger(step, { start });
    } catch (error) {
      try {
        return animeApi.stagger(step, start);
      } catch (fallbackError) {
        return (index) => start + index * step;
      }
    }
  }

  return (index) => start + index * step;
}

function getTranslateAxis(element, axis) {
  const transform = element.style.transform || "";
  const match = transform.match(/translate\(([-\d.]+)px,\s*([-\d.]+)px\)/);
  if (!match) {
    return 0;
  }
  return axis === "x" ? Number(match[1]) : Number(match[2]);
}

function mergeTransform(current, addition) {
  return current ? `${current} ${addition}` : addition;
}

function asUnit(value, unit) {
  return typeof value === "number" ? `${value}${unit}` : value;
}

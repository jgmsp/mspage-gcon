const state = {
  manifest: null,
  activePodId: null,
  activeSourceId: null,
  activeSelectId: null,
  activeSlotId: null,
  pendingOpen: false,
  diagnostics: null,
  activeTheme: readStorage("mspage-gcon-theme") || "light",
};

const generatedAt = document.getElementById("generated-at");
const themeCycle = document.getElementById("theme-cycle");
const filterStep = document.getElementById("flow-filter");
const sourceStep = document.getElementById("flow-select");
const selectStep = document.getElementById("flow-subselect");
const whichStep = document.getElementById("flow-which");
const viewerStep = document.getElementById("flow-viewer");
const podFilters = document.getElementById("pod-filters");
const sourceFilters = document.getElementById("source-filters");
const selectFilters = document.getElementById("select-filters");
const slotFilters = document.getElementById("slot-filters");
const slotKicker = document.getElementById("slot-kicker");
const slotTitle = document.getElementById("slot-title");
const slotSelection = document.getElementById("slot-selection");
const slotMeta = document.getElementById("slot-meta");
const slotSharedBadge = document.getElementById("slot-shared-badge");
const picturePanel = document.getElementById("picture-panel");
const pogImage = document.getElementById("pog-image");
const pendingToggle = document.getElementById("pending-toggle");
const pendingPanel = document.getElementById("pending-panel");
const pendingTitle = document.getElementById("pending-title");
const pendingMeta = document.getElementById("pending-meta");
const pendingImage = document.getElementById("pending-image");
const pogStatusLine = document.getElementById("pog-status-line");

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
bindEvents();
loadManifest().catch((error) => {
  console.error(error);
  slotMeta.textContent = "Unable to load POG manifest.";
});

function bindEvents() {
  themeCycle?.addEventListener("click", cycleTheme);
  pendingToggle?.addEventListener("click", () => {
    state.pendingOpen = !state.pendingOpen;
    renderPendingPanel(getSelectedSlot());
  });
}

async function loadManifest() {
  const [manifestResponse, diagnosticsResponse] = await Promise.all([
    fetch("./manifest.json"),
    fetch("./diagnostics.json"),
  ]);
  if (!manifestResponse.ok) {
    throw new Error(`Failed to load manifest: ${manifestResponse.status}`);
  }
  state.manifest = await manifestResponse.json();
  state.diagnostics = diagnosticsResponse.ok ? await diagnosticsResponse.json() : null;
  initializeState();
  render();
}

function initializeState() {
  state.activePodId = null;
  state.activeSourceId = null;
  state.activeSelectId = null;
  state.activeSlotId = null;
  state.pendingOpen = false;
}

function render() {
  renderMeta();
  updateThemeControl(currentTheme());
  renderPods();
  renderSources();
  renderSelects();
  renderSlots();
  renderFlowVisibility();
  renderSelectedSlot();
  renderStatus();
}

function renderMeta() {
  const publishedAt = state.manifest?.board?.generatedAt;
  generatedAt.textContent = publishedAt ? formatDateTime(publishedAt) : "Awaiting snapshot";
}

function renderStatus() {
  const diagnostics = state.diagnostics;
  if (!diagnostics) {
    pogStatusLine.textContent = "Status: Diagnostics unavailable";
    return;
  }
  const parts = [`Status: ${capitalize(diagnostics.status || "unknown")}`];
  if (diagnostics.lastSuccessAt) {
    parts.push(`Last success ${formatDateTime(diagnostics.lastSuccessAt)}`);
  }
  if (diagnostics.sourceMode) {
    parts.push(`Mode ${diagnostics.sourceMode}`);
  }
  pogStatusLine.textContent = parts.join(" · ");
}

function renderFlowVisibility() {
  filterStep.classList.remove("hidden");
  sourceStep.classList.toggle("hidden", !state.activePodId);
  selectStep.classList.toggle("hidden", !state.activeSourceId);
  whichStep.classList.toggle("hidden", !state.activeSelectId);
  viewerStep.classList.toggle("hidden", !state.activeSlotId);
}

function renderPods() {
  const pods = state.manifest?.pods || [];
  podFilters.replaceChildren(
    ...pods.map((pod) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = pod.id === state.activePodId ? "pill active" : "pill";
      if (!pod.enabled) {
        button.classList.add("disabled");
      }
      button.textContent = pod.label;
      button.disabled = !pod.enabled;
      button.addEventListener("click", () => {
        if (!pod.enabled) {
          return;
        }
        state.activePodId = pod.id;
        state.activeSourceId = null;
        state.activeSelectId = null;
        state.activeSlotId = null;
        state.pendingOpen = false;
        render();
      });
      return button;
    })
  );
}

function renderSources() {
  const sources = getSourcesForActivePod();
  sourceFilters.replaceChildren(
    ...sources.map((source) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = source.id === state.activeSourceId ? "pill active" : "pill";
      button.textContent = source.label.replace(/^MSP - CEGM /, "");
      button.addEventListener("click", () => {
        state.activeSourceId = source.id;
        state.activeSelectId = null;
        state.activeSlotId = null;
        state.pendingOpen = false;
        render();
      });
      return button;
    })
  );
}

function renderSelects() {
  const selects = getSelectsForActiveSource();
  selectFilters.replaceChildren(
    ...selects.map((select) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = select.id === state.activeSelectId ? "pill active" : "pill";
      button.textContent = select.label;
      button.addEventListener("click", () => {
        state.activeSelectId = select.id;
        state.activeSlotId = null;
        state.pendingOpen = false;
        render();
      });
      return button;
    })
  );
}

function renderSlots() {
  const slots = getSlotsForActiveSelect();
  slotFilters.replaceChildren(
    ...slots.map((slot) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = slot.id === state.activeSlotId ? "pill active" : "pill";
      button.textContent = slot.label;
      button.addEventListener("click", () => {
        state.activeSlotId = slot.id;
        render();
      });
      return button;
    })
  );
}

function renderSelectedSlot() {
  const slot = getSelectedSlot();
  if (!slot) {
    slotKicker.textContent = "Current slot";
    slotTitle.textContent = "No slot selected";
    slotSelection.textContent = "Selected: none";
    slotMeta.textContent = "Choose a pod, source, section, and grouped slot to view a POG.";
    slotSharedBadge.classList.add("hidden");
    pogImage.removeAttribute("src");
    picturePanel.classList.add("hidden");
    renderPendingPanel(null);
    return;
  }

  const effectiveCurrent = resolveEffectiveCurrent(slot);
  const activePod = getActivePod();
  const activeSource = getActiveSource();
  slotKicker.textContent = `${activePod?.label || ""} / ${activeSource?.label.replace(/^MSP - CEGM /, "") || ""} / ${slot.selectKey}`;
  slotTitle.textContent = slot.title || slot.sourceSlotKey || slot.label;
  slotSelection.textContent = `Selected: ${slot.label}`;
  slotMeta.textContent = buildCurrentMeta(slot, effectiveCurrent);
  slotSharedBadge.textContent = slot.sharedGroup ? `Grouped ${slot.sourceSlotKey}` : "";
  slotSharedBadge.classList.toggle("hidden", !slot.sharedGroup);
  pogImage.src = effectiveCurrent.imagePath;
  pogImage.alt = `${slot.title || slot.sourceSlotKey || slot.label} planogram`;
  picturePanel.classList.remove("hidden");
  renderPendingPanel(slot);
}

function resolveEffectiveCurrent(slot) {
  const now = Date.now();
  if (slot.pending && slot.current?.endAt) {
    const endAt = Date.parse(slot.current.endAt);
    if (!Number.isNaN(endAt) && endAt <= now) {
      return slot.pending;
    }
  }
  return slot.current;
}

function buildCurrentMeta(slot, current) {
  const parts = [current.displayName];
  if (current.endAt) {
    parts.push(`Expires ${formatDateTime(current.endAt)}`);
  }
  if (slot.pending) {
    parts.push("Pending successor available");
  }
  return parts.join(" · ");
}

function renderPendingPanel(slot) {
  pendingPanel.classList.toggle("hidden", !state.pendingOpen);
  pendingToggle.setAttribute("aria-expanded", state.pendingOpen ? "true" : "false");
  if (!slot?.pending) {
    pendingTitle.textContent = "No pending successor";
    pendingMeta.textContent = "This grouped slot does not have a published pending replacement.";
    pendingImage.classList.add("hidden");
    pendingImage.removeAttribute("src");
    return;
  }

  pendingTitle.textContent = slot.title || slot.sourceSlotKey || `${slot.label} pending`;
  pendingMeta.textContent = slot.current?.endAt
    ? `Selected ${slot.label} · promotes after ${formatDateTime(slot.current.endAt)}`
    : `Selected ${slot.label} · pending successor is ready.`;
  pendingImage.src = slot.pending.imagePath;
  pendingImage.alt = `${slot.title || slot.sourceSlotKey || slot.label} pending planogram`;
  pendingImage.classList.remove("hidden");
}

function getActivePod() {
  return (state.manifest?.pods || []).find((pod) => pod.id === state.activePodId) || null;
}

function getActiveSource() {
  return (state.manifest?.sources || []).find((source) => source.id === state.activeSourceId) || null;
}

function getSourcesForActivePod() {
  if (!state.activePodId) {
    return [];
  }
  return (state.manifest?.sources || []).filter((source) => source.podId === state.activePodId);
}

function getSelectsForActiveSource() {
  if (!state.activeSourceId) {
    return [];
  }
  return (state.manifest?.selects || []).filter((select) => select.sourceId === state.activeSourceId);
}

function getSlotsForActiveSelect() {
  if (!state.activeSelectId) {
    return [];
  }
  return (state.manifest?.slots || []).filter((slot) => slot.selectId === state.activeSelectId);
}

function getSelectedSlot() {
  return (state.manifest?.slots || []).find((slot) => slot.id === state.activeSlotId) || null;
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
    timeZone: "America/Chicago",
  }).format(date);
}

function capitalize(value) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : "";
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
  if (!themeCycle) {
    return;
  }
  themeCycle.innerHTML = THEME_ICONS[theme.id] || THEME_ICONS.light;
  themeCycle.title = `Cycle theme. Current theme: ${theme.label}`;
  themeCycle.setAttribute("aria-label", `Cycle theme. Current theme: ${theme.label}`);
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

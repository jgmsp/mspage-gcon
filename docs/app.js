const state = {
  payload: null,
  activePod: "all",
};

const departuresBody = document.getElementById("departures-body");
const podFilters = document.getElementById("pod-filters");
const lastUpdated = document.getElementById("last-updated");
const visibleCount = document.getElementById("visible-count");
const emptyState = document.getElementById("empty-state");

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
  renderPodFilters();
  renderRows();
}

function renderMeta() {
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

function renderPodFilters() {
  const pods = state.payload?.pods ?? [];
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
    state.activePod = id;
    render();
  });
  return button;
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
    return tr;
  });

  departuresBody.replaceChildren(...rows);
}

function getVisibleDepartures() {
  const departures = state.payload?.departures ?? [];
  if (state.activePod === "all") {
    return departures;
  }
  return departures.filter((departure) => departure.podId === state.activePod);
}

loadSnapshot().catch((error) => {
  console.error(error);
  emptyState.classList.remove("hidden");
  emptyState.textContent = "Unable to load the current snapshot.";
});

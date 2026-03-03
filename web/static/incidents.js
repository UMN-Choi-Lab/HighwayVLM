const cameraFilter = document.getElementById("camera-filter");
const limitFilter = document.getElementById("limit-filter");
const refreshNow = document.getElementById("refresh-now");
const incidentsList = document.getElementById("incidents-list");
const emptyState = document.getElementById("incidents-empty");
const incidentTotal = document.getElementById("incident-total");
const latestIncident = document.getElementById("latest-incident");
const hourlyTotal = document.getElementById("hourly-total");
const latestHour = document.getElementById("latest-hour");
const subtitle = document.getElementById("page-subtitle");

const query = new URLSearchParams(window.location.search);
let initialCameraId = query.get("camera_id") || "";
const camerasById = new Map();

const fetchJson = async (url) => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed: ${url}`);
  }
  return response.json();
};

const formatDateTime = (value) => {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const formatType = (value) =>
  value
    ? value
        .toString()
        .replace(/_/g, " ")
        .replace(/\b\w/g, (match) => match.toUpperCase())
    : "Unknown";

const frameUrl = (imagePath) => {
  if (!imagePath) return null;
  const normalized = imagePath
    .toString()
    .split(/[\\/]+/)
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return normalized ? `/frames/${normalized}` : null;
};

const selectedCameraId = () => (cameraFilter?.value || "").trim();
const selectedLimit = () => Number.parseInt(limitFilter?.value || "250", 10) || 250;

const buildCameraOptionLabel = (camera) => {
  const base = camera?.name || camera?.camera_id || "Unknown camera";
  const route = `${camera?.corridor || ""} ${camera?.direction || ""}`.trim();
  return route ? `${base} (${route})` : base;
};

const updateQuery = () => {
  const id = selectedCameraId();
  const params = new URLSearchParams(window.location.search);
  if (id) {
    params.set("camera_id", id);
  } else {
    params.delete("camera_id");
  }
  const suffix = params.toString();
  const next = suffix ? `?${suffix}` : window.location.pathname;
  window.history.replaceState({}, "", next);
};

const updateSubtitle = () => {
  const id = selectedCameraId();
  if (!id) {
    subtitle.textContent = "Full incident history with timestamps, camera context, and detailed summaries.";
    return;
  }
  const camera = camerasById.get(id);
  const label = camera ? buildCameraOptionLabel(camera) : id;
  subtitle.textContent = `Incident history filtered to ${label}.`;
};

const renderOverview = (overview) => {
  incidentTotal.textContent = (overview?.incident_total ?? 0).toString();
  latestIncident.textContent = formatDateTime(overview?.latest_incident_at);
  hourlyTotal.textContent = (overview?.hourly_total ?? 0).toString();
  latestHour.textContent = formatDateTime(overview?.latest_hour_bucket);
};

const renderIncidents = (items) => {
  incidentsList.innerHTML = "";
  if (!items.length) {
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;
  items.forEach((item) => {
    const cameraName = item.camera_name || camerasById.get(item.camera_id)?.name || item.camera_id || "Unknown camera";
    const severity = (item.severity || "unknown").toLowerCase();
    const image = frameUrl(item.image_path);

    const card = document.createElement("article");
    card.className = "incident-card";

    const left = document.createElement("div");
    left.className = "thumb-wrap";
    if (image) {
      const img = document.createElement("img");
      img.src = image;
      img.alt = `Incident frame for ${cameraName}`;
      img.loading = "lazy";
      img.decoding = "async";
      left.appendChild(img);
    } else {
      const blank = document.createElement("div");
      blank.className = "thumb-empty";
      blank.textContent = "No frame available";
      left.appendChild(blank);
    }

    const right = document.createElement("div");
    const top = document.createElement("div");
    top.className = "meta-top";

    const title = document.createElement("p");
    title.className = "meta-title";
    title.textContent = cameraName;

    const pill = document.createElement("span");
    pill.className = `pill ${severity}`;
    pill.textContent = severity;

    top.appendChild(title);
    top.appendChild(pill);

    const meta = document.createElement("div");
    meta.className = "meta-grid";
    meta.innerHTML = [
      `<div><span>Type</span><br>${formatType(item.incident_type)}</div>`,
      `<div><span>Camera</span><br>${item.camera_id || "--"}</div>`,
      `<div><span>Created</span><br>${formatDateTime(item.created_at)}</div>`,
      `<div><span>Captured</span><br>${formatDateTime(item.captured_at)}</div>`,
      `<div><span>Traffic</span><br>${formatType(item.traffic_state)}</div>`,
      `<div><span>Direction</span><br>${item.observed_direction || item.direction || "--"}</div>`,
    ].join("");

    const description = document.createElement("p");
    description.className = "detail";
    description.innerHTML = `<strong>Description:</strong> ${item.description || "No description provided."}`;

    const notes = document.createElement("p");
    notes.className = "detail";
    notes.innerHTML = `<strong>Summary:</strong> ${item.notes || "No summary recorded."}`;

    const links = document.createElement("div");
    links.className = "inline-links";
    if (image) {
      const frameLink = document.createElement("a");
      frameLink.href = image;
      frameLink.target = "_blank";
      frameLink.rel = "noreferrer";
      frameLink.textContent = "Open frame";
      links.appendChild(frameLink);
    }
    const hourlyLink = document.createElement("a");
    hourlyLink.href = `/hourly?camera_id=${encodeURIComponent(item.camera_id || "")}`;
    hourlyLink.textContent = "View hourly checks";
    links.appendChild(hourlyLink);

    right.appendChild(top);
    right.appendChild(meta);
    right.appendChild(description);
    right.appendChild(notes);
    right.appendChild(links);

    card.appendChild(left);
    card.appendChild(right);
    incidentsList.appendChild(card);
  });
};

const loadFilters = async () => {
  const cameras = await fetchJson("/cameras");
  cameraFilter.innerHTML = "";

  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = "All cameras";
  cameraFilter.appendChild(allOption);

  cameras.forEach((camera) => {
    camerasById.set(camera.camera_id, camera);
    const option = document.createElement("option");
    option.value = camera.camera_id;
    option.textContent = buildCameraOptionLabel(camera);
    cameraFilter.appendChild(option);
  });

  if (initialCameraId && !camerasById.has(initialCameraId)) {
    const unknown = document.createElement("option");
    unknown.value = initialCameraId;
    unknown.textContent = `${initialCameraId} (unknown camera)`;
    cameraFilter.appendChild(unknown);
  }
  cameraFilter.value = initialCameraId || "";
  updateSubtitle();
};

const refresh = async () => {
  const cameraId = selectedCameraId();
  const limit = selectedLimit();
  updateQuery();
  updateSubtitle();

  const cameraQuery = cameraId ? `&camera_id=${encodeURIComponent(cameraId)}` : "";
  const [overview, incidents] = await Promise.all([
    fetchJson(`/api/archive/overview?${cameraId ? `camera_id=${encodeURIComponent(cameraId)}` : ""}`),
    fetchJson(`/api/incidents?limit=${limit}${cameraQuery}`),
  ]);

  renderOverview(overview || {});
  renderIncidents(Array.isArray(incidents) ? incidents : []);
};

const init = async () => {
  await loadFilters();
  await refresh();
};

cameraFilter?.addEventListener("change", () => {
  initialCameraId = selectedCameraId();
  refresh();
});
limitFilter?.addEventListener("change", refresh);
refreshNow?.addEventListener("click", refresh);

init().catch((error) => {
  incidentsList.innerHTML = "";
  emptyState.hidden = false;
  emptyState.textContent = `Failed to load incident archive: ${error.message}`;
});

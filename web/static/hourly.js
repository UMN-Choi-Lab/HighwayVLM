const cameraFilter = document.getElementById("camera-filter");
const limitFilter = document.getElementById("limit-filter");
const refreshNow = document.getElementById("refresh-now");
const hourlyList = document.getElementById("hourly-list");
const emptyState = document.getElementById("hourly-empty");
const hourlyTotal = document.getElementById("hourly-total");
const latestHour = document.getElementById("latest-hour");
const incidentTotal = document.getElementById("incident-total");
const latestIncident = document.getElementById("latest-incident");
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
const selectedLimit = () => Number.parseInt(limitFilter?.value || "168", 10) || 168;

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
    subtitle.textContent = "One saved frame per camera-hour to verify overnight coverage and pipeline health.";
    return;
  }
  const camera = camerasById.get(id);
  const label = camera ? buildCameraOptionLabel(camera) : id;
  subtitle.textContent = `Hourly heartbeat snapshots filtered to ${label}.`;
};

const renderOverview = (overview) => {
  hourlyTotal.textContent = (overview?.hourly_total ?? 0).toString();
  latestHour.textContent = formatDateTime(overview?.latest_hour_bucket);
  incidentTotal.textContent = (overview?.incident_total ?? 0).toString();
  latestIncident.textContent = formatDateTime(overview?.latest_incident_at);
};

const renderHourly = (items) => {
  hourlyList.innerHTML = "";
  if (!items.length) {
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;

  items.forEach((item) => {
    const cameraName = item.camera_name || camerasById.get(item.camera_id)?.name || item.camera_id || "Unknown camera";
    const status = (item.status || "unknown").toLowerCase();
    const image = frameUrl(item.image_path);

    const card = document.createElement("article");
    card.className = "hourly-card";

    const left = document.createElement("div");
    left.className = "thumb-wrap";
    if (image) {
      const img = document.createElement("img");
      img.src = image;
      img.alt = `Hourly snapshot for ${cameraName}`;
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
    pill.className = `pill ${status}`;
    pill.textContent = status;

    top.appendChild(title);
    top.appendChild(pill);

    const meta = document.createElement("div");
    meta.className = "meta-grid";
    meta.innerHTML = [
      `<div><span>Hour bucket</span><br>${formatDateTime(item.hour_bucket)}</div>`,
      `<div><span>Captured</span><br>${formatDateTime(item.captured_at || item.created_at)}</div>`,
      `<div><span>Camera</span><br>${item.camera_id || "--"}</div>`,
      `<div><span>Traffic</span><br>${formatType(item.traffic_state)}</div>`,
      `<div><span>Incident count</span><br>${item.incident_count ?? 0}</div>`,
      `<div><span>Skipped reason</span><br>${item.skipped_reason || "--"}</div>`,
    ].join("");

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
    const incidentsLink = document.createElement("a");
    incidentsLink.href = `/incidents?camera_id=${encodeURIComponent(item.camera_id || "")}`;
    incidentsLink.textContent = "View incidents";
    links.appendChild(incidentsLink);

    right.appendChild(top);
    right.appendChild(meta);

    const summary = document.createElement("p");
    summary.className = "detail";
    summary.innerHTML = `<strong>Summary:</strong> ${item.summary || "No summary recorded."}`;
    right.appendChild(summary);

    const reports = Array.isArray(item.incident_reports) ? item.incident_reports : [];
    const reportText = reports.length
      ? reports
          .map((report) => {
            const kind = formatType(report.incident_type || report.report_kind);
            const severity = report.severity ? ` (${report.severity})` : "";
            const description = report.description || "No description provided.";
            return `${kind}${severity}: ${description}`;
          })
          .join(" | ")
      : "No hourly incident report rows were stored.";
    const reportSummary = document.createElement("p");
    reportSummary.className = "detail";
    reportSummary.innerHTML = `<strong>Incident reports:</strong> ${reportText}`;
    right.appendChild(reportSummary);

    if (item.error) {
      const error = document.createElement("p");
      error.className = "detail";
      error.innerHTML = `<strong>Error:</strong> ${item.error}`;
      right.appendChild(error);
    }

    right.appendChild(links);

    card.appendChild(left);
    card.appendChild(right);
    hourlyList.appendChild(card);
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
  const [overview, hourly] = await Promise.all([
    fetchJson(`/api/archive/overview?${cameraId ? `camera_id=${encodeURIComponent(cameraId)}` : ""}`),
    fetchJson(`/api/hourly?limit=${limit}${cameraQuery}`),
  ]);

  renderOverview(overview || {});
  renderHourly(Array.isArray(hourly) ? hourly : []);
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
  hourlyList.innerHTML = "";
  emptyState.hidden = false;
  emptyState.textContent = `Failed to load hourly archive: ${error.message}`;
});

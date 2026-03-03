const cameraFilter = document.getElementById("camera-filter");
const hoursFilter = document.getElementById("hours-filter");
const refreshNow = document.getElementById("refresh-now");
const overnightList = document.getElementById("overnight-list");
const emptyState = document.getElementById("overnight-empty");
const cameraTotal = document.getElementById("camera-total");
const hourlyTotal = document.getElementById("hourly-total");
const reportTotal = document.getElementById("report-total");
const cameraIncidentTotal = document.getElementById("camera-incident-total");
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
const selectedHours = () => Number.parseInt(hoursFilter?.value || "12", 10) || 12;

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
  const hours = selectedHours();
  if (!id) {
    subtitle.textContent = `Morning-ready view of each camera's hourly snapshots and incident reports from the last ${hours} hours.`;
    return;
  }
  const camera = camerasById.get(id);
  const label = camera ? buildCameraOptionLabel(camera) : id;
  subtitle.textContent = `Overnight review for ${label} across the last ${hours} hours.`;
};

const cutoffDate = () => {
  const now = Date.now();
  return new Date(now - selectedHours() * 60 * 60 * 1000);
};

const inWindow = (row) => {
  const value = row?.hour_bucket || row?.captured_at || row?.created_at;
  if (!value) return false;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  return date >= cutoffDate();
};

const renderStats = (rows) => {
  const cameraIds = new Set();
  const cameraIdsWithIncidents = new Set();
  let reports = 0;

  rows.forEach((row) => {
    if (row.camera_id) {
      cameraIds.add(row.camera_id);
    }
    const incidentReports = Array.isArray(row.incident_reports) ? row.incident_reports : [];
    reports += incidentReports.length;
    if ((row.incident_count || 0) > 0) {
      cameraIdsWithIncidents.add(row.camera_id);
    }
  });

  cameraTotal.textContent = cameraIds.size.toString();
  hourlyTotal.textContent = rows.length.toString();
  reportTotal.textContent = reports.toString();
  cameraIncidentTotal.textContent = cameraIdsWithIncidents.size.toString();
};

const groupRows = (rows) => {
  const groups = new Map();
  rows.forEach((row) => {
    const key = row.camera_id || "unknown";
    const current = groups.get(key) || [];
    current.push(row);
    groups.set(key, current);
  });
  return [...groups.entries()]
    .map(([cameraId, items]) => ({
      cameraId,
      items: items.sort((a, b) => String(b.hour_bucket || "").localeCompare(String(a.hour_bucket || ""))),
    }))
    .sort((a, b) => a.cameraId.localeCompare(b.cameraId));
};

const renderGroups = (rows) => {
  overnightList.innerHTML = "";
  if (!rows.length) {
    emptyState.hidden = false;
    return;
  }
  emptyState.hidden = true;

  const groups = groupRows(rows);
  groups.forEach(({ cameraId, items }) => {
    const first = items[0];
    const cameraName = first.camera_name || camerasById.get(cameraId)?.name || cameraId || "Unknown camera";
    const incidentHours = items.filter((item) => (item.incident_count || 0) > 0).length;
    const healthyHours = items.filter((item) => item.status === "healthy").length;
    const latestImage = frameUrl(first.image_path);

    const card = document.createElement("article");
    card.className = "hourly-card";

    const left = document.createElement("div");
    left.className = "thumb-wrap";
    if (latestImage) {
      const img = document.createElement("img");
      img.src = latestImage;
      img.alt = `Latest overnight frame for ${cameraName}`;
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
    pill.className = `pill ${incidentHours ? "incident" : "healthy"}`;
    pill.textContent = incidentHours ? "incidents in window" : "no incidents in window";

    top.appendChild(title);
    top.appendChild(pill);

    const meta = document.createElement("div");
    meta.className = "meta-grid";
    meta.innerHTML = [
      `<div><span>Camera</span><br>${cameraId || "--"}</div>`,
      `<div><span>Rows in window</span><br>${items.length}</div>`,
      `<div><span>Incident hours</span><br>${incidentHours}</div>`,
      `<div><span>Healthy hours</span><br>${healthyHours}</div>`,
      `<div><span>Latest bucket</span><br>${formatDateTime(first.hour_bucket)}</div>`,
      `<div><span>Latest traffic</span><br>${formatType(first.traffic_state)}</div>`,
    ].join("");

    const summary = document.createElement("p");
    summary.className = "detail";
    summary.innerHTML = `<strong>Latest summary:</strong> ${first.summary || "No summary recorded."}`;

    const timeline = document.createElement("p");
    timeline.className = "detail";
    timeline.innerHTML = `<strong>Window timeline:</strong> ${items
      .map((item) => {
        const when = formatDateTime(item.hour_bucket);
        const status = formatType(item.status);
        const count = item.incident_count ?? 0;
        return `${when} [${status}, incidents=${count}]`;
      })
      .join(" | ")}`;

    const incidentText = items
      .flatMap((item) =>
        (Array.isArray(item.incident_reports) ? item.incident_reports : [])
          .filter((report) => (report.report_kind || "").toLowerCase() !== "no_incident")
          .map((report) => {
            const when = formatDateTime(item.hour_bucket);
            const kind = formatType(report.incident_type || report.report_kind);
            const severity = report.severity ? ` (${report.severity})` : "";
            const description = report.description || "No description provided.";
            return `${when}: ${kind}${severity}: ${description}`;
          })
      );

    const reports = document.createElement("p");
    reports.className = "detail";
    reports.innerHTML = `<strong>Incident reports:</strong> ${
      incidentText.length ? incidentText.join(" | ") : "No incident reports in this window."
    }`;

    const links = document.createElement("div");
    links.className = "inline-links";
    if (latestImage) {
      const frameLink = document.createElement("a");
      frameLink.href = latestImage;
      frameLink.target = "_blank";
      frameLink.rel = "noreferrer";
      frameLink.textContent = "Open latest frame";
      links.appendChild(frameLink);
    }
    const hourlyLink = document.createElement("a");
    hourlyLink.href = `/hourly?camera_id=${encodeURIComponent(cameraId || "")}`;
    hourlyLink.textContent = "View hourly checks";
    links.appendChild(hourlyLink);

    const incidentsLink = document.createElement("a");
    incidentsLink.href = `/incidents?camera_id=${encodeURIComponent(cameraId || "")}`;
    incidentsLink.textContent = "View incidents";
    links.appendChild(incidentsLink);

    right.appendChild(top);
    right.appendChild(meta);
    right.appendChild(summary);
    right.appendChild(timeline);
    right.appendChild(reports);
    right.appendChild(links);

    card.appendChild(left);
    card.appendChild(right);
    overnightList.appendChild(card);
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
  updateQuery();
  updateSubtitle();

  const cameraQuery = cameraId ? `&camera_id=${encodeURIComponent(cameraId)}` : "";
  const hourly = await fetchJson(`/api/hourly?limit=720${cameraQuery}`);
  const rows = (Array.isArray(hourly) ? hourly : []).filter(inWindow);

  renderStats(rows);
  renderGroups(rows);
};

const init = async () => {
  await loadFilters();
  await refresh();
};

cameraFilter?.addEventListener("change", () => {
  initialCameraId = selectedCameraId();
  refresh();
});
hoursFilter?.addEventListener("change", refresh);
refreshNow?.addEventListener("click", refresh);

init().catch((error) => {
  overnightList.innerHTML = "";
  emptyState.hidden = false;
  emptyState.textContent = `Failed to load overnight monitor: ${error.message}`;
});

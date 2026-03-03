const REFRESH_SECONDS = 30;

const grid = document.getElementById("camera-grid");
const lastUpdated = document.getElementById("last-updated");
const lastUpdatedFull = document.getElementById("last-updated-full");
const refreshInterval = document.getElementById("refresh-interval");
const appStatus = document.getElementById("app-status");
const statusDetail = document.getElementById("status-detail");
const refreshNow = document.getElementById("refresh-now");
const template = document.getElementById("camera-card-template");

refreshInterval.textContent = `${REFRESH_SECONDS}s`;

let refreshing = false;

const formatTime = (value) => {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString();
};

const titleCase = (value) =>
  value
    ? value
        .toString()
        .replace(/_/g, " ")
        .replace(/\b\w/g, (match) => match.toUpperCase())
    : "Unknown";

const frameUrlFromPath = (imagePath) => {
  if (!imagePath) return null;
  const normalized = imagePath
    .toString()
    .split(/[\\/]+/)
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return normalized ? `/frames/${normalized}` : null;
};

const withCacheBust = (url, token) => {
  if (!url) return url;
  const separator = url.includes("?") ? "&" : "?";
  const cacheKey = token ? encodeURIComponent(token) : Date.now();
  return `${url}${separator}t=${cacheKey}`;
};

const setStatus = (text, state, detail) => {
  if (!appStatus) return;
  appStatus.textContent = text;
  appStatus.classList.remove("status-loading", "status-live", "status-error");
  appStatus.classList.add(`status-${state}`);
  if (statusDetail) {
    statusDetail.textContent = detail || "";
  }
};

const buildCard = (camera) => {
  const node = template.content.firstElementChild.cloneNode(true);
  const cameraId = camera.camera_id;
  node.dataset.cameraId = cameraId;
  if (camera.snapshot_url) {
    node.dataset.snapshotUrl = camera.snapshot_url;
  }
  node.querySelector(".camera-name").textContent = camera.name || cameraId;
  node.querySelector(".camera-sub").textContent = `${camera.corridor || ""} ${camera.direction || ""}`.trim();
  const link = node.querySelector(".snapshot-link");
  link.href = camera.snapshot_url || "#";
  const incidentsLink = node.querySelector(".incidents-link");
  const hourlyLink = node.querySelector(".hourly-link");
  const encodedCameraId = encodeURIComponent(cameraId || "");
  if (incidentsLink) {
    incidentsLink.href = `/camera/${encodedCameraId}/incidents`;
  }
  if (hourlyLink) {
    hourlyLink.href = `/camera/${encodedCameraId}/hourly`;
  }
  const snapshot = node.querySelector(".snapshot");
  const img = node.querySelector(".snapshot-img");
  img.alt = `Camera snapshot for ${camera.name || cameraId || "camera"}`;
  img.addEventListener("load", () => {
    snapshot.classList.add("is-loaded");
  });
  img.addEventListener("error", () => {
    const fallback = img.dataset.fallbackSrc;
    if (fallback && img.src !== fallback) {
      img.src = fallback;
      return;
    }
    snapshot.classList.remove("is-loaded");
  });
  return node;
};

const normalizeIncidents = (value) => {
  if (!value) return [];
  return Array.isArray(value) ? value : [];
};

const resolveNotes = (analysis, latest, fallback) => {
  const note = analysis?.notes || latest?.notes;
  if (note && note.toString().trim()) {
    return note;
  }
  return fallback;
};

const summarizeError = (value) => {
  if (!value) return "Unknown error";
  const text = value.toString().replace(/^snapshot_failed:\s*/i, "").replace(/^vlm_failed:\s*/i, "");
  if (text.includes("504")) {
    return "Upstream camera source returned 504.";
  }
  if (text.includes("Failed to resolve") || text.includes("NameResolutionError")) {
    return "Snapshot host could not be resolved.";
  }
  return text.length > 96 ? `${text.slice(0, 93)}...` : text;
};

const summarizeSkip = (value) => {
  const normalized = (value || "").toString().trim().toLowerCase();
  if (!normalized) return "No recent skip reason.";
  const labels = {
    unchanged_frame: "Frame unchanged; analysis skipped.",
    vlm_min_interval: "Frame captured; analysis waiting for minimum interval.",
    vlm_error_cooldown: "Frame captured; analysis waiting for error cooldown.",
    vlm_max_calls_per_run: "Frame captured; analysis deferred by per-run limit.",
    vlm_quota_exceeded: "Frame captured; analysis blocked by model quota.",
    empty_snapshot: "Snapshot source returned an empty response.",
  };
  return labels[normalized] || `${titleCase(normalized)}.`;
};

const buildFeedStatus = (latest) => {
  if (latest?.error) {
    return {
      label: "Error",
      className: "source-error",
      detail: summarizeError(latest.error),
    };
  }
  if (latest?.captured_at && latest?.skipped_reason) {
    return {
      label: "Captured",
      className: "source-warn",
      detail: summarizeSkip(latest.skipped_reason),
    };
  }
  if (latest?.captured_at) {
    return {
      label: "Live",
      className: "source-ok",
      detail: "Snapshot source reachable.",
    };
  }
  if (latest?.skipped_reason) {
    return {
      label: "Waiting",
      className: "source-warn",
      detail: summarizeSkip(latest.skipped_reason),
    };
  }
  return {
    label: "Waiting",
    className: "source-warn",
    detail: "No snapshot captured yet.",
  };
};

const buildSummaryText = (trafficLabel, incidents, isUnknown) => {
  if (!incidents.length) {
    return isUnknown
      ? "No summary yet."
      : `Traffic appears ${trafficLabel.toLowerCase()} with no active incidents detected.`;
  }

  const types = incidents
    .map((incident) => titleCase(incident?.type || "incident"))
    .filter(Boolean);
  const uniqueTypes = [...new Set(types)];
  const joinedTypes = uniqueTypes.join(", ");
  const stateText = isUnknown ? "unknown traffic conditions" : `${trafficLabel.toLowerCase()} traffic`;
  const incidentWord = incidents.length === 1 ? "incident" : "incidents";
  return `${incidents.length} ${incidentWord} detected under ${stateText}: ${joinedTypes}.`;
};

const updateCard = (node, summary) => {
  const updated = node.querySelector(".updated-at");
  const polledAt = node.querySelector(".polled-at");
  const snapshot = node.querySelector(".snapshot");
  const img = node.querySelector(".snapshot-img");
  const link = node.querySelector(".snapshot-link");
  const snapshotLabel = node.querySelector(".snapshot-label");
  const badge = node.querySelector(".badge");
  const sourceStatus = node.querySelector(".source-status");
  const sourceDetail = node.querySelector(".source-detail");
  const trafficState = node.querySelector(".traffic-state");
  const incidentsCount = node.querySelector(".incidents-count");
  const incidentsList = node.querySelector(".incidents-list");
  const incidentsEmpty = node.querySelector(".incidents-empty");
  const summaryText = node.querySelector(".summary-text");
  const notesText = node.querySelector(".notes-text-body");

  const latest = summary?.latest_log;
  const analysis = summary?.analysis_log || latest;
  const feedStatus = buildFeedStatus(latest);
  if (polledAt) {
    polledAt.textContent = formatTime(latest?.created_at);
  }
  updated.textContent = formatTime(analysis?.created_at);
  if (sourceStatus) {
    sourceStatus.textContent = feedStatus.label;
    sourceStatus.className = `source-status ${feedStatus.className}`;
  }
  if (sourceDetail) {
    sourceDetail.textContent = feedStatus.detail;
  }

  const snapshotUrl = node.dataset.snapshotUrl;
  const framePath = latest?.image_path || analysis?.image_path;
  const frameUrl = frameUrlFromPath(framePath);
  const cacheToken = Date.now();
  const primaryUrl = latest?.error ? null : (snapshotUrl ? withCacheBust(snapshotUrl, cacheToken) : null);
  const fallbackUrl = frameUrl ? withCacheBust(frameUrl, cacheToken) : null;
  const imageUrl = primaryUrl || fallbackUrl;
  if (imageUrl) {
    img.dataset.fallbackSrc = fallbackUrl || "";
    if (img.src !== imageUrl) {
      img.src = imageUrl;
    }
  } else {
    img.dataset.fallbackSrc = "";
    snapshot.classList.remove("is-loaded");
  }
  if (link) {
    const linkUrl = primaryUrl ? snapshotUrl : frameUrl;
    if (linkUrl) {
      link.href = linkUrl;
      link.textContent = primaryUrl ? "Open live snapshot" : "Open stored frame";
    } else {
      link.removeAttribute("href");
      link.textContent = "Snapshot unavailable";
    }
  }
  if (snapshotLabel) {
    snapshotLabel.textContent = primaryUrl ? "Live snapshot" : "Stored fallback";
  }

  const rawTraffic = (analysis?.traffic_state || "").toString().trim().toLowerCase();
  const isUnknown = !rawTraffic || rawTraffic === "unknown";
  const trafficValue = isUnknown ? "pending" : rawTraffic;
  const trafficLabel = isUnknown ? "Awaiting analysis" : titleCase(rawTraffic);
  if (badge) {
    badge.className = `badge ${trafficValue}`;
    badge.textContent = trafficLabel;
  }

  if (trafficState) {
    trafficState.textContent = trafficLabel;
  }

  const incidents = normalizeIncidents(analysis?.incidents || latest?.incidents);
  if (incidentsCount) {
    incidentsCount.textContent = incidents.length.toString();
  }
  if (incidentsList && incidentsEmpty) {
    incidentsList.innerHTML = "";
    if (incidents.length) {
      incidentsEmpty.style.display = "none";
      incidents.forEach((incident) => {
        const item = document.createElement("li");
        const type = titleCase(incident?.type || "incident");
        const severity = incident?.severity ? ` (${incident.severity})` : "";
        const desc = incident?.description ? `: ${incident.description}` : "";
        item.textContent = `${type}${severity}${desc}`;
        incidentsList.appendChild(item);
      });
    } else {
      incidentsEmpty.style.display = "block";
    }
  }

  if (notesText) {
    notesText.textContent = resolveNotes(
      analysis,
      latest,
      "No notes recorded for this frame."
    );
  }

  if (summaryText) {
    if (latest?.error) {
      summaryText.textContent = `Live snapshot unavailable. Showing the last analyzed frame. ${feedStatus.detail}`;
    } else {
      summaryText.textContent = buildSummaryText(trafficLabel, incidents, isUnknown);
    }
  }
};

const loadCameras = async () => {
  const response = await fetch("/cameras");
  return response.json();
};

const loadSummary = async () => {
  const response = await fetch("/status/summary");
  return response.json();
};

const ensureCards = (cameras) => {
  const existing = new Map();
  [...grid.children].forEach((node) => {
    existing.set(node.dataset.cameraId, node);
  });
  cameras.forEach((camera) => {
    const existingCard = existing.get(camera.camera_id);
    if (existingCard) {
      if (camera.snapshot_url) {
        existingCard.dataset.snapshotUrl = camera.snapshot_url;
      }
      return;
    }
    grid.appendChild(buildCard(camera));
  });
};

const refresh = async (source = "auto") => {
  if (refreshing) return;
  refreshing = true;
  try {
    setStatus("Loading", "loading", source === "manual" ? "Manual refresh" : "Auto refresh");
    const [cameras, summary] = await Promise.all([loadCameras(), loadSummary()]);
    ensureCards(cameras);
    summary.forEach((entry) => {
      const node = grid.querySelector(`[data-camera-id="${entry.camera_id}"]`);
      if (node) {
        updateCard(node, entry);
      }
    });
    const now = new Date();
    lastUpdated.textContent = now.toLocaleTimeString();
    if (lastUpdatedFull) {
      lastUpdatedFull.textContent = now.toLocaleString();
    }
    const errorCount = summary.filter((entry) => entry.latest_log?.error).length;
    const skippedCount = summary.filter((entry) => entry.latest_log?.skipped_reason).length;
    const hasData = summary.some((entry) => entry.latest_log?.created_at);
    if (errorCount) {
      setStatus("Issues", "error", `${errorCount} camera errors reported`);
    } else if (hasData) {
      const detail = skippedCount ? `${skippedCount} cameras awaiting analysis` : "Receiving camera data";
      setStatus("Live", "live", detail);
    } else {
      setStatus("Waiting for data", "loading", "No frames analyzed yet");
    }
  } catch (error) {
    lastUpdated.textContent = "error";
    setStatus("Offline", "error", "API unreachable");
  } finally {
    refreshing = false;
  }
};

if (refreshNow) {
  refreshNow.addEventListener("click", () => refresh("manual"));
}

refresh("auto");
setInterval(() => refresh("auto"), REFRESH_SECONDS * 1000);

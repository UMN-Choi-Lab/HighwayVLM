(function () {
  "use strict";

  const cameraFilter = document.getElementById("camera-filter");
  const hoursFilter = document.getElementById("hours-filter");
  const refreshBtn = document.getElementById("refresh-btn");
  const clearBtn = document.getElementById("clear-btn");
  const autoRefreshCb = document.getElementById("auto-refresh");
  const autoRefreshLabel = document.getElementById("auto-refresh-label");
  const DEFAULT_REFRESH_SECONDS = 30;
  let refreshTimer = null;
  let refreshStartTimeout = null;
  let refreshSeconds = DEFAULT_REFRESH_SECONDS;

  // Populate camera list
  fetch("/api/cameras")
    .then((r) => r.json())
    .then((cameras) => {
      cameras.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c.camera_id;
        opt.textContent = c.name || c.camera_id;
        cameraFilter.appendChild(opt);
      });
    })
    .catch(() => {});

  function fetchStats() {
    const camId = cameraFilter.value;
    const hours = hoursFilter.value;
    const params = new URLSearchParams({ hours });
    if (camId) params.set("camera_id", camId);
    return fetch("/api/debug/stats?" + params)
      .then((r) => r.json())
      .then(render)
      .catch((err) => console.error("Debug fetch error:", err));
  }

  function render(data) {
    renderSettings(data.settings || {});
    renderMotion(data);
    renderVLMReasons(data);
    renderHourlyTrend(data.hourly_trend || []);
    renderSourceTypes(data.source_types || {});
    renderErrors(data.error_reasons || {}, data.skip_reasons || {});
    renderTraffic(data.traffic_states || {});
    renderCameraMotion(data.camera_motion || {});
    renderLogs(data.recent_logs || []);
    renderHints(data);
    renderVehicleStats(data.vehicle_stats || {});
    document.getElementById("total-logs").textContent = data.total_logs || 0;
    document.getElementById("anomaly-count").textContent = data.anomaly_count || 0;
  }

  // --- Settings ---
  function renderSettings(settings) {
    const grid = document.getElementById("settings-grid");
    grid.innerHTML = "";
    Object.entries(settings).forEach(([key, val]) => {
      const div = document.createElement("div");
      div.className = "setting-item";
      div.innerHTML =
        '<div class="setting-key">' +
        escHtml(key) +
        '</div><div class="setting-val">' +
        escHtml(String(val)) +
        "</div>";
      grid.appendChild(div);
    });
  }

  // --- Motion ---
  function renderMotion(data) {
    const ms = data.motion_stats || {};
    document.getElementById("motion-avg").textContent = fmt(ms.avg);
    document.getElementById("motion-min").textContent = fmt(ms.min);
    document.getElementById("motion-max").textContent = fmt(ms.max);
    document.getElementById("motion-count").textContent = ms.count || 0;

    const scores = data.motion_scores || [];
    const wrap = document.getElementById("motion-histogram");
    if (!scores.length) {
      wrap.innerHTML = '<p class="no-data">No motion scores in this window.</p>';
      return;
    }

    const settings = data.settings || {};
    const lowTh = settings.MOTION_LOW_THRESHOLD || 0.005;
    const highTh = settings.MOTION_HIGH_THRESHOLD || 0.05;

    // Build histogram buckets
    const maxScore = Math.max(...scores, highTh * 1.5);
    const bucketCount = 30;
    const bucketSize = maxScore / bucketCount;
    const buckets = new Array(bucketCount).fill(0);
    scores.forEach((s) => {
      const idx = Math.min(Math.floor(s / bucketSize), bucketCount - 1);
      buckets[idx]++;
    });
    const maxBucket = Math.max(...buckets, 1);

    let html = '<div class="histogram">';
    buckets.forEach((count, i) => {
      const pct = (count / maxBucket) * 100;
      const mid = (i + 0.5) * bucketSize;
      let cls = "";
      if (mid >= highTh) cls = "above-high";
      else if (mid >= lowTh) cls = "above-low";
      html +=
        '<div class="hist-bar ' +
        cls +
        '" style="height:' +
        Math.max(pct, 2) +
        '%" title="' +
        fmtRange(i * bucketSize, (i + 1) * bucketSize) +
        ": " +
        count +
        '"></div>';
    });
    html += "</div>";
    html +=
      '<div class="hist-labels"><span>0</span><span>' +
      fmt(maxScore) +
      "</span></div>";
    html += '<div class="threshold-markers">';
    html +=
      '<span><span class="dot" style="background:#38d7ff"></span> Below LOW (' +
      lowTh +
      ")</span>";
    html +=
      '<span><span class="dot" style="background:#ff9a3c"></span> LOW-HIGH (' +
      lowTh +
      "-" +
      highTh +
      ")</span>";
    html +=
      '<span><span class="dot" style="background:#ff7e7e"></span> Above HIGH (' +
      highTh +
      ")</span>";
    html += "</div>";
    wrap.innerHTML = html;
  }

  // --- VLM Reasons ---
  function renderVLMReasons(data) {
    renderBarChart("vlm-reasons-chart", data.vlm_reasons || {});
  }

  // --- Hourly Trend ---
  function renderHourlyTrend(trend) {
    const wrap = document.getElementById("hourly-trend-chart");
    if (!trend.length) {
      wrap.innerHTML = '<p class="no-data">No data in this window.</p>';
      return;
    }
    const maxVal = Math.max(...trend.map((t) => t.count), 1);
    let html = '<div class="histogram">';
    trend.forEach((t) => {
      const pct = (t.count / maxVal) * 100;
      const label = t.hour ? t.hour.slice(11) + ":00" : "?";
      html +=
        '<div class="hist-bar" style="height:' +
        Math.max(pct, 2) +
        '%" title="' +
        escHtml(label) +
        ": " +
        t.count +
        '"></div>';
    });
    html += "</div>";
    if (trend.length > 1) {
      const first = trend[0].hour ? trend[0].hour.slice(11) + ":00" : "";
      const last = trend[trend.length - 1].hour
        ? trend[trend.length - 1].hour.slice(11) + ":00"
        : "";
      html +=
        '<div class="hist-labels"><span>' +
        escHtml(first) +
        "</span><span>" +
        escHtml(last) +
        "</span></div>";
    }
    wrap.innerHTML = html;
  }

  // --- Source Types ---
  function renderSourceTypes(data) {
    renderBarChart("source-chart", data);
  }

  // --- Errors ---
  function renderErrors(errors, skips) {
    renderBarChart("error-chart", errors, "danger");
    renderBarChart("skip-chart", skips, "warm");
  }

  // --- Traffic ---
  function renderTraffic(data) {
    renderBarChart("traffic-chart", data, "ok");
  }

  // --- Camera motion ---
  function renderCameraMotion(data) {
    renderBarChart("camera-motion-chart", data);
  }

  // --- Logs table ---
  function renderLogs(logs) {
    const tbody = document.getElementById("logs-tbody");
    if (!logs.length) {
      tbody.innerHTML =
        '<tr><td colspan="9" class="no-data">No logs in this window.</td></tr>';
      return;
    }
    tbody.innerHTML = logs
      .map(
        (l) =>
          "<tr>" +
          "<td>" +
          escHtml(shortTime(l.created_at)) +
          "</td>" +
          "<td>" +
          escHtml(l.camera_name || l.camera_id || "--") +
          "</td>" +
          "<td>" +
          escHtml(l.traffic_state || "--") +
          "</td>" +
          "<td>" +
          (l.vehicle_count != null ? l.vehicle_count : "--") +
          "</td>" +
          "<td>" +
          fmt(l.motion_score) +
          "</td>" +
          "<td>" +
          (l.anomaly_detected ? escHtml(l.anomaly_reason || "yes") : "--") +
          "</td>" +
          "<td>" +
          escHtml(l.vlm_call_reason || "--") +
          "</td>" +
          "<td>" +
          escHtml(l.source_type || "--") +
          "</td>" +
          "<td>" +
          (l.error
            ? '<span class="cell-error">' + escHtml(l.error) + "</span>"
            : l.skipped_reason
              ? '<span class="cell-skip">' + escHtml(l.skipped_reason) + "</span>"
              : "--") +
          "</td>" +
          "</tr>",
      )
      .join("");
  }

  // --- Vehicle Stats ---
  function renderVehicleStats(vs) {
    const el = document.getElementById("vehicle-stats");
    if (!el) return;
    document.getElementById("vehicle-avg").textContent =
      vs.avg != null ? Number(vs.avg).toFixed(1) : "--";
    document.getElementById("vehicle-min").textContent =
      vs.min != null ? vs.min : "--";
    document.getElementById("vehicle-max").textContent =
      vs.max != null ? vs.max : "--";
    document.getElementById("vehicle-samples").textContent = vs.count || 0;
  }

  // --- Hints ---
  function renderHints(data) {
    const el = document.getElementById("hints-list");
    const hints = [];
    const ms = data.motion_stats || {};
    const settings = data.settings || {};
    const reasons = data.vlm_reasons || {};
    const sources = data.source_types || {};

    if (
      ms.count > 0 &&
      ms.max !== null &&
      ms.max < (settings.MOTION_LOW_THRESHOLD || 0.005)
    ) {
      hints.push({
        cls: "warning",
        text:
          "All motion scores are below LOW_THRESHOLD (" +
          (settings.MOTION_LOW_THRESHOLD || 0.005) +
          "). Consider lowering MOTION_LOW_THRESHOLD or MOTION_DIFF_THRESHOLD.",
      });
    }

    const totalReasons = Object.values(reasons).reduce((a, b) => a + b, 0);
    if (
      totalReasons > 0 &&
      !reasons["anomaly"] &&
      !reasons["anomaly_detected"]
    ) {
      hints.push({
        cls: "warning",
        text: "No anomaly-triggered VLM calls. Only periodic triggers detected. Consider lowering motion thresholds.",
      });
    }

    if (data.anomaly_count > totalReasons * 0.7 && totalReasons > 5) {
      hints.push({
        cls: "warning",
        text: "Over 70% of VLM calls are anomaly-triggered. Consider raising MOTION_DIFF_THRESHOLD to reduce call volume.",
      });
    }

    const snapshotCount = sources["snapshot"] || sources["snapshot_fallback"] || 0;
    const hlsCount = sources["hls"] || 0;
    if (snapshotCount > 0 && hlsCount > 0 && snapshotCount > hlsCount) {
      hints.push({
        cls: "warning",
        text:
          "High snapshot fallback rate (" +
          snapshotCount +
          " snapshot vs " +
          hlsCount +
          " HLS). Check HLS_TIMEOUT_SECONDS and HLS_MAX_CONSECUTIVE_FAILURES.",
      });
    }

    if (!hints.length) {
      hints.push({
        cls: "ok",
        text: "No obvious tuning issues detected in this time window.",
      });
    }

    el.innerHTML = hints
      .map((h) => '<div class="hint ' + h.cls + '">' + escHtml(h.text) + "</div>")
      .join("");
  }

  // --- Generic bar chart ---
  function renderBarChart(id, data, fillCls) {
    const wrap = document.getElementById(id);
    const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
    if (!entries.length) {
      wrap.innerHTML = '<p class="no-data">No data in this window.</p>';
      return;
    }
    const maxVal = Math.max(...entries.map((e) => e[1]), 1);
    wrap.innerHTML = entries
      .map(
        (e) =>
          '<div class="bar-row">' +
          '<span class="bar-label" title="' +
          escHtml(e[0]) +
          '">' +
          escHtml(e[0]) +
          "</span>" +
          '<div class="bar-track"><div class="bar-fill' +
          (fillCls ? " " + fillCls : "") +
          '" style="width:' +
          (e[1] / maxVal) * 100 +
          '%"></div></div>' +
          '<span class="bar-value">' +
          e[1] +
          "</span>" +
          "</div>",
      )
      .join("");
  }

  // --- Utils ---
  function escHtml(s) {
    if (s == null) return "--";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmt(v) {
    if (v == null) return "--";
    return typeof v === "number" ? v.toFixed(6) : String(v);
  }

  function fmtRange(a, b) {
    return fmt(a) + " - " + fmt(b);
  }

  function shortTime(iso) {
    if (!iso) return "--";
    return iso.replace("T", " ").slice(0, 19);
  }

  // --- Refresh logic ---
  function scheduleRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
    if (refreshStartTimeout) {
      clearTimeout(refreshStartTimeout);
      refreshStartTimeout = null;
    }

    if (!autoRefreshCb.checked) {
      return;
    }

    // Align refreshes to wall-clock cadence boundaries so all pages refresh together.
    const intervalMs = refreshSeconds * 1000;
    const now = Date.now();
    let delayMs = intervalMs - (now % intervalMs);
    if (delayMs >= intervalMs) {
      delayMs = 0;
    }

    refreshStartTimeout = setTimeout(() => {
      fetchStats();
      refreshTimer = setInterval(fetchStats, intervalMs);
    }, delayMs);
  }

  function updateRefreshLabel() {
    if (!autoRefreshLabel) return;
    autoRefreshLabel.textContent = `Auto-refresh (${refreshSeconds}s)`;
  }

  async function loadRuntimeRefreshSeconds() {
    if (!window.HighwayVLMRuntime || typeof window.HighwayVLMRuntime.load !== "function") {
      return DEFAULT_REFRESH_SECONDS;
    }
    const settings = await window.HighwayVLMRuntime.load();
    const candidate = Number.parseInt(settings?.SYSTEM_INTERVAL_SECONDS, 10);
    return Number.isFinite(candidate) && candidate > 0 ? candidate : DEFAULT_REFRESH_SECONDS;
  }

  refreshBtn.addEventListener("click", fetchStats);
  clearBtn.addEventListener("click", () => {
    const camId = cameraFilter.value;
    const label = camId ? "logs for this camera" : "ALL pipeline logs";
    if (!confirm("Delete " + label + "? This cannot be undone.")) return;
    const params = new URLSearchParams();
    if (camId) params.set("camera_id", camId);
    fetch("/api/debug/clear?" + params, { method: "POST" })
      .then((r) => r.json())
      .then((data) => {
        alert("Deleted " + (data.deleted || 0) + " log entries.");
        fetchStats();
      })
      .catch((err) => alert("Clear failed: " + err));
  });
  cameraFilter.addEventListener("change", fetchStats);
  hoursFilter.addEventListener("change", fetchStats);
  autoRefreshCb.addEventListener("change", scheduleRefresh);

  async function init() {
    refreshSeconds = await loadRuntimeRefreshSeconds();
    updateRefreshLabel();
    fetchStats();
    scheduleRefresh();
  }

  init();
})();

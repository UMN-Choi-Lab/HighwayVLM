(function () {
  "use strict";

  const DEFAULTS = Object.freeze({
    SYSTEM_INTERVAL_SECONDS: 30,
  });

  const toPositiveInt = (value, fallback) => {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
  };

  const normalize = (settings) => ({
    ...DEFAULTS,
    ...(settings || {}),
    SYSTEM_INTERVAL_SECONDS: toPositiveInt(
      settings?.SYSTEM_INTERVAL_SECONDS,
      DEFAULTS.SYSTEM_INTERVAL_SECONDS
    ),
  });

  const load = async () => {
    try {
      // Frontend pages read cadence from one API source so refresh timing stays in sync with backend ticks.
      const response = await fetch("/api/runtime/settings");
      if (!response.ok) {
        return { ...DEFAULTS };
      }
      const payload = await response.json();
      return normalize(payload);
    } catch (_error) {
      return { ...DEFAULTS };
    }
  };

  window.HighwayVLMRuntime = {
    defaults: DEFAULTS,
    load,
  };
})();

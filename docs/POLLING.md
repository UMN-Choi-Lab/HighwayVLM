# Polling And Refresh Cadence

This document is the single reference for how polling/refresh timing works in HighwayVLM.

## Single Source Of Truth

- `SYSTEM_INTERVAL_SECONDS` is the only cadence setting that controls:
  - backend camera scan ticks
  - frontend page auto-refresh cadence
- Default value is `30`.
- Source code owner:
  - `highwayvlm/settings.py` -> `get_system_interval_seconds()`

Legacy helper functions still exist in `settings.py` for compatibility, but they all return the same `SYSTEM_INTERVAL_SECONDS` value.

## Backend Tick Model

Code path:

- `highwayvlm/pipeline.py` -> `run_loop()` -> `run_once()`

Behavior:

1. The worker aligns startup to the next wall-clock cadence boundary.
2. Every tick starts a full sweep for all configured cameras.
3. The sweep is concurrent:
   - one task per camera in a thread pool
   - cameras are processed in parallel in the same tick window
4. After each sweep, the next scheduled tick is advanced by exactly one interval.
5. If work overruns, the scheduler catches up to the next valid cadence boundary.

This means the worker uses fixed scheduled ticks, not `sleep(interval)` after work completes.

## Per-Camera Decision Flow (Each Tick)

Within each camera task (`_process_camera`):

1. Try HLS branch if enabled.
2. If HLS is unavailable/unhandled, use snapshot fallback.
3. Run local CV-first checks (motion + vehicle/stopped-vehicle signals).
4. Escalate to VLM only when CV gating says it is needed, or when pending confirmation requires another check.
5. If VLM runs, use comparison analysis (`analyze_comparison`) and confirmation filtering.
6. Persist log/incident/archive outputs.

Important skip reasons you will commonly see:

- `unchanged_frame`
- `cv_baseline_needed`
- `local_motion_normal`
- `vlm_error_cooldown`
- `vlm_quota_exceeded`
- `empty_snapshot`

## Frontend Auto-Refresh Model

Code path:

- `web/static/runtime-settings.js`
- `web/static/dashboard.js`
- `web/static/debug.js`
- `web/static/incidents.js`
- `web/static/hourly.js`
- `web/static/overnight.js`

Behavior:

1. Pages load runtime settings from `GET /api/runtime/settings`.
2. Each page reads `SYSTEM_INTERVAL_SECONDS`.
3. Auto-refresh timers are aligned to cadence boundaries using the same modulo strategy as backend ticks.

## Dashboard "Live" vs "Scan" Behavior

- Dashboard cards can display live HLS playback continuously between ticks.
- CV/VLM analysis and persistence still occur on the shared scan cadence (`SYSTEM_INTERVAL_SECONDS`).
- So the UI can look live while formal analysis stays on the 30-second schedule.

## How To Change Cadence

Change only one value:

- `SYSTEM_INTERVAL_SECONDS` in environment/runtime config

Do not set separate page refresh intervals or separate scan intervals; all timing fans out from this one setting.

## Verification Checklist

1. Confirm runtime value:
   - `GET /api/runtime/settings`
2. Confirm backend and frontend agree:
   - dashboard/debug/archive pages show refresh at the same interval
3. Confirm concurrent sweep behavior:
   - logs within a tick should show multiple cameras processed in the same cadence window

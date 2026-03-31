# CV-First VLM Incident Pipeline (Current)

This document describes the active per-camera decision path in `highwayvlm/pipeline.py`.

## Core Principle

HighwayVLM is CV-first:

1. Collect frame data.
2. Run local CV checks.
3. Escalate to VLM only when local signals require it.
4. Confirm incidents before archiving/reporting.

## Per-Tick Processing Model

- Cadence is controlled by `SYSTEM_INTERVAL_SECONDS`.
- Each tick processes all cameras concurrently.
- Each camera follows the same CV-first flow below.

See `docs/POLLING.md` for full tick/refresh scheduling details.

## Camera Flow

1. Start with HLS branch when enabled.
2. If HLS branch is unavailable/unhandled, run snapshot fallback.
3. Save current frame and update hash/state metadata.
4. If frame hash is unchanged:
   - log skip with `skipped_reason="unchanged_frame"`
5. Run local CV features:
   - motion analysis
   - vehicle detection
   - stopped-vehicle comparison checks
6. Decide if VLM is needed:
   - use CV gating (`should_call_vlm(...)`)
   - force VLM if a pending incident needs confirmation
7. If VLM is not needed:
   - log local result with `vlm_model="local_cv"` or `local_motion`
8. If VLM is needed:
   - call `analyze_comparison(...)` with two-frame context
9. Apply confirmation and filtering:
   - low-confidence suppression
   - pending incident multi-cycle confirmation
   - false-alarm style filtering
10. Persist logs and derived artifacts:
   - `vlm_logs`
   - `incident_events` (when confirmed)
   - `hourly_snapshots` + `hourly_incident_reports`
   - annotated image and clip where applicable

## Common Skip Reasons

- `unchanged_frame`
- `cv_baseline_needed`
- `local_motion_normal`
- `vlm_error_cooldown`
- `vlm_quota_exceeded`
- `empty_snapshot`

## Data Written Per Camera

- Every processed cycle still writes a log row (including skips/errors).
- Incident rows are only written for confirmed incidents.
- Hourly archive rows are maintained through storage-derived writes.

## Operational Notes

- Dashboard can show live HLS playback between ticks, but analysis remains cadence-driven.
- The first usable snapshot cycle may log `cv_baseline_needed` until prior-frame context exists.
- Runtime setting snapshots are available at:
  - `GET /api/runtime/settings`
  - `GET /api/debug/stats` -> `settings`

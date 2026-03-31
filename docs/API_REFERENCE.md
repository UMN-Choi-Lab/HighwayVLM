# API Reference

## FastAPI Docs

- `/docs`
- `/redoc`
- `/openapi.json`

## HTML Routes

- `GET /`
  - Returns `web/dashboard.html`
- `GET /incidents`
  - Returns `web/incidents.html`
- `GET /hourly`
  - Returns `web/hourly.html`
- `GET /overnight`
  - Returns `web/overnight.html`
- `GET /debug`
  - Returns `web/debug.html`

Redirect helpers:

- `GET /camera/{camera_id}/incidents` -> `/incidents?camera_id=...`
- `GET /camera/{camera_id}/hourly` -> `/hourly?camera_id=...`
- `GET /camera/{camera_id}/overnight` -> `/overnight?camera_id=...`

## Health

- `GET /health`
- `GET /api/health`

Both return:

```json
{"status":"ok"}
```

## Camera Catalog

- `GET /cameras`
- `GET /api/cameras`

Returns loaded camera entries from `config/cameras.yaml`.

## Runtime Settings

- `GET /api/runtime/settings`

Returns runtime tuning values used by backend and frontend.  
Most important key for cadence:

- `SYSTEM_INTERVAL_SECONDS`

See `docs/POLLING.md` for timing behavior.

## Debug Routes

- `GET /api/debug/stats`
  - Query params:
    - `camera_id` optional
    - `hours` optional, `1..168`, default `1`
  - Returns aggregate debug metrics plus `settings` snapshot.

- `POST /api/debug/clear`
  - Query params:
    - `camera_id` optional
  - Clears rows from `vlm_logs` (all or one camera).

## Log Routes

- `GET /logs/latest`
- `GET /api/logs/latest`
  - Query params:
    - `camera_id` optional
  - Returns newest log row or `{}`.

- `GET /logs`
- `GET /api/logs`
  - Query params:
    - `camera_id` optional
    - `limit` optional, default `50`, min `1`, max `500`

## Dashboard Summary

- `GET /status/summary`

Returns one object per configured camera with:

- `latest_log`: most recent row of any kind
- `analysis_log`: most recent row with populated analysis result

## Incident Routes

- `GET /api/incidents`
  - Query params:
    - `camera_id` optional
    - `limit` optional, default `200`, min `1`, max `2000`
    - `include_false_alarms` optional, default `false`

- `POST /api/incidents/clear`
  - Query params:
    - `camera_id` optional

- `POST /api/incidents/clear_false_alarms`
  - Query params:
    - `camera_id` optional

- `POST /api/incidents/{incident_id}/false_alarm`
  - Toggles false-alarm state for one incident row.
  - Returns `404` if incident does not exist.

## Hourly Routes

- `GET /api/hourly`
  - Query params:
    - `camera_id` optional
    - `limit` optional, default `336`, min `1`, max `2000`
  - Returns hourly snapshot rows with `incident_reports`.

- `POST /api/hourly/clear`
  - Query params:
    - `camera_id` optional

## Archive Overview

- `GET /api/archive/overview`
  - Query params:
    - `camera_id` optional
    - `include_false_alarms` optional, default `false`
  - Returns aggregate totals and latest timestamps for incidents/hourly archive.

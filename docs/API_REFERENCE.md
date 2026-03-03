# API Reference

## FastAPI Docs

The application currently exposes FastAPI's built-in documentation endpoints:

- `/docs`
- `/redoc`
- `/openapi.json`

## HTML Routes

### `GET /`

- Returns `web/dashboard.html`

### `GET /incidents`

- Returns `web/incidents.html`

### `GET /hourly`

- Returns `web/hourly.html`

### `GET /overnight`

- Returns `web/overnight.html`
- The page loads `web/static/overnight.js`, which builds a camera-grouped overnight review from `/api/hourly`

### `GET /camera/{camera_id}/incidents`

- Redirects to `/incidents?camera_id=<camera_id>`

### `GET /camera/{camera_id}/hourly`

- Redirects to `/hourly?camera_id=<camera_id>`

### `GET /camera/{camera_id}/overnight`

- Redirects to `/overnight?camera_id=<camera_id>`

## Health Routes

### `GET /health`

Response:

```json
{"status":"ok"}
```

### `GET /api/health`

Response:

```json
{"status":"ok"}
```

## Camera Routes

### `GET /cameras`

- Returns the loaded camera config array

### `GET /api/cameras`

- Same payload as `/cameras`

Camera object shape:

```json
{
  "camera_id": "C30248",
  "name": "I-94: Hudson Rd WB @ 4th St",
  "snapshot_url": "https://...",
  "source_url": "",
  "corridor": "I-94",
  "direction": "WB",
  "poll_interval_sec": 30
}
```

## Log Routes

### `GET /logs/latest`

Query params:

- `camera_id` optional

Returns the newest `vlm_logs` row converted into JSON, or `{}` if no log exists.

### `GET /api/logs/latest`

- Same payload as `/logs/latest`

### `GET /logs`

Query params:

- `camera_id` optional
- `limit` integer, default `50`, min `1`, max `500`

Returns recent `vlm_logs` rows.

### `GET /api/logs`

- Same payload as `/logs`

Log object fields include:

- `id`
- `created_at`
- `captured_at`
- `camera_id`
- `camera_name`
- `corridor`
- `direction`
- `observed_direction`
- `traffic_state`
- `incidents`
- `notes`
- `overall_confidence`
- `image_path`
- `vlm_model`
- `raw_response`
- `error`
- `skipped_reason`
- `frame_hash`
- `last_seen_at`
- `last_processed_at`

## Summary Route

### `GET /status/summary`

Returns one object per configured camera:

```json
{
  "camera_id": "C30248",
  "name": "I-94: Hudson Rd WB @ 4th St",
  "corridor": "I-94",
  "direction": "WB",
  "latest_log": {},
  "analysis_log": {}
}
```

Notes:

- `latest_log` is the most recent row of any kind
- `analysis_log` is the most recent row where `traffic_state` is not null

## Incident Archive Route

### `GET /api/incidents`

Query params:

- `camera_id` optional
- `limit` integer, default `200`, min `1`, max `2000`

Returns rows from `incident_events`.

Incident row fields include:

- `id`
- `created_at`
- `captured_at`
- `camera_id`
- `camera_name`
- `corridor`
- `direction`
- `observed_direction`
- `traffic_state`
- `incident_type`
- `severity`
- `description`
- `notes`
- `overall_confidence`
- `image_path`
- `vlm_model`

## Hourly Archive Route

### `GET /api/hourly`

Query params:

- `camera_id` optional
- `limit` integer, default `336`, min `1`, max `2000`

Returns rows from `hourly_snapshots` with attached `incident_reports`.

Hourly row fields include:

- `id`
- `camera_id`
- `camera_name`
- `corridor`
- `direction`
- `hour_bucket`
- `created_at`
- `captured_at`
- `image_path`
- `frame_hash`
- `traffic_state`
- `incident_count`
- `status`
- `summary`
- `error`
- `skipped_reason`
- `incident_reports`

Each `incident_reports` element may contain:

- `report_kind`
- `incident_type`
- `severity`
- `description`
- `notes`
- `overall_confidence`
- `created_at`
- `captured_at`
- `image_path`
- `traffic_state`

## Archive Overview Route

### `GET /api/archive/overview`

Query params:

- `camera_id` optional

Response shape:

```json
{
  "camera_id": "C30248",
  "incident_total": 3,
  "hourly_total": 55,
  "latest_incident_at": "2026-02-18T02:21:09.557122+00:00",
  "latest_hour_bucket": "2026-02-18T15:00:00Z"
}
```

# App Reference

## Overview

HighwayVLM watches freeway traffic cameras, fetches snapshots, runs a vision-language model over selected frames, stores structured incident data, and serves an operator-facing dashboard plus archive pages.

This document describes the current implementation, not the intended future design.

## End-To-End Flow

1. FastAPI starts from `main.py`.
2. Startup initializes the database and syncs the camera catalog.
3. A daemon thread begins the live polling loop.
4. The live loop fetches snapshots for all configured cameras each tick.
5. Every fetched frame is written to disk.
6. A frame hash determines whether the frame changed.
7. Local CV gating decides whether VLM escalation is needed for that frame.
8. If gated in, the app calls the OpenAI-compatible API with comparison context.
9. The model response is normalized into a strict schema.
10. The log entry is written to SQLite.
11. Incident and hourly archive rows are derived from that same log write.
12. The frontend queries summary and archive endpoints to display current state.

## Folder-By-Folder Reference

### `config/`

- Holds the camera catalog.
- The active file is `config/cameras.yaml`.
- Each camera entry may define:
  - `camera_id`
  - `name`
  - `snapshot_url`
  - `source_url`
  - `corridor`
  - `direction`

### `highwayvlm/`

- Main package.
- Important files:
  - `api.py`
  - `settings.py`
  - `config_loader.py`
  - `pipeline.py`
  - `storage.py`
  - `ingest/fetcher.py`
  - `ingest/snapshot.py`
  - `vlm/client.py`
  - `vlm/run_vlm.py`

### `web/`

- Contains static HTML pages.
- JavaScript fetches JSON from FastAPI routes.
- CSS is plain static stylesheet code.

### `scripts/`

- Very thin wrappers that insert the repo root into `sys.path` and call package entrypoints.

### `infra/`

- `docker/` for deployment files
- `monitoring/` for local CLI inspection of the archive

### `data/`

- Generated runtime state.
- Not intended for hand-editing.

### `logs/`

- Generated append-only JSONL incident output.

## Startup And Runtime

## `main.py`

- Imports `app` from `highwayvlm.api`.
- No extra logic is added here.

## `highwayvlm/api.py`

At import time:

- creates the FastAPI app
- resolves the `web/` and `web/static/` directories
- ensures `data/frames` exists
- mounts:
  - `/frames`
  - `/static`

On startup:

- `init_db()` ensures SQLite tables and indexes exist
- `load_cameras()` reads `config/cameras.yaml`
- `sync_cameras()` updates the `cameras` table
- a daemon thread starts `pipeline.run_loop()`

## API Routes

### HTML routes

- `/`
  - dashboard page
- `/incidents`
  - incident archive page
- `/hourly`
  - hourly archive page
- `/overnight`
  - overnight page shell
- `/debug`
  - debug/tuning page shell

### Redirect helper routes

- `/camera/{camera_id}/incidents`
- `/camera/{camera_id}/hourly`
- `/camera/{camera_id}/overnight`

These convert path-based navigation into query-parameter page URLs.

### Health routes

- `/health`
- `/api/health`

Both return `{"status": "ok"}`.

### Camera routes

- `/cameras`
- `/api/cameras`

Both return the loaded camera config entries directly.

### Log routes

- `/logs/latest`
- `/api/logs/latest`
- `/logs`
- `/api/logs`

These read from `vlm_logs`.

### Summary and archive routes

- `/status/summary`
  - dashboard summary grouped by camera
- `/api/runtime/settings`
  - shared runtime settings payload for backend/frontend cadence
- `/api/debug/stats`
  - debug aggregates plus runtime settings snapshot
- `/api/debug/clear`
  - clears rows from `vlm_logs`
- `/api/incidents`
  - incident rows from `incident_events`
- `/api/incidents/clear`
  - clears incident rows
- `/api/incidents/clear_false_alarms`
  - clears rows marked false alarm
- `/api/incidents/{incident_id}/false_alarm`
  - toggles false alarm flag for one incident
- `/api/hourly`
  - hourly snapshot rows plus attached hourly incident reports
- `/api/hourly/clear`
  - clears hourly archive rows
- `/api/archive/overview`
  - total counts and latest timestamps

## OpenAPI

Because FastAPI defaults are not overridden, the app currently exposes:

- `/docs`
- `/redoc`
- `/openapi.json`

This is the current machine-readable route contract for the running app.

## Live Polling Pipeline

The live worker lives in `highwayvlm/pipeline.py`.

## Per-Camera State

Each camera gets an in-memory `CameraState` object containing:

- `last_seen_hash`
- `last_seen_at`
- `last_processed_hash`
- `last_processed_at`
- `last_image_path`
- `last_polled_at`
- `last_error_at`

This state is not persisted across restarts.

## Poll Decision

Polling cadence is centralized in one setting:

- `SYSTEM_INTERVAL_SECONDS`

Tick behavior:

- first sweep waits until the next cadence boundary
- each tick submits all cameras concurrently in a thread pool
- each camera runs CV-first gating, and only escalates to VLM when warranted
- the worker keeps a fixed tick schedule instead of `work_duration + sleep`

See `docs/POLLING.md` for full cadence and concurrency details.

## Snapshot Fetch

`fetch_snapshot_bytes(camera)` supports several source patterns:

- direct image URL
- JSON endpoint that contains an image URL somewhere inside the payload
- HTML viewer page where an image URL can be extracted
- template-generated metadata endpoint
- public camera API endpoint discovery based on the camera source origin

## Saved Frame Layout

Fetched images are saved by `save_snapshot()` as:

`data/frames/live/<camera_id>/<YYYYMMDD>/<camera_id>_<timestamp>.<ext>`

The value written into `image_path` is relative to `data/frames`.

## Deduplication

Each snapshot is hashed with SHA-256.

If the hash matches `last_processed_hash`, the frame is still logged, but the VLM is skipped with:

- `skipped_reason = "unchanged_frame"`

## Additional Skip Conditions

The worker can also skip VLM analysis for:

- `empty_snapshot`
- `vlm_error_cooldown`
- `vlm_quota_exceeded`

Errors are recorded separately in the `error` field.

## OpenAI / Vision Model Call

The current implementation is in `highwayvlm/vlm/client.py`.

## Configuration

The VLM client reads:

- `OPENAI_API_KEY` or `VLM_API_KEY`
- `OPENAI_BASE_URL` or `VLM_BASE_URL`
- `VLM_MODEL`
- `VLM_TIMEOUT_SECONDS`
- `VLM_MAX_RETRIES`
- `VLM_MAX_TOKENS`

Default base URL:

- `https://api.openai.com/v1`

Default model:

- `gpt-4o-mini`

## Prompt Structure

The prompt has two parts:

### System prompt

The system prompt instructs the model to:

- act as a freeway incident detection system
- prefer false positives over missed incidents
- classify traffic state
- detect a specific incident taxonomy
- produce JSON only
- include detailed incident descriptions with spatial context

Incident types explicitly named by the prompt:

- `crash`
- `stopped_vehicle_lane`
- `stopped_vehicle_shoulder`
- `stalled_vehicle`
- `debris`
- `emergency_response`
- `pedestrian`
- `traffic_anomaly`

Traffic states explicitly allowed:

- `free`
- `moderate`
- `heavy`
- `stop_and_go`
- `unknown`

Severity values explicitly allowed:

- `low`
- `medium`
- `high`

### User prompt

The user prompt adds:

- camera name
- corridor and direction
- camera ID
- timestamp
- reminders about what to inspect in the image

## Request Format

The client sends:

- one system text message
- one user content array containing:
  - a text item
  - an `image_url` item whose URL is a base64 data URL

Endpoint used:

- `POST {base_url}/chat/completions`

## Response Parsing

The client tries to extract text from:

- `choices[0].message.content`
- `output_text`

It then:

1. tries to parse the whole text as JSON
2. falls back to searching for the first valid JSON object substring
3. normalizes loose output formats
4. validates the final shape with Pydantic

## Normalization Rules

The client tolerates imperfect model output by:

- wrapping a bare incident object into an `incidents` array
- coercing non-list `incidents` into a list
- defaulting missing incident `type` to `incident`
- mapping severity aliases such as `minor`, `moderate`, `critical`
- normalizing traffic labels to snake_case lowercase
- defaulting missing values

If the final `traffic_state` is `unknown`, it is rewritten to:

- `moderate` if incidents exist
- `free` if no incidents exist

If notes are blank or too generic, the client synthesizes them.

## Storage Model

All persistent behavior flows through `highwayvlm/storage.py`.

## Tables

### `cameras`

Stores the current synced camera catalog.

### `vlm_logs`

Stores one row for every pipeline pass that chooses to insert a log, including:

- successful analyses
- skipped frames
- snapshot failures
- VLM failures

Important columns:

- `created_at`
- `captured_at`
- `camera_id`
- `traffic_state`
- `incidents_json`
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

### `incident_events`

One row per incident item extracted from a successful log entry.

### `hourly_snapshots`

At most one row per `(camera_id, hour_bucket)`.

This acts as an archive/heartbeat table that summarizes camera coverage and incident state for that hour.

### `hourly_incident_reports`

Stores one-or-more descriptive rows attached to each hourly snapshot bucket.

If no incidents exist, the code still inserts a `no_incident` report row.

## Derived Writes

Every `insert_log(log_entry)` call does three things after writing `vlm_logs`:

1. append incident JSONL if incidents exist
2. insert `incident_events` rows if incidents exist
3. attempt to archive the frame into `hourly_snapshots`

## Hourly Status Logic

Hourly status is derived as:

- `error` if `error` exists
- `incident` if incidents exist
- `skipped` if `skipped_reason` exists
- `healthy` if `traffic_state` exists
- `unknown` otherwise

## Frontend Behavior

## Dashboard

Files:

- `web/dashboard.html`
- `web/static/dashboard.js`
- `web/static/dashboard.css`

Requests:

- `/cameras`
- `/status/summary`

Refresh interval:

- loaded from `/api/runtime/settings` using `SYSTEM_INTERVAL_SECONDS`

The dashboard prefers the configured `snapshot_url` for preview images and uses stored frame paths as fallback.

## Incident Archive

Files:

- `web/incidents.html`
- `web/static/incidents.js`
- `web/static/archive.css`

Requests:

- `/cameras`
- `/api/archive/overview`
- `/api/incidents`

## Hourly Archive

Files:

- `web/hourly.html`
- `web/static/hourly.js`
- `web/static/archive.css`

Requests:

- `/cameras`
- `/api/archive/overview`
- `/api/hourly`

## Overnight Page

Files:

- `web/overnight.html`
- `web/static/overnight.js`

Current status:

- route exists
- page shell exists
- client script loads hourly archive data and filters it to the selected overnight window
- rows are grouped by camera for a morning review view

## Settings And Environment

Settings accessors are centralized in `highwayvlm/settings.py`.

Important groups:

- filesystem paths
- timing values
- VLM configuration
- snapshot discovery helpers

Some defined paths are not actively used by the live worker:

- `HOURLY_FRAMES_DIR`
- `INCIDENT_REPORTS_DIR`

## One-Off Scripts

## Snapshot Runner

`scripts/snapshot.py` -> `highwayvlm.ingest.snapshot.main`

Purpose:

- ingest-only testing or manual snapshot capture

## Standalone VLM Runner

`scripts/run_vlm.py` -> `highwayvlm.vlm.run_vlm.main`

Purpose:

- intended VLM-only testing over latest snapshots

Current behavior:

- snapshot lookup now searches the nested active ingest path recursively under `data/frames/`
- the live background worker is still the main production path

## Deployment

Docker files live in `infra/docker/`.

Current container behavior:

- installs dependencies from `requirements.txt`
- copies the repo into `/app`
- creates runtime directories
- starts `uvicorn main:app`
- exposes port `8000`

Compose mounts:

- host `.../highwayvlm/data` -> `/app/data`
- host `.../highwayvlm/logs` -> `/app/logs`

## Monitoring CLI

`infra/monitoring/monitor.py` can print:

- archive summary
- hourly rows
- incident rows
- watch loop

It reads directly from the same storage helpers used by the API.

## Current Known Issues And Mismatches

- The settings module includes some reserved output directories not used by the active live worker.

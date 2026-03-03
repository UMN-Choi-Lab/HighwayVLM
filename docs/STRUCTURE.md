# Structure Guide

## Top Level

- `main.py`
  - Thin import-only entrypoint for `uvicorn main:app`.
- `config/`
  - Camera configuration files.
- `highwayvlm/`
  - Active backend package.
- `web/`
  - Static frontend pages and assets.
- `scripts/`
  - Thin wrappers around package entrypoints.
- `infra/`
  - Deployment and monitoring utilities.
- `docs/`
  - Human-maintained reference material.
- `data/`
  - Generated runtime state.
- `logs/`
  - Generated append-only logs.

## Backend Package

### `highwayvlm/api.py`

- Defines the FastAPI app.
- Mounts static files.
- Serves page routes and JSON routes.
- Starts the background worker thread on app startup.

### `highwayvlm/settings.py`

- Centralizes filesystem paths and environment-variable accessors.
- Defines current runtime directories such as:
  - `data/frames`
  - `data/raw_vlm_outputs`
  - `logs/incidents.jsonl`
- Also defines `HOURLY_FRAMES_DIR` and `INCIDENT_REPORTS_DIR`, which are currently not written by the active live pipeline.

### `highwayvlm/config_loader.py`

- Reads YAML camera definitions.
- Normalizes each camera record to:
  - `camera_id`
  - `name`
  - `snapshot_url`
  - `source_url`
  - `corridor`
  - `direction`
  - `poll_interval_sec`

### `highwayvlm/pipeline.py`

- Main live worker loop.
- Keeps in-memory per-camera state.
- Saves every fetched frame.
- Applies:
  - poll interval gating
  - unchanged-frame skipping
  - minimum VLM interval
  - post-error cooldown
  - maximum VLM calls per run

### `highwayvlm/storage.py`

- Owns SQLite schema creation and lightweight migration logic.
- Stores logs and archive data.
- Provides read helpers used by:
  - the API
  - the monitoring CLI

### `highwayvlm/ingest/fetcher.py`

- Handles snapshot retrieval from external camera sources.
- Supports:
  - direct image URLs
  - JSON metadata payloads
  - HTML viewer pages
  - regex-based extraction
  - metadata-template fallback discovery

### `highwayvlm/ingest/snapshot.py`

- Standalone snapshot fetch runner.
- Useful for ingest-only testing.

### `highwayvlm/vlm/client.py`

- Contains:
  - prompt construction
  - response extraction
  - JSON parsing
  - normalization
  - validation
  - retry handling

### `highwayvlm/vlm/run_vlm.py`

- Standalone VLM runner intended to analyze latest saved snapshots.
- Searches the nested live snapshot layout recursively under `data/frames/`.

## Frontend

### `web/dashboard.html`

- Main live dashboard page.
- Uses `web/static/dashboard.js`.

### `web/incidents.html`

- Incident archive page.
- Uses `web/static/incidents.js`.

### `web/hourly.html`

- Hourly archive page.
- Uses `web/static/hourly.js`.

### `web/overnight.html`

- Intended overnight review page.
- Uses `web/static/overnight.js`.

### `web/static/overnight.js`

- Fetches:
  - `/cameras`
  - `/api/hourly`
- Filters rows to the selected time window and groups them by camera for morning review.

### `web/static/dashboard.js`

- Fetches:
  - `/cameras`
  - `/status/summary`
- Renders per-camera cards and refreshes every 30 seconds.

### `web/static/incidents.js`

- Fetches:
  - `/cameras`
  - `/api/archive/overview`
  - `/api/incidents`

### `web/static/hourly.js`

- Fetches:
  - `/cameras`
  - `/api/archive/overview`
  - `/api/hourly`

### `web/static/dashboard.css` and `web/static/archive.css`

- Define the current operator-facing visual style.

## Scripts

- `scripts/snapshot.py`
  - Adds repo root to `sys.path` then calls `highwayvlm.ingest.snapshot.main`.
- `scripts/run_vlm.py`
  - Adds repo root to `sys.path` then calls `highwayvlm.vlm.run_vlm.main`.

## Infrastructure

### `infra/docker/Dockerfile`

- Builds the app container.
- Installs Python dependencies.
- Creates runtime directories.
- Runs `uvicorn main:app`.

### `infra/docker/docker-compose.server.yml`

- Server deployment definition.
- Mounts host data and log directories into `/app/data` and `/app/logs`.

### `infra/monitoring/monitor.py`

- CLI for printing archive summaries, hourly rows, incident rows, or a watch loop.

### `infra/monitoring/monitor.ps1`

- PowerShell wrapper for the monitoring CLI.

## Runtime Data

- `data/highwayvlm.db`
  - SQLite database
- `data/frames/live/`
  - saved camera frames
- `data/raw_vlm_outputs/`
  - per-analysis raw JSON output files
- `logs/incidents.jsonl`
  - append-only incident log

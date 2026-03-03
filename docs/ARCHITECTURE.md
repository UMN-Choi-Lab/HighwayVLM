# Architecture

## Purpose

HighwayVLM is a single-process FastAPI application with an in-process background worker. The server both exposes the operator UI/API and runs the polling and VLM analysis loop.

## Main Components

### App Entrypoint

- `main.py`
  - Imports `app` from `highwayvlm.api`.

### API Layer

- `highwayvlm/api.py`
  - Creates `FastAPI(title="HighwayVLM API")`
  - Mounts:
    - `/frames` -> `data/frames`
    - `/static` -> `web/static`
  - Serves HTML pages from `web/`
  - Exposes JSON endpoints used by the dashboard and archive views
  - Starts the background worker during FastAPI startup

### Orchestration Layer

- `highwayvlm/pipeline.py`
  - Maintains per-camera in-memory state
  - Polls configured cameras
  - Deduplicates unchanged frames
  - Applies VLM rate limits and cooldown logic
  - Calls the VLM client
  - Persists all outcomes through `storage.insert_log()`

### Ingest Layer

- `highwayvlm/ingest/fetcher.py`
  - Fetches direct images
  - Extracts image URLs from JSON payloads
  - Extracts image URLs from viewer HTML using regex
  - Falls back to metadata endpoint strategies if the configured snapshot URL is not a direct image

### VLM Layer

- `highwayvlm/vlm/client.py`
  - Builds the traffic-monitoring prompt
  - Encodes snapshot bytes as a data URL
  - Sends a Chat Completions request to an OpenAI-compatible API
  - Parses JSON from the response text
  - Normalizes loose outputs into the strict expected schema
  - Validates the final payload with Pydantic

### Persistence Layer

- `highwayvlm/storage.py`
  - Creates and migrates SQLite tables
  - Stores every polling/VLM event in `vlm_logs`
  - Writes incident rows to `incident_events`
  - Writes hourly archive rows to `hourly_snapshots`
  - Writes one-or-more hourly incident detail rows to `hourly_incident_reports`
  - Appends incident JSONL rows to `logs/incidents.jsonl`

### Presentation Layer

- `web/`
  - Static pages
  - Client-side fetches against the FastAPI JSON endpoints

## Runtime Sequence

1. `uvicorn main:app` imports `highwayvlm.api:app`.
2. FastAPI startup runs `_bootstrap()` then `_start_worker()`.
3. `_bootstrap()` initializes the database and syncs the camera catalog.
4. `_start_worker()` launches `pipeline.run_loop()` in a daemon thread.
5. The worker repeatedly calls `run_once(states, client)`.
6. For each due camera:
   - fetch snapshot
   - hash bytes
   - save frame
   - decide whether to skip or analyze
   - if analyzed, call the VLM and persist the result
7. The frontend pages poll JSON endpoints for summaries and archive data.

Cadence nuance:

- camera poll intervals are configured per camera
- the worker still handles cameras sequentially in one process
- after each `run_once()` pass, the process sleeps for `RUN_INTERVAL_SECONDS`
- actual per-camera spacing is therefore the configured target plus the time spent fetching and analyzing cameras in that loop

## Why The Worker Lives Inside The API Process

This app currently favors simplicity over separation:

- one process
- one startup command
- one shared local SQLite file
- no message queue or scheduler service

Tradeoff:

- easier local development
- less operational surface area
- tighter coupling between API uptime and ingest/VLM execution

## VLM Call Path

The live worker path is:

`highwayvlm/api.py` -> `pipeline.run_loop()` -> `pipeline.run_once()` -> `VLMClient.analyze()` -> OpenAI-compatible `/chat/completions`

The call currently sends:

- a system prompt with incident taxonomy and strict JSON instructions
- a user message containing camera context and timestamp
- an image payload encoded as `image_url`

## OpenAPI

FastAPI is not customized to disable its documentation endpoints, so these are part of the current architecture:

- `/docs`
- `/redoc`
- `/openapi.json`

These describe the JSON and page routes declared in `highwayvlm/api.py`.

## Current Architectural Caveats

- `HOURLY_FRAMES_DIR` and `INCIDENT_REPORTS_DIR` exist in settings as reserved output locations, but the active live worker does not write to them.

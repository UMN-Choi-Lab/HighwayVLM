# Quick Reference

This is the shortest practical map of the HighwayVLM codebase.

## 5 Core Files

1. `highwayvlm/pipeline.py`
   - Directory: `highwayvlm/`
   - Purpose: live engine
   - Handles:
     - polling cameras
     - saving frames
     - deciding whether to skip or analyze
     - writing logs

2. `highwayvlm/vlm/client.py`
   - Directory: `highwayvlm/vlm/`
   - Purpose: prompt and model client
   - Handles:
     - system prompt
     - user prompt
     - image encoding
     - OpenAI-compatible API call to `POST /chat/completions`
     - response parsing and validation

3. `highwayvlm/api.py`
   - Directory: `highwayvlm/`
   - Purpose: FastAPI app
   - Handles:
     - page routes
     - JSON API routes
     - mounting `/frames` and `/static`
     - starting the background worker on startup

4. `highwayvlm/settings.py`
   - Directory: `highwayvlm/`
   - Purpose: centralized runtime configuration
   - Handles:
     - `RUN_INTERVAL_SECONDS`
     - `MIN_VLM_INTERVAL_SECONDS`
     - `VLM_MAX_CALLS_PER_RUN`
     - timeouts
     - retries
     - model name
     - base URL
     - filesystem paths

5. `highwayvlm/storage.py`
   - Directory: `highwayvlm/`
   - Purpose: persistence layer
   - Handles:
     - SQLite schema creation
     - `vlm_logs`
     - `incident_events`
     - `hourly_snapshots`
     - `hourly_incident_reports`
     - dashboard and archive query helpers

## 2 More Files To Keep Handy

6. `config/cameras.yaml`
   - Directory: `config/`
   - Purpose: active camera list
   - Controls:
     - which cameras are active
     - camera names
     - snapshot URLs
     - corridor and direction labels

7. `web/static/dashboard.js`
   - Directory: `web/static/`
   - Purpose: main dashboard frontend logic
   - Handles:
     - fetching `/cameras`
     - fetching `/status/summary`
     - card rendering
     - timestamps
     - feed status labels
     - refresh behavior

## Top 10 Most Important Files

1. `highwayvlm/pipeline.py`
2. `highwayvlm/vlm/client.py`
3. `highwayvlm/api.py`
4. `highwayvlm/settings.py`
5. `highwayvlm/storage.py`
6. `config/cameras.yaml`
7. `web/static/dashboard.js`
8. `highwayvlm/ingest/fetcher.py`
   - snapshot fetching and image saving
9. `web/static/overnight.js`
   - overnight monitor behavior
10. `highwayvlm/config_loader.py`
   - loads and normalizes camera config

## Where Things Happen

### Prompts

- File: `highwayvlm/vlm/client.py`
- Look for:
  - `_build_prompt()`

### External AI API Call

- File: `highwayvlm/vlm/client.py`
- Look for:
  - `requests.post(...)`
  - `url = f"{self.base_url}/chat/completions"`

### FastAPI Routes

- File: `highwayvlm/api.py`

### Polling Setup

- Config source:
  - `highwayvlm/settings.py`
- Main setting:
  - `RUN_INTERVAL_SECONDS`
- Runtime execution:
  - `highwayvlm/pipeline.py`
  - `run_loop()`

### VLM Throttling

- File: `highwayvlm/settings.py`
- Main settings:
  - `MIN_VLM_INTERVAL_SECONDS`
  - `VLM_MAX_CALLS_PER_RUN`
  - `VLM_ERROR_COOLDOWN_SECONDS`

### Snapshot Fetching

- File: `highwayvlm/ingest/fetcher.py`

### Camera List

- File: `config/cameras.yaml`

### Dashboard Data

- Backend:
  - `highwayvlm/api.py`
  - `highwayvlm/storage.py`
- Frontend:
  - `web/static/dashboard.js`

### Hourly And Incident Archives

- Write path:
  - `highwayvlm/storage.py`
- Read path:
  - `highwayvlm/api.py`
  - `web/static/hourly.js`
  - `web/static/incidents.js`
  - `web/static/overnight.js`

## Directory Guide

1. `highwayvlm/`
   - Main backend package

2. `highwayvlm/vlm/`
   - Prompting and model client code

3. `highwayvlm/ingest/`
   - Snapshot fetch and ingest utilities

4. `web/`
   - Static HTML pages

5. `web/static/`
   - Frontend JS and CSS

6. `config/`
   - Camera definitions

7. `docs/`
   - Project documentation

8. `scripts/`
   - Thin command wrappers

9. `infra/`
   - Docker and monitoring tools

10. `data/`
   - Runtime outputs like frames, DB, and raw model outputs

## Read Order

If you want to understand the app quickly, read in this order:

1. `highwayvlm/settings.py`
2. `config/cameras.yaml`
3. `highwayvlm/api.py`
4. `highwayvlm/pipeline.py`
5. `highwayvlm/vlm/client.py`
6. `highwayvlm/storage.py`
7. `web/static/dashboard.js`

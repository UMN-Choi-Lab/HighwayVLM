# HighwayVLM

HighwayVLM is a FastAPI app that polls freeway camera snapshots, sends frames to an OpenAI-compatible vision model, stores structured traffic results in SQLite, and serves a simple dashboard plus archive views.

## Current State

- Runtime: `python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- Backend: FastAPI
- Model API: OpenAI-compatible `chat/completions`
- Storage: SQLite, saved frames, raw VLM outputs
- Frontend: static HTML, CSS, and JS served by FastAPI
- OpenAPI docs:
  - `/docs`
  - `/redoc`
  - `/openapi.json`

## What The App Does

1. Loads camera definitions from `config/cameras.yaml`.
2. Tries to poll each camera on its configured cadence.
3. Saves each frame under `data/frames/live/...`.
4. Calls the VLM only when the current frame is eligible for analysis, then stores logs and any structured result.
5. Serves dashboard, incident, hourly, and overnight views.

Realized per-camera cadence can be slower than the configured interval because the worker processes cameras sequentially and then sleeps for `RUN_INTERVAL_SECONDS`.

## Observed Overnight Run

The cost analysis uses the overnight window from `12:00 AM` to `6:00 AM` Central Time on `March 3, 2026`.

- The stored data shows `288` analyzed frames total across `4` cameras.
- That is `72` analyses per camera over `6` hours.
- Over the full 6-hour window, that averages to `1` analysis every `5` minutes per camera.
- That overnight run reflects the `MIN_VLM_INTERVAL_SECONDS=300` setup used at the time.
- The timestamps do not show a steady 5-minute schedule.
- The timestamps also do not show a continuous 30-second schedule for the full night.
- When the app was actively running, each camera was analyzed about every `43` to `45` seconds.

The cost extrapolation in `docs/COST_ANALYSIS.md` should be read as:

- observed spend based on a real overnight run using the `300` second minimum VLM interval
- projected cost for a future design that analyzes every camera every `30` seconds

## Main Files

- `main.py`: app entrypoint
- `highwayvlm/api.py`: FastAPI routes, static mounts, startup wiring
- `highwayvlm/pipeline.py`: polling loop, frame capture, VLM call flow
- `highwayvlm/ingest/fetcher.py`: snapshot fetching
- `highwayvlm/vlm/client.py`: prompt build, image encoding, API call, JSON parsing
- `highwayvlm/storage.py`: SQLite reads and writes
- `web/`: dashboard and archive frontend
- `config/`: camera list
- `infra/`: docker and monitoring helpers

## API

Primary JSON routes:

- `GET /health`
- `GET /cameras`
- `GET /logs/latest`
- `GET /logs`
- `GET /status/summary`
- `GET /api/incidents`
- `GET /api/hourly`
- `GET /api/archive/overview`

HTML endpoints:

- `GET /`
- `GET /incidents`
- `GET /hourly`
- `GET /overnight`

## VLM Flow

- Default model: `gpt-4o-mini`
- Default base URL: `https://api.openai.com/v1`
- Endpoint used: `POST /chat/completions`
- Request contents:
  - system prompt
  - user prompt with camera metadata
  - one base64 image
- Expected response:
  - JSON with `observed_direction`, `traffic_state`, `incidents`, `notes`, and `overall_confidence`

## Local Setup

1. Install dependencies:
   `python -m pip install -r requirements.txt`
2. Create `.env` with at least:
   `OPENAI_API_KEY=...`
3. Run the app:
   `python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
4. Open `http://localhost:8000`

## Environment Variables

- `OPENAI_API_KEY`
- `VLM_MODEL`
- `RUN_INTERVAL_SECONDS`
- `MIN_VLM_INTERVAL_SECONDS`
- `VLM_MAX_CALLS_PER_RUN`

## Runtime Outputs

- `data/highwayvlm.db`: SQLite database
- `data/frames/live/...`: saved frames
- `data/raw_vlm_outputs/*.json`: raw VLM responses
- `logs/incidents.jsonl`: incident log

## Folders

- `highwayvlm/`: backend code
- `web/`: UI
- `config/`: camera definitions
- `scripts/`: one-off runners
- `infra/`: docker and monitoring helpers
- `docs/`: project docs
- `data/`: runtime artifacts
- `logs/`: runtime logs

## Entry Points

- `python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- `python scripts/snapshot.py`
- `python scripts/run_vlm.py`
- `python infra/monitoring/monitor.py summary`

## Documentation Index

- `docs/APP_REFERENCE.md`
- `docs/API_REFERENCE.md`
- `docs/ARCHITECTURE.md`
- `docs/STRUCTURE.md`
- `docs/REPO_MAP.md`
- `docs/COST_ANALYSIS.md`

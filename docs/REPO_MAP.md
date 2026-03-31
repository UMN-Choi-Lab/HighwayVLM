# Repo Map

## Read This First

- Start in `highwayvlm/` for backend logic.
- Start in `web/` for frontend behavior.
- Start in `infra/` for deployment or operator tooling.
- Treat `data/` and `logs/` as generated runtime output, not source.

## Active Code Areas

- `main.py`
  - App import entrypoint.
- `highwayvlm/`
  - Live backend package.
- `web/`
  - Static UI pages and assets.
- `config/`
  - Camera catalog and configuration.
- `scripts/`
  - Thin execution wrappers.
- `infra/`
  - Docker and monitoring helpers.

## Documentation

- `README.md`
  - Current-state project overview.
- `docs/APP_REFERENCE.md`
  - Full system reference.
- `docs/API_REFERENCE.md`
  - Route reference.
- `docs/POLLING.md`
  - Central polling and refresh cadence reference.
- `docs/ARCHITECTURE.md`
  - Architectural summary.
- `docs/STRUCTURE.md`
  - Folder and file reference.

## Generated Runtime Areas

- `data/`
  - SQLite DB, frames, and raw model outputs.
- `logs/`
  - Incident JSONL output.

## Remaining Known Gaps

- `HOURLY_FRAMES_DIR` and `INCIDENT_REPORTS_DIR` are still defined in settings, but the active live worker does not write to them.

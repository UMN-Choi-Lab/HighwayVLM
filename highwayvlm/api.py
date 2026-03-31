import threading
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from highwayvlm.config_loader import load_cameras
from highwayvlm.pipeline import run_loop
from highwayvlm.settings import (
    FRAMES_DIR,
    get_runtime_settings_snapshot,
)
from highwayvlm.storage import (
    clear_false_alarms,
    clear_hourly,
    clear_incidents,
    clear_vlm_logs,
    get_archive_overview,
    get_debug_stats,
    get_status_summary,
    init_db,
    list_hourly_snapshots,
    list_incident_events,
    list_latest_log,
    list_logs,
    sync_cameras,
    toggle_false_alarm,
)

app = FastAPI(title="HighwayVLM API")

_worker_started = False
_ROOT = Path(__file__).resolve().parent.parent
_WEB_DIR = _ROOT / "web"
_STATIC_DIR = _WEB_DIR / "static"

FRAMES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/frames", StaticFiles(directory=FRAMES_DIR), name="frames")
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def _bootstrap():
    init_db()
    cameras = load_cameras()
    if cameras:
        sync_cameras(cameras)


def _start_worker():
    global _worker_started
    if _worker_started:
        return
    _worker_started = True
    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()


@app.on_event("startup")
def startup():
    _bootstrap()
    _start_worker()


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return FileResponse(_WEB_DIR / "dashboard.html")


@app.get("/incidents", response_class=HTMLResponse)
def incidents_page():
    return FileResponse(_WEB_DIR / "incidents.html")


@app.get("/camera/{camera_id}/incidents")
def camera_incidents_page(camera_id: str):
    return RedirectResponse(url=f"/incidents?camera_id={quote(camera_id)}")


@app.get("/hourly", response_class=HTMLResponse)
def hourly_page():
    return FileResponse(_WEB_DIR / "hourly.html")


@app.get("/camera/{camera_id}/hourly")
def camera_hourly_page(camera_id: str):
    return RedirectResponse(url=f"/hourly?camera_id={quote(camera_id)}")


@app.get("/overnight", response_class=HTMLResponse)
def overnight_page():
    return FileResponse(_WEB_DIR / "overnight.html")


@app.get("/camera/{camera_id}/overnight")
def camera_overnight_page(camera_id: str):
    return RedirectResponse(url=f"/overnight?camera_id={quote(camera_id)}")


@app.get("/debug", response_class=HTMLResponse)
def debug_page():
    return FileResponse(_WEB_DIR / "debug.html")


@app.get("/api/debug/stats")
def debug_stats_api(
    camera_id: Optional[str] = None,
    hours: int = Query(1, ge=1, le=168),
):
    stats = get_debug_stats(camera_id=camera_id, hours=hours)
    stats["settings"] = get_runtime_settings_snapshot()
    return stats


@app.get("/api/runtime/settings")
def runtime_settings_api():
    return get_runtime_settings_snapshot()


@app.post("/api/debug/clear")
def debug_clear_api(camera_id: Optional[str] = None):
    deleted = clear_vlm_logs(camera_id=camera_id)
    return {"deleted": deleted}


@app.post("/api/incidents/clear")
def incidents_clear_api(camera_id: Optional[str] = None):
    deleted = clear_incidents(camera_id=camera_id)
    return {"deleted": deleted}


@app.post("/api/incidents/clear_false_alarms")
def incidents_clear_false_alarms_api(camera_id: Optional[str] = None):
    deleted = clear_false_alarms(camera_id=camera_id)
    return {"deleted": deleted}


@app.post("/api/incidents/{incident_id}/false_alarm")
def incidents_false_alarm_api(incident_id: int):
    result = toggle_false_alarm(incident_id)
    if result is None:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"error": "Incident not found"})
    return result


@app.post("/api/hourly/clear")
def hourly_clear_api(camera_id: Optional[str] = None):
    deleted = clear_hourly(camera_id=camera_id)
    return {"deleted": deleted}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/health")
def api_health():
    return {"status": "ok"}


@app.get("/cameras")
def cameras():
    return load_cameras()


@app.get("/api/cameras")
def cameras_api():
    return load_cameras()


@app.get("/logs/latest")
def logs_latest(camera_id: Optional[str] = None):
    return list_latest_log(camera_id=camera_id) or {}


@app.get("/api/logs/latest")
def logs_latest_api(camera_id: Optional[str] = None):
    return list_latest_log(camera_id=camera_id) or {}


@app.get("/logs")
def logs(
    camera_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    return list_logs(limit=limit, camera_id=camera_id)


@app.get("/api/logs")
def logs_api(
    camera_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    return list_logs(limit=limit, camera_id=camera_id)


@app.get("/status/summary")
def status_summary():
    return get_status_summary(load_cameras())


@app.get("/api/incidents")
def incidents_api(
    camera_id: Optional[str] = None,
    limit: int = Query(200, ge=1, le=2000),
    include_false_alarms: bool = False,
):
    return list_incident_events(
        limit=limit,
        camera_id=camera_id,
        include_false_alarms=include_false_alarms,
    )


@app.get("/api/hourly")
def hourly_api(
    camera_id: Optional[str] = None,
    limit: int = Query(336, ge=1, le=2000),
):
    return list_hourly_snapshots(limit=limit, camera_id=camera_id)


@app.get("/api/archive/overview")
def archive_overview_api(
    camera_id: Optional[str] = None,
    include_false_alarms: bool = False,
):
    return get_archive_overview(
        camera_id=camera_id,
        include_false_alarms=include_false_alarms,
    )

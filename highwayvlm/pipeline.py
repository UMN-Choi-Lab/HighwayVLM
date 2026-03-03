import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib

from highwayvlm.config_loader import load_cameras
from highwayvlm.ingest.fetcher import fetch_snapshot_bytes, save_snapshot
from highwayvlm.settings import (
    RAW_VLM_OUTPUT_DIR,
    get_min_vlm_interval_seconds,
    get_run_interval_seconds,
    get_vlm_error_cooldown_seconds,
    get_vlm_max_calls_per_run,
    get_vlm_model,
)
from highwayvlm.storage import init_db, insert_log, sanitize_error_message, sync_cameras
from highwayvlm.vlm.client import VLMClient


def _utc_now():
    return datetime.now(timezone.utc)


def _utc_iso():
    return _utc_now().isoformat()


def _hash_bytes(payload):
    return hashlib.sha256(payload).hexdigest()

def _is_quota_error(exc):
    if not exc:
        return False
    message = str(exc).lower()
    return "insufficient_quota" in message or "exceeded your current quota" in message


@dataclass
class CameraState:
    last_seen_hash: str | None = None
    last_seen_at: datetime | None = None
    last_processed_hash: str | None = None
    last_processed_at: datetime | None = None
    last_image_path: str | None = None
    last_polled_at: datetime | None = None
    last_error_at: datetime | None = None


def _write_raw_output(camera_id, captured_at, model, text, parsed):
    if not text:
        return None
    RAW_VLM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = captured_at or _utc_now().strftime("%Y%m%dT%H%M%SZ")
    path = RAW_VLM_OUTPUT_DIR / f"{camera_id}_{timestamp}.json"
    payload = {
        "camera_id": camera_id,
        "captured_at": captured_at,
        "model": model,
        "response_text": text,
        "parsed": parsed,
    }
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return path


def _seconds_since(value):
    if not value:
        return None
    return (_utc_now() - value).total_seconds()


def run_once(states, client):
    cameras = load_cameras()
    init_db()
    sync_cameras(cameras)
    min_vlm_interval = get_min_vlm_interval_seconds()
    error_cooldown = get_vlm_error_cooldown_seconds()
    max_calls = get_vlm_max_calls_per_run()
    max_calls = max_calls if max_calls and max_calls > 0 else None
    calls_made = 0
    camera_entries = []
    for camera in cameras:
        camera_id = camera.get("camera_id")
        if not camera_id:
            continue
        state = states.setdefault(camera_id, CameraState())
        camera_entries.append((camera, state))
    camera_entries.sort(
        key=lambda entry: entry[1].last_processed_at
        or datetime.min.replace(tzinfo=timezone.utc)
    )
    for camera, state in camera_entries:
        camera_id = camera.get("camera_id")
        state.last_polled_at = _utc_now()
        base_log = {
            "created_at": _utc_iso(),
            "captured_at": None,
            "camera_id": camera_id,
            "camera_name": camera.get("name"),
            "corridor": camera.get("corridor"),
            "direction": camera.get("direction"),
            "observed_direction": None,
            "traffic_state": None,
            "incidents_json": None,
            "notes": None,
            "overall_confidence": None,
            "image_path": None,
            "vlm_model": client.model,
            "raw_response": None,
            "error": None,
            "skipped_reason": None,
            "frame_hash": None,
            "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
            "last_processed_at": state.last_processed_at.isoformat() if state.last_processed_at else None,
        }
        try:
            image_bytes, content_type = fetch_snapshot_bytes(camera)
        except Exception as exc:
            print(f"Snapshot failed for {camera_id}: {exc}")
            if state.last_image_path:
                base_log["image_path"] = state.last_image_path
            base_log["error"] = sanitize_error_message(f"snapshot_failed: {exc}")
            insert_log(base_log)
            continue
        if not image_bytes:
            base_log["skipped_reason"] = "empty_snapshot"
            if state.last_image_path:
                base_log["image_path"] = state.last_image_path
            insert_log(base_log)
            continue
        image_hash = _hash_bytes(image_bytes)
        state.last_seen_hash = image_hash
        state.last_seen_at = _utc_now()
        base_log["frame_hash"] = image_hash
        base_log["last_seen_at"] = state.last_seen_at.isoformat()
        captured_at = _utc_now().strftime("%Y%m%dT%H%M%SZ")
        image_path = save_snapshot(camera_id, image_bytes, content_type, captured_at)
        state.last_image_path = str(image_path)
        if state.last_processed_hash == image_hash:
            base_log["captured_at"] = captured_at
            base_log["image_path"] = str(image_path)
            base_log["skipped_reason"] = "unchanged_frame"
            insert_log(base_log)
            continue
        time_since_processed = _seconds_since(state.last_processed_at)
        if min_vlm_interval and time_since_processed is not None and time_since_processed < min_vlm_interval:
            base_log["captured_at"] = captured_at
            base_log["image_path"] = str(image_path)
            base_log["skipped_reason"] = "vlm_min_interval"
            insert_log(base_log)
            continue
        time_since_error = _seconds_since(state.last_error_at)
        if error_cooldown and time_since_error is not None and time_since_error < error_cooldown:
            base_log["captured_at"] = captured_at
            base_log["image_path"] = str(image_path)
            base_log["skipped_reason"] = "vlm_error_cooldown"
            insert_log(base_log)
            continue
        if max_calls is not None and calls_made >= max_calls:
            base_log["captured_at"] = captured_at
            base_log["image_path"] = str(image_path)
            base_log["skipped_reason"] = "vlm_max_calls_per_run"
            insert_log(base_log)
            continue
        try:
            result, raw_text = client.analyze(camera, image_bytes, captured_at, content_type)
        except Exception as exc:
            print(f"VLM failed for {camera_id}: {exc}")
            base_log["captured_at"] = captured_at
            base_log["image_path"] = str(image_path)
            if _is_quota_error(exc):
                base_log["skipped_reason"] = "vlm_quota_exceeded"
            else:
                base_log["error"] = sanitize_error_message(f"vlm_failed: {exc}")
            state.last_error_at = _utc_now()
            insert_log(base_log)
            continue
        state.last_processed_at = _utc_now()
        state.last_processed_hash = image_hash
        base_log["last_processed_at"] = state.last_processed_at.isoformat()
        calls_made += 1
        _write_raw_output(camera_id, captured_at, client.model, raw_text, result.model_dump())
        insert_log(
            {
                "created_at": _utc_iso(),
                "captured_at": captured_at,
                "camera_id": camera_id,
                "camera_name": camera.get("name"),
                "corridor": camera.get("corridor"),
                "direction": camera.get("direction"),
                "observed_direction": result.observed_direction,
                "traffic_state": result.traffic_state,
                "incidents_json": json.dumps([i.model_dump() for i in result.incidents], ensure_ascii=True),
                "notes": result.notes,
                "overall_confidence": result.overall_confidence,
                "image_path": str(image_path),
                "vlm_model": client.model,
                "raw_response": raw_text,
                "error": None,
                "skipped_reason": None,
                "frame_hash": image_hash,
                "last_seen_at": state.last_seen_at.isoformat() if state.last_seen_at else None,
                "last_processed_at": state.last_processed_at.isoformat() if state.last_processed_at else None,
            }
        )


def run_loop():
    interval = get_run_interval_seconds()
    client = VLMClient(model=get_vlm_model())
    states = {}
    while True:
        run_once(states, client)
        time.sleep(interval)

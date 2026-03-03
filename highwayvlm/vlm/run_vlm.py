"""
VLM inference runner.

Loads the latest snapshot per camera, calls the VLM, and stores logs.
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from highwayvlm.config_loader import load_cameras
from highwayvlm.settings import (
    FRAMES_DIR,
    RAW_VLM_OUTPUT_DIR,
    get_vlm_interval_seconds,
    get_vlm_model,
)
from highwayvlm.storage import init_db, insert_log, sync_cameras
from highwayvlm.vlm.client import VLMClient


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _latest_snapshot(camera_id):
    if not FRAMES_DIR.exists():
        return None
    candidates = [
        path for path in FRAMES_DIR.rglob(f"{camera_id}_*")
        if path.is_file()
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _parse_captured_at(path, camera_id):
    stem = path.stem
    if stem.startswith(f"{camera_id}_"):
        return stem.split("_", 1)[1]
    return None


def _guess_content_type(path):
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".gif":
        return "image/gif"
    return "image/jpeg"


def _normalize_image_path(path):
    if not path:
        return None
    try:
        return str(path.relative_to(FRAMES_DIR))
    except ValueError:
        return str(path)


def _write_raw_output(camera_id, captured_at, model, text, parsed):
    RAW_VLM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = captured_at or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
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


def run_once():
    cameras = load_cameras()
    init_db()
    sync_cameras(cameras)
    model = get_vlm_model()
    client = VLMClient(model=model)
    for camera in cameras:
        camera_id = camera.get("camera_id")
        image_path = _latest_snapshot(camera_id)
        if not image_path:
            print(f"No snapshots found for {camera_id}")
            continue
        captured_at = _parse_captured_at(image_path, camera_id)
        try:
            image_bytes = image_path.read_bytes()
            content_type = _guess_content_type(image_path)
            result, text = client.analyze(camera, image_bytes, captured_at, content_type)
        except Exception as exc:
            print(f"VLM failed for {camera_id}: {exc}")
            continue
        _write_raw_output(camera_id, captured_at, model, text, result.model_dump())
        insert_log(
            {
                "created_at": _utc_now(),
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
                "image_path": _normalize_image_path(image_path),
                "vlm_model": model,
                "raw_response": text,
            }
        )


def run_loop():
    interval = get_vlm_interval_seconds()
    while True:
        run_once()
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Run VLM inference on snapshots")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    args = parser.parse_args()
    if args.loop:
        run_loop()
    else:
        run_once()


if __name__ == "__main__":
    main()

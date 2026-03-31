"""
Fetches MnDOT camera snapshots and saves them locally.
"""

import argparse
from datetime import datetime, timezone

from highwayvlm.config_loader import load_cameras
from highwayvlm.ingest.fetcher import fetch_snapshot_bytes, save_snapshot
from highwayvlm.storage import init_db, upsert_cameras


def fetch_snapshots_once():
    cameras = load_cameras()
    init_db()
    upsert_cameras(cameras)
    results = []
    for camera in cameras:
        camera_id = camera.get("camera_id")
        if not camera_id:
            continue
        try:
            image_bytes, content_type = fetch_snapshot_bytes(camera)
        except Exception as exc:
            print(f"Snapshot failed for {camera_id}: {exc}")
            continue
        if not image_bytes:
            continue
        captured_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = save_snapshot(camera_id, image_bytes, content_type, captured_at)
        results.append({"camera_id": camera_id, "captured_at": captured_at, "image_path": str(path)})
    return results


def run_loop():
    from highwayvlm.settings import get_system_interval_seconds
    import time

    interval = get_system_interval_seconds()
    while True:
        fetch_snapshots_once()
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Fetch camera snapshots")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    args = parser.parse_args()
    if args.loop:
        run_loop()
    else:
        fetch_snapshots_once()


if __name__ == "__main__":
    main()

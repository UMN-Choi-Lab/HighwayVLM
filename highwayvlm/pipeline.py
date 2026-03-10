import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib

from highwayvlm.config_loader import load_cameras
from highwayvlm.ingest.fetcher import fetch_snapshot_bytes, save_snapshot
from highwayvlm.ingest.annotate import save_annotated_image
from highwayvlm.ingest.clip import save_incident_clip
from highwayvlm.ingest.motion import analyze_motion, should_call_vlm
from highwayvlm.ingest.stream import build_stream_url, extract_frames
from highwayvlm.ingest.vehicle import get_detector
from highwayvlm.settings import (
    RAW_VLM_OUTPUT_DIR,
    get_hls_enabled,
    get_hls_max_consecutive_failures,
    get_incident_confirm_cycles,
    get_incident_high_confidence,
    get_incident_low_confidence,
    get_min_vlm_interval_seconds,
    get_periodic_vlm_interval_seconds,
    get_run_interval_seconds,
    get_vlm_error_cooldown_seconds,
    get_vlm_model,
)
from highwayvlm.storage import (
    get_false_alarm_summary,
    init_db,
    insert_log,
    sanitize_error_message,
    sync_cameras,
)
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
class PendingIncident:
    """An incident awaiting confirmation across consecutive cycles."""
    incident_types: set
    first_seen_at: datetime
    cycle_count: int = 1
    last_result: object = None
    last_raw_text: str | None = None
    last_capture_data: dict | None = None


@dataclass
class CameraState:
    last_seen_hash: str | None = None
    last_seen_at: datetime | None = None
    last_processed_hash: str | None = None
    last_processed_at: datetime | None = None
    last_image_path: str | None = None
    last_polled_at: datetime | None = None
    last_error_at: datetime | None = None
    last_vlm_call_at: datetime | None = None
    last_traffic_state: str | None = None
    last_motion_score: float | None = None
    hls_consecutive_failures: int = 0
    hls_last_retry_at: datetime | None = None
    pending_incident: PendingIncident | None = None


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


def _build_false_alarm_context(camera_id):
    """Build a context string from recent false alarm patterns for this camera."""
    patterns = get_false_alarm_summary(camera_id=camera_id, days=7, limit=5)
    if not patterns:
        return None
    lines = ["KNOWN FALSE ALARM PATTERNS for this camera (marked by human operators):"]
    for p in patterns:
        lines.append(
            f"- {p['incident_type']} reported {p['count']} time(s) as false alarm. "
            f"Example: {p['example_description']}"
        )
    lines.append("Be extra cautious about these incident types — they are often false positives on this camera.")
    return "\n".join(lines)


def _incidents_match(prev_types, new_incidents):
    """Check if new incidents overlap with previously pending incident types."""
    new_types = {i.type for i in new_incidents}
    return bool(prev_types & new_types)


def _should_confirm_immediately(result, stopped_vehicles, is_nighttime):
    """High-confidence incidents with YOLO-confirmed stopped vehicles skip confirmation.
    At night, NEVER skip confirmation — too many false positives."""
    if is_nighttime:
        return False
    high_conf = get_incident_high_confidence()
    if result.overall_confidence >= high_conf and stopped_vehicles:
        return True
    return False


def _is_low_confidence(result):
    """Low-confidence incidents are logged but not archived as incidents."""
    return result.overall_confidence < get_incident_low_confidence()


def _get_confirm_cycles(is_nighttime):
    """At night, require more confirmation cycles."""
    base = get_incident_confirm_cycles()
    return base + 1 if is_nighttime else base


def _run_hls_branch(camera, state, client, base_log, captured_at):
    """Attempt HLS stream extraction + motion analysis. Returns True if handled."""
    camera_id = camera.get("camera_id")
    max_failures = get_hls_max_consecutive_failures()
    periodic_interval = get_periodic_vlm_interval_seconds()

    # Check if we should retry after consecutive failures (every 5 min)
    if state.hls_consecutive_failures >= max_failures:
        retry_age = _seconds_since(state.hls_last_retry_at)
        if retry_age is not None and retry_age < 300:
            return False  # Still in backoff, fall through to snapshot
        # Reset to allow retry
        state.hls_consecutive_failures = 0

    # Extract frames from HLS stream
    stream_url = build_stream_url(camera_id)
    try:
        capture = extract_frames(camera_id, stream_url)
    except Exception as exc:
        print(f"HLS extraction failed for {camera_id}: {exc}")
        state.hls_consecutive_failures += 1
        state.hls_last_retry_at = _utc_now()
        return False

    if capture.error or len(capture.frames) < 2:
        if capture.error:
            print(f"HLS stream error for {camera_id}: {capture.error}")
        else:
            print(f"HLS got only {len(capture.frames)} frame(s) for {camera_id}, need ≥2")
        state.hls_consecutive_failures += 1
        state.hls_last_retry_at = _utc_now()
        return False

    # HLS success — reset failure counter
    state.hls_consecutive_failures = 0

    # Save first frame as the representative snapshot
    first_frame = capture.frames[0]
    image_path = save_snapshot(camera_id, first_frame.image_bytes, first_frame.content_type, captured_at)
    state.last_image_path = str(image_path)

    image_hash = _hash_bytes(first_frame.image_bytes)
    state.last_seen_hash = image_hash
    state.last_seen_at = _utc_now()

    base_log["frame_hash"] = image_hash
    base_log["last_seen_at"] = state.last_seen_at.isoformat()
    base_log["captured_at"] = captured_at
    base_log["image_path"] = str(image_path)
    base_log["source_type"] = "hls"

    # Run local motion analysis
    frame_bytes_list = [f.image_bytes for f in capture.frames]
    motion = analyze_motion(frame_bytes_list)

    base_log["motion_score"] = motion.changed_pixel_fraction
    base_log["anomaly_detected"] = 1 if motion.anomaly_detected else 0
    base_log["anomaly_reason"] = motion.anomaly_reason

    state.last_motion_score = motion.changed_pixel_fraction

    # Run YOLOv8 vehicle detection on middle frame
    detector = get_detector()
    middle_idx = len(capture.frames) // 2
    middle_frame_bytes = capture.frames[middle_idx].image_bytes
    vehicle = detector.detect(middle_frame_bytes)

    base_log["vehicle_count"] = vehicle.vehicle_count

    # YOLO cross-frame stopped vehicle detection
    last_frame = capture.frames[-1]
    stopped_vehicles = detector.detect_stopped(
        first_frame.image_bytes, last_frame.image_bytes
    )

    # Decision gate: should we call VLM?
    vlm_age = _seconds_since(state.last_vlm_call_at)
    call_vlm, reason = should_call_vlm(motion, vlm_age, periodic_interval)

    # Also call VLM if we have a pending incident to confirm
    if not call_vlm and state.pending_incident is not None:
        call_vlm = True
        reason = "pending_incident_confirmation"

    base_log["vlm_call_reason"] = reason

    if not call_vlm:
        # Use vehicle-derived traffic state (reliable count-based classification).
        base_log["traffic_state"] = vehicle.traffic_state
        base_log["vlm_model"] = "local_motion"
        base_log["skipped_reason"] = "local_motion_normal"
        base_log["notes"] = (
            f"Local analysis: changed_pixels={motion.changed_pixel_fraction:.4f}, "
            f"brightness={motion.mean_brightness:.0f}, "
            f"vehicle_count={vehicle.vehicle_count}"
        )
        state.last_traffic_state = vehicle.traffic_state
        insert_log(base_log)
        return True

    # Build enriched context for VLM
    false_alarm_ctx = _build_false_alarm_context(camera_id)
    motion_context = {
        "changed_pixel_fraction": round(motion.changed_pixel_fraction, 4),
        "traffic_state": vehicle.traffic_state,
        "vehicle_count": vehicle.vehicle_count,
        "anomaly_detected": motion.anomaly_detected,
        "anomaly_reason": motion.anomaly_reason,
        "mean_brightness": round(motion.mean_brightness, 1),
        "stopped_vehicles": stopped_vehicles,
        "false_alarm_context": false_alarm_ctx,
    }

    try:
        result, raw_text = client.analyze_comparison(
            camera,
            first_frame.image_bytes,
            last_frame.image_bytes,
            captured_at,
            content_type=first_frame.content_type,
            motion_context=motion_context,
        )
    except Exception as exc:
        print(f"VLM comparison failed for {camera_id}: {exc}")
        # Fall back to vehicle-derived traffic state
        base_log["traffic_state"] = vehicle.traffic_state
        if _is_quota_error(exc):
            base_log["skipped_reason"] = "vlm_quota_exceeded"
        else:
            base_log["error"] = sanitize_error_message(f"vlm_comparison_failed: {exc}")
        state.last_error_at = _utc_now()
        state.last_traffic_state = vehicle.traffic_state
        insert_log(base_log)
        return True

    # VLM success
    state.last_vlm_call_at = _utc_now()
    state.last_processed_at = _utc_now()
    state.last_processed_hash = image_hash
    state.last_traffic_state = result.traffic_state
    base_log["last_processed_at"] = state.last_processed_at.isoformat()

    _write_raw_output(camera_id, captured_at, client.model, raw_text, result.model_dump())

    # --- Confirmation pipeline for incidents ---
    confirmed_incidents = result.incidents
    is_nighttime = motion.is_nighttime
    confirm_cycles = _get_confirm_cycles(is_nighttime)

    if result.incidents:
        if _is_low_confidence(result):
            # Low confidence: log but don't archive as incident
            print(f"Low confidence ({result.overall_confidence:.2f}) incidents for {camera_id}, logging only")
            confirmed_incidents = []
            state.pending_incident = None

        elif _should_confirm_immediately(result, stopped_vehicles, is_nighttime):
            # High confidence + YOLO confirms stopped vehicle (daytime only) → report immediately
            print(f"High confidence ({result.overall_confidence:.2f}) + YOLO confirmed for {camera_id}, reporting immediately")
            confirmed_incidents = result.incidents
            state.pending_incident = None

        elif state.pending_incident is not None and _incidents_match(
            state.pending_incident.incident_types, result.incidents
        ):
            # Pending incident confirmed by consecutive detection
            state.pending_incident.cycle_count += 1
            if state.pending_incident.cycle_count >= confirm_cycles:
                print(f"Incident CONFIRMED for {camera_id} after {state.pending_incident.cycle_count} cycles")
                confirmed_incidents = result.incidents
                state.pending_incident = None
            else:
                # Still pending, need more cycles
                state.pending_incident.last_result = result
                state.pending_incident.last_raw_text = raw_text
                confirmed_incidents = []
        else:
            # First detection → mark as pending
            print(f"Incident PENDING confirmation for {camera_id} (confidence={result.overall_confidence:.2f})")
            state.pending_incident = PendingIncident(
                incident_types={i.type for i in result.incidents},
                first_seen_at=_utc_now(),
                last_result=result,
                last_raw_text=raw_text,
            )
            confirmed_incidents = []
    else:
        # No incidents: clear pending if any
        if state.pending_incident is not None:
            print(f"Pending incident CLEARED for {camera_id} (not confirmed)")
        state.pending_incident = None

    # Save video clip and annotated image only for CONFIRMED incidents
    clip_path = None
    annotated_path = None
    if confirmed_incidents:
        try:
            clip_path = save_incident_clip(camera_id, captured_at, capture.frames)
        except Exception as exc:
            print(f"Clip save failed for {camera_id}: {exc}")
        try:
            incidents_dicts = [i.model_dump() for i in confirmed_incidents]
            annotated_path = save_annotated_image(
                camera_id, captured_at,
                first_frame.image_bytes, last_frame.image_bytes,
                incidents_dicts,
            )
        except Exception as exc:
            print(f"Annotated image save failed for {camera_id}: {exc}")

    insert_log(
        {
            **base_log,
            "observed_direction": result.observed_direction,
            "traffic_state": result.traffic_state,
            "incidents_json": json.dumps(
                [i.model_dump() for i in confirmed_incidents], ensure_ascii=True
            ),
            "notes": result.notes,
            "overall_confidence": result.overall_confidence,
            "vlm_model": client.model,
            "raw_response": raw_text,
            "error": None,
            "skipped_reason": None,
            "clip_path": clip_path,
            "annotated_image_path": annotated_path,
        }
    )
    return True


def _get_max_workers():
    return int(os.getenv("PIPELINE_MAX_WORKERS", "6"))


def _process_camera(camera, state, client, hls_enabled, min_vlm_interval, error_cooldown):
    """Process a single camera. Called from thread pool."""
    camera_id = camera.get("camera_id")
    state.last_polled_at = _utc_now()
    captured_at = _utc_now().strftime("%Y%m%dT%H%M%SZ")
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
        "source_type": None,
        "motion_score": None,
        "anomaly_detected": None,
        "anomaly_reason": None,
        "vlm_call_reason": None,
        "vehicle_count": None,
        "clip_path": None,
    }

    # --- HLS branch ---
    if hls_enabled:
        handled = _run_hls_branch(camera, state, client, base_log, captured_at)
        if handled:
            return

    # --- Snapshot fallback (existing logic) ---
    base_log["source_type"] = "snapshot"
    try:
        image_bytes, content_type = fetch_snapshot_bytes(camera)
    except Exception as exc:
        print(f"Snapshot failed for {camera_id}: {exc}")
        if state.last_image_path:
            base_log["image_path"] = state.last_image_path
        base_log["error"] = sanitize_error_message(f"snapshot_failed: {exc}")
        insert_log(base_log)
        return
    if not image_bytes:
        base_log["skipped_reason"] = "empty_snapshot"
        if state.last_image_path:
            base_log["image_path"] = state.last_image_path
        insert_log(base_log)
        return
    image_hash = _hash_bytes(image_bytes)
    state.last_seen_hash = image_hash
    state.last_seen_at = _utc_now()
    base_log["frame_hash"] = image_hash
    base_log["last_seen_at"] = state.last_seen_at.isoformat()
    image_path = save_snapshot(camera_id, image_bytes, content_type, captured_at)
    state.last_image_path = str(image_path)
    if state.last_processed_hash == image_hash:
        base_log["captured_at"] = captured_at
        base_log["image_path"] = str(image_path)
        base_log["skipped_reason"] = "unchanged_frame"
        insert_log(base_log)
        return
    time_since_processed = _seconds_since(state.last_processed_at)
    if min_vlm_interval and time_since_processed is not None and time_since_processed < min_vlm_interval:
        base_log["captured_at"] = captured_at
        base_log["image_path"] = str(image_path)
        base_log["skipped_reason"] = "vlm_min_interval"
        insert_log(base_log)
        return
    time_since_error = _seconds_since(state.last_error_at)
    if error_cooldown and time_since_error is not None and time_since_error < error_cooldown:
        base_log["captured_at"] = captured_at
        base_log["image_path"] = str(image_path)
        base_log["skipped_reason"] = "vlm_error_cooldown"
        insert_log(base_log)
        return
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
        return
    state.last_processed_at = _utc_now()
    state.last_processed_hash = image_hash
    state.last_vlm_call_at = _utc_now()
    base_log["last_processed_at"] = state.last_processed_at.isoformat()
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
            "source_type": "snapshot",
            "motion_score": None,
            "anomaly_detected": None,
            "anomaly_reason": None,
            "vlm_call_reason": "snapshot_fallback",
        }
    )


def run_once(states, client):
    cameras = load_cameras()
    init_db()
    sync_cameras(cameras)
    min_vlm_interval = get_min_vlm_interval_seconds()
    error_cooldown = get_vlm_error_cooldown_seconds()
    hls_enabled = get_hls_enabled()
    camera_entries = []
    for camera in cameras:
        camera_id = camera.get("camera_id")
        if not camera_id:
            continue
        state = states.setdefault(camera_id, CameraState())
        camera_entries.append((camera, state))

    max_workers = _get_max_workers()
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _process_camera, camera, state, client,
                hls_enabled, min_vlm_interval, error_cooldown,
            ): camera.get("camera_id")
            for camera, state in camera_entries
        }
        for future in as_completed(futures):
            camera_id = futures[future]
            try:
                future.result()
            except Exception as exc:
                print(f"Unhandled error processing {camera_id}: {exc}")


def run_loop():
    interval = get_run_interval_seconds()
    client = VLMClient(model=get_vlm_model())
    states = {}
    while True:
        run_once(states, client)
        time.sleep(interval)

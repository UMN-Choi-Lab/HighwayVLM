import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from highwayvlm.settings import INCIDENTS_LOG_PATH, get_db_path


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


_REDACTION_RULES = [
    (re.compile(r"sk-[A-Za-z0-9]{10,}"), "sk-REDACTED"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._-]{10,}"), r"\1REDACTED"),
    (re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)(\S+)"), r"\1REDACTED"),
    (re.compile(r"(?i)(token\s*[:=]\s*)(\S+)"), r"\1REDACTED"),
]


def sanitize_error_message(value):
    if not value or not isinstance(value, str):
        return value
    sanitized = value
    for pattern, replacement in _REDACTION_RULES:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def _connect():
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def _ensure_columns(conn, table, columns):
    existing = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, ddl in columns.items():
        if name in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cameras (
                camera_id TEXT PRIMARY KEY,
                name TEXT,
                snapshot_url TEXT,
                source_url TEXT,
                corridor TEXT,
                direction TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vlm_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                captured_at TEXT,
                camera_id TEXT,
                camera_name TEXT,
                corridor TEXT,
                direction TEXT,
                observed_direction TEXT,
                traffic_state TEXT,
                incidents_json TEXT,
                notes TEXT,
                overall_confidence REAL,
                image_path TEXT,
                vlm_model TEXT,
                raw_response TEXT,
                error TEXT,
                skipped_reason TEXT,
                frame_hash TEXT,
                last_seen_at TEXT,
                last_processed_at TEXT,
                FOREIGN KEY(camera_id) REFERENCES cameras(camera_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incident_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                captured_at TEXT,
                camera_id TEXT,
                camera_name TEXT,
                corridor TEXT,
                direction TEXT,
                observed_direction TEXT,
                traffic_state TEXT,
                incident_type TEXT,
                severity TEXT,
                description TEXT,
                notes TEXT,
                overall_confidence REAL,
                image_path TEXT,
                vlm_model TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hourly_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT,
                camera_name TEXT,
                corridor TEXT,
                direction TEXT,
                hour_bucket TEXT,
                created_at TEXT,
                captured_at TEXT,
                image_path TEXT,
                frame_hash TEXT,
                traffic_state TEXT,
                incident_count INTEGER,
                status TEXT,
                summary TEXT,
                error TEXT,
                skipped_reason TEXT,
                UNIQUE(camera_id, hour_bucket)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hourly_incident_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id TEXT,
                hour_bucket TEXT,
                created_at TEXT,
                captured_at TEXT,
                image_path TEXT,
                traffic_state TEXT,
                report_kind TEXT,
                incident_type TEXT,
                severity TEXT,
                description TEXT,
                notes TEXT,
                overall_confidence REAL
            )
            """
        )
        _ensure_columns(
            conn,
            "cameras",
            {
                "source_url": "source_url TEXT",
            },
        )
        _ensure_columns(
            conn,
            "vlm_logs",
            {
                "created_at": "created_at TEXT",
                "captured_at": "captured_at TEXT",
                "camera_id": "camera_id TEXT",
                "camera_name": "camera_name TEXT",
                "corridor": "corridor TEXT",
                "direction": "direction TEXT",
                "observed_direction": "observed_direction TEXT",
                "traffic_state": "traffic_state TEXT",
                "incidents_json": "incidents_json TEXT",
                "notes": "notes TEXT",
                "overall_confidence": "overall_confidence REAL",
                "image_path": "image_path TEXT",
                "vlm_model": "vlm_model TEXT",
                "raw_response": "raw_response TEXT",
                "error": "error TEXT",
                "skipped_reason": "skipped_reason TEXT",
                "frame_hash": "frame_hash TEXT",
                "last_seen_at": "last_seen_at TEXT",
                "last_processed_at": "last_processed_at TEXT",
                "source_type": "source_type TEXT",
                "motion_score": "motion_score REAL",
                "anomaly_detected": "anomaly_detected INTEGER",
                "anomaly_reason": "anomaly_reason TEXT",
                "vlm_call_reason": "vlm_call_reason TEXT",
                "vehicle_count": "vehicle_count INTEGER",
                "clip_path": "clip_path TEXT",
                "annotated_image_path": "annotated_image_path TEXT",
            },
        )
        _ensure_columns(
            conn,
            "incident_events",
            {
                "clip_path": "clip_path TEXT",
                "false_alarm": "false_alarm INTEGER DEFAULT 0",
                "annotated_image_path": "annotated_image_path TEXT",
            },
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vlm_logs_camera ON vlm_logs(camera_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_vlm_logs_created ON vlm_logs(created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_incident_events_camera_created ON incident_events(camera_id, created_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hourly_snapshots_camera_hour ON hourly_snapshots(camera_id, hour_bucket)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hourly_snapshots_hour ON hourly_snapshots(hour_bucket)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_hourly_incident_reports_camera_hour ON hourly_incident_reports(camera_id, hour_bucket)"
        )


def upsert_cameras(cameras):
    if not cameras:
        return
    with _connect() as conn:
        for camera in cameras:
            camera_id = camera.get("camera_id")
            if not camera_id:
                continue
            conn.execute(
                """
                INSERT INTO cameras (
                    camera_id,
                    name,
                    snapshot_url,
                    source_url,
                    corridor,
                    direction,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(camera_id) DO UPDATE SET
                    name = excluded.name,
                    snapshot_url = excluded.snapshot_url,
                    source_url = excluded.source_url,
                    corridor = excluded.corridor,
                    direction = excluded.direction,
                    updated_at = excluded.updated_at
                """,
                (
                    camera_id,
                    camera.get("name"),
                    camera.get("snapshot_url"),
                    camera.get("source_url"),
                    camera.get("corridor"),
                    camera.get("direction"),
                    _utc_now(),
                ),
            )


def sync_cameras(cameras):
    if not cameras:
        return
    upsert_cameras(cameras)
    camera_ids = sorted(
        {camera.get("camera_id") for camera in cameras if camera.get("camera_id")}
    )
    if not camera_ids:
        return
    placeholders = ",".join("?" for _ in camera_ids)
    with _connect() as conn:
        conn.execute(
            f"DELETE FROM cameras WHERE camera_id NOT IN ({placeholders})",
            camera_ids,
        )


def list_cameras():
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT camera_id, name, snapshot_url, source_url, corridor, direction, updated_at
            FROM cameras
            ORDER BY camera_id
            """
        ).fetchall()
    return [
        {
            "camera_id": row[0],
            "name": row[1],
            "snapshot_url": row[2],
            "source_url": row[3],
            "corridor": row[4],
            "direction": row[5],
            "updated_at": row[6],
        }
        for row in rows
    ]


def insert_log(log_entry):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO vlm_logs (
                created_at,
                captured_at,
                camera_id,
                camera_name,
                corridor,
                direction,
                observed_direction,
                traffic_state,
                incidents_json,
                notes,
                overall_confidence,
                image_path,
                vlm_model,
                raw_response,
                error,
                skipped_reason,
                frame_hash,
                last_seen_at,
                last_processed_at,
                source_type,
                motion_score,
                anomaly_detected,
                anomaly_reason,
                vlm_call_reason,
                vehicle_count,
                clip_path,
                annotated_image_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_entry.get("created_at"),
                log_entry.get("captured_at"),
                log_entry.get("camera_id"),
                log_entry.get("camera_name"),
                log_entry.get("corridor"),
                log_entry.get("direction"),
                log_entry.get("observed_direction"),
                log_entry.get("traffic_state"),
                log_entry.get("incidents_json"),
                log_entry.get("notes"),
                log_entry.get("overall_confidence"),
                log_entry.get("image_path"),
                log_entry.get("vlm_model"),
                log_entry.get("raw_response"),
                log_entry.get("error"),
                log_entry.get("skipped_reason"),
                log_entry.get("frame_hash"),
                log_entry.get("last_seen_at"),
                log_entry.get("last_processed_at"),
                log_entry.get("source_type"),
                log_entry.get("motion_score"),
                log_entry.get("anomaly_detected"),
                log_entry.get("anomaly_reason"),
                log_entry.get("vlm_call_reason"),
                log_entry.get("vehicle_count"),
                log_entry.get("clip_path"),
                log_entry.get("annotated_image_path"),
            ),
        )
    _append_incident_log(log_entry)
    _archive_incident_events(log_entry)
    _archive_hourly_snapshot(log_entry)


def _parse_incidents(incidents_payload):
    if not incidents_payload:
        return []
    if isinstance(incidents_payload, list):
        return incidents_payload
    try:
        parsed = json.loads(incidents_payload)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


_INVALID_INCIDENT_TYPES = {
    "",
    "none",
    "no_incident",
    "no incidents",
    "clear",
    "false_alarm",
    "false_positive",
    "normal_traffic",
}

_FALSE_ALARM_HINTS = (
    "false alarm",
    "false positive",
    "no incident",
    "no incidents",
    "no active incident",
    "clear traffic",
    "normal traffic",
)


def _is_valid_incident(incident, base_notes=""):
    if not isinstance(incident, dict):
        return True
    incident_type = str(incident.get("type") or "").strip().lower()
    description = str(incident.get("description") or "").strip().lower()
    if incident_type in _INVALID_INCIDENT_TYPES:
        return False
    if description and any(token in description for token in _FALSE_ALARM_HINTS):
        return False
    return True


def _filter_valid_incidents(incidents, base_notes=""):
    return [incident for incident in incidents if _is_valid_incident(incident, base_notes)]


def _append_incident_log(log_entry):
    base_notes = (log_entry.get("notes") or "").strip()
    incidents = _filter_valid_incidents(
        _parse_incidents(log_entry.get("incidents_json")),
        base_notes=base_notes,
    )
    if not incidents:
        return
    payload = {
        "created_at": log_entry.get("created_at"),
        "captured_at": log_entry.get("captured_at"),
        "camera_id": log_entry.get("camera_id"),
        "camera_name": log_entry.get("camera_name"),
        "corridor": log_entry.get("corridor"),
        "direction": log_entry.get("direction"),
        "observed_direction": log_entry.get("observed_direction"),
        "traffic_state": log_entry.get("traffic_state"),
        "incidents": incidents,
        "notes": log_entry.get("notes"),
        "overall_confidence": log_entry.get("overall_confidence"),
        "image_path": log_entry.get("image_path"),
        "vlm_model": log_entry.get("vlm_model"),
    }
    INCIDENTS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INCIDENTS_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _parse_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _to_hour_bucket(log_entry):
    captured = _parse_datetime(log_entry.get("captured_at"))
    created = _parse_datetime(log_entry.get("created_at"))
    value = captured or created
    if not value:
        return None
    hour = value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return hour.isoformat().replace("+00:00", "Z")


def _build_hourly_summary(log_entry, incidents):
    created_at = log_entry.get("created_at") or "unknown time"
    camera_name = log_entry.get("camera_name") or log_entry.get("camera_id") or "unknown camera"
    notes = (log_entry.get("notes") or "").strip()
    error = sanitize_error_message(log_entry.get("error"))
    skipped_reason = sanitize_error_message(log_entry.get("skipped_reason"))
    traffic_state = (log_entry.get("traffic_state") or "unknown").replace("_", " ")
    if error:
        return (
            f"Hourly heartbeat for {camera_name} at {created_at} recorded an error while polling or analyzing this "
            f"camera: {error}. The system remained active, but this interval should be reviewed for pipeline health."
        )
    if incidents:
        incident_types = []
        for incident in incidents:
            kind = (incident.get("type") or "incident").replace("_", " ")
            incident_types.append(kind)
        label = ", ".join(incident_types)
        if notes:
            return (
                f"Hourly heartbeat captured active incident conditions for {camera_name} with traffic state "
                f"{traffic_state}: {notes}. Incident types observed in this frame include {label}."
            )
        return (
            f"Hourly heartbeat captured active incident conditions for {camera_name} with traffic state "
            f"{traffic_state}. Incident types observed in this frame include {label}."
        )
    if notes:
        return (
            f"Hourly heartbeat confirms camera coverage for {camera_name} with traffic state {traffic_state}. "
            f"Summary: {notes}"
        )
    if skipped_reason:
        return (
            f"Hourly heartbeat captured a frame for {camera_name} but detailed VLM analysis was skipped for this "
            f"interval due to {skipped_reason}; this still confirms the ingest pipeline was active."
        )
    return (
        f"Hourly heartbeat confirms {camera_name} was reachable and a frame was stored for this interval; "
        "the pipeline appears operational for this camera."
    )


def _archive_incident_events(log_entry):
    base_notes = (log_entry.get("notes") or "").strip()
    incidents = _filter_valid_incidents(
        _parse_incidents(log_entry.get("incidents_json")),
        base_notes=base_notes,
    )
    if not incidents:
        return
    with _connect() as conn:
        for incident in incidents:
            if isinstance(incident, dict):
                incident_type = incident.get("type")
                severity = incident.get("severity")
                description = incident.get("description")
            else:
                incident_type = "incident"
                severity = "low"
                description = str(incident)
            event_notes = base_notes
            if not event_notes:
                kind = (incident_type or "incident").replace("_", " ")
                level = severity or "low"
                details = description or "No detailed summary was provided by the model."
                event_notes = f"{kind} ({level}): {details}"
            conn.execute(
                """
                INSERT INTO incident_events (
                    created_at,
                    captured_at,
                    camera_id,
                    camera_name,
                    corridor,
                    direction,
                    observed_direction,
                    traffic_state,
                    incident_type,
                    severity,
                    description,
                    notes,
                    overall_confidence,
                    image_path,
                    vlm_model,
                    clip_path,
                    annotated_image_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log_entry.get("created_at"),
                    log_entry.get("captured_at"),
                    log_entry.get("camera_id"),
                    log_entry.get("camera_name"),
                    log_entry.get("corridor"),
                    log_entry.get("direction"),
                    log_entry.get("observed_direction"),
                    log_entry.get("traffic_state"),
                    incident_type,
                    severity,
                    description,
                    event_notes,
                    log_entry.get("overall_confidence"),
                    log_entry.get("image_path"),
                    log_entry.get("vlm_model"),
                    log_entry.get("clip_path"),
                    log_entry.get("annotated_image_path"),
                ),
            )


def _archive_hourly_snapshot(log_entry):
    image_path = log_entry.get("image_path")
    camera_id = log_entry.get("camera_id")
    captured_at = log_entry.get("captured_at")
    if not image_path or not camera_id or not captured_at:
        return
    hour_bucket = _to_hour_bucket(log_entry)
    if not hour_bucket:
        return
    incidents = _filter_valid_incidents(
        _parse_incidents(log_entry.get("incidents_json")),
        base_notes=(log_entry.get("notes") or "").strip(),
    )
    error = sanitize_error_message(log_entry.get("error"))
    skipped_reason = sanitize_error_message(log_entry.get("skipped_reason"))
    if error:
        status = "error"
    elif incidents:
        status = "incident"
    elif skipped_reason:
        status = "skipped"
    elif log_entry.get("traffic_state"):
        status = "healthy"
    else:
        status = "unknown"
    summary = _build_hourly_summary(log_entry, incidents)
    inserted = False
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO hourly_snapshots (
                camera_id,
                camera_name,
                corridor,
                direction,
                hour_bucket,
                created_at,
                captured_at,
                image_path,
                frame_hash,
                traffic_state,
                incident_count,
                status,
                summary,
                error,
                skipped_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(camera_id, hour_bucket) DO NOTHING
            """,
            (
                camera_id,
                log_entry.get("camera_name"),
                log_entry.get("corridor"),
                log_entry.get("direction"),
                hour_bucket,
                log_entry.get("created_at"),
                log_entry.get("captured_at"),
                image_path,
                log_entry.get("frame_hash"),
                log_entry.get("traffic_state"),
                len(incidents),
                status,
                summary,
                error,
                skipped_reason,
            ),
        )
        inserted = cursor.rowcount == 1
    if inserted:
        _archive_hourly_incident_reports(log_entry, hour_bucket, incidents)


def _archive_hourly_incident_reports(log_entry, hour_bucket, incidents):
    base_payload = (
        log_entry.get("camera_id"),
        hour_bucket,
        log_entry.get("created_at"),
        log_entry.get("captured_at"),
        log_entry.get("image_path"),
        log_entry.get("traffic_state"),
        log_entry.get("notes"),
        log_entry.get("overall_confidence"),
    )
    rows = []
    if incidents:
        for incident in incidents:
            incident_type = "incident"
            severity = "unknown"
            description = None
            if isinstance(incident, dict):
                incident_type = incident.get("type") or "incident"
                severity = incident.get("severity") or "unknown"
                description = incident.get("description")
            else:
                description = str(incident)
            rows.append(
                (
                    *base_payload[:6],
                    "incident",
                    incident_type,
                    severity,
                    description,
                    *base_payload[6:],
                )
            )
    else:
        rows.append(
            (
                *base_payload[:6],
                "no_incident",
                "none",
                "none",
                "No incident detected in the saved hourly snapshot for this camera.",
                *base_payload[6:],
            )
        )
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO hourly_incident_reports (
                camera_id,
                hour_bucket,
                created_at,
                captured_at,
                image_path,
                traffic_state,
                report_kind,
                incident_type,
                severity,
                description,
                notes,
                overall_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def clear_vlm_logs(camera_id=None):
    with _connect() as conn:
        if camera_id:
            cursor = conn.execute(
                "DELETE FROM vlm_logs WHERE camera_id = ?", (camera_id,)
            )
        else:
            cursor = conn.execute("DELETE FROM vlm_logs")
        return cursor.rowcount


def toggle_false_alarm(incident_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, false_alarm FROM incident_events WHERE id = ?", (incident_id,)
        ).fetchone()
        if not row:
            return None
        new_value = 0 if row[1] else 1
        conn.execute(
            "UPDATE incident_events SET false_alarm = ? WHERE id = ?",
            (new_value, incident_id),
        )
    return {"id": incident_id, "false_alarm": new_value}


def get_false_alarm_summary(camera_id=None, days=7, limit=10):
    """Return recent false alarm patterns grouped by camera + incident type."""
    with _connect() as conn:
        where = "WHERE false_alarm = 1"
        params = []
        if camera_id:
            where += " AND camera_id = ?"
            params.append(camera_id)
        where += " AND created_at >= datetime('now', ?)"
        params.append(f"-{days} days")
        rows = conn.execute(
            f"""
            SELECT camera_id, incident_type, COUNT(*) as cnt, description
            FROM incident_events
            {where}
            GROUP BY camera_id, incident_type
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    return [
        {
            "camera_id": row[0],
            "incident_type": row[1],
            "count": row[2],
            "example_description": row[3],
        }
        for row in rows
    ]


def clear_incidents(camera_id=None):
    with _connect() as conn:
        if camera_id:
            cursor = conn.execute(
                "DELETE FROM incident_events WHERE camera_id = ?", (camera_id,)
            )
        else:
            cursor = conn.execute("DELETE FROM incident_events")
        return cursor.rowcount


def clear_false_alarms(camera_id=None):
    with _connect() as conn:
        if camera_id:
            cursor = conn.execute(
                "DELETE FROM incident_events WHERE camera_id = ? AND false_alarm = 1",
                (camera_id,),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM incident_events WHERE false_alarm = 1"
            )
        return cursor.rowcount


def clear_hourly(camera_id=None):
    with _connect() as conn:
        if camera_id:
            conn.execute(
                "DELETE FROM hourly_incident_reports WHERE camera_id = ?", (camera_id,)
            )
            cursor = conn.execute(
                "DELETE FROM hourly_snapshots WHERE camera_id = ?", (camera_id,)
            )
        else:
            conn.execute("DELETE FROM hourly_incident_reports")
            cursor = conn.execute("DELETE FROM hourly_snapshots")
        return cursor.rowcount


def get_debug_stats(camera_id=None, hours=1):
    cutoff = (
        datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=hours)
    ).isoformat()
    where = "WHERE created_at >= ?"
    params = [cutoff]
    if camera_id:
        where += " AND camera_id = ?"
        params.append(camera_id)

    with _connect() as conn:
        conn.row_factory = sqlite3.Row

        # Motion score stats
        motion_row = conn.execute(
            f"SELECT AVG(motion_score) as avg, MIN(motion_score) as min, "
            f"MAX(motion_score) as max, COUNT(motion_score) as cnt "
            f"FROM vlm_logs {where} AND motion_score IS NOT NULL",
            params,
        ).fetchone()
        motion_stats = {
            "avg": motion_row["avg"],
            "min": motion_row["min"],
            "max": motion_row["max"],
            "count": motion_row["cnt"],
        }

        # Raw motion scores for histogram
        motion_scores = [
            r[0]
            for r in conn.execute(
                f"SELECT motion_score FROM vlm_logs {where} AND motion_score IS NOT NULL "
                f"ORDER BY created_at DESC LIMIT 500",
                params,
            ).fetchall()
        ]

        # VLM call reason breakdown
        vlm_reasons = {
            r[0] or "null": r[1]
            for r in conn.execute(
                f"SELECT vlm_call_reason, COUNT(*) FROM vlm_logs {where} GROUP BY vlm_call_reason",
                params,
            ).fetchall()
        }

        # Source type distribution
        source_types = {
            r[0] or "null": r[1]
            for r in conn.execute(
                f"SELECT source_type, COUNT(*) FROM vlm_logs {where} GROUP BY source_type",
                params,
            ).fetchall()
        }

        # Error/skip reason breakdown
        error_reasons = {
            sanitize_error_message(r[0]) or "null": r[1]
            for r in conn.execute(
                f"SELECT error, COUNT(*) FROM vlm_logs {where} AND error IS NOT NULL GROUP BY error",
                params,
            ).fetchall()
        }
        skip_reasons = {
            sanitize_error_message(r[0]) or "null": r[1]
            for r in conn.execute(
                f"SELECT skipped_reason, COUNT(*) FROM vlm_logs {where} AND skipped_reason IS NOT NULL GROUP BY skipped_reason",
                params,
            ).fetchall()
        }

        # Anomaly detection count
        anomaly_count = conn.execute(
            f"SELECT COUNT(*) FROM vlm_logs {where} AND anomaly_detected = 1",
            params,
        ).fetchone()[0]

        # Vehicle count stats
        vehicle_row = conn.execute(
            f"SELECT AVG(vehicle_count) as avg, MIN(vehicle_count) as min, "
            f"MAX(vehicle_count) as max, COUNT(vehicle_count) as cnt "
            f"FROM vlm_logs {where} AND vehicle_count IS NOT NULL",
            params,
        ).fetchone()
        vehicle_stats = {
            "avg": vehicle_row["avg"],
            "min": vehicle_row["min"],
            "max": vehicle_row["max"],
            "count": vehicle_row["cnt"],
        }

        # Per-camera motion averages
        camera_motion = {
            r[0]: round(r[1], 6) if r[1] is not None else None
            for r in conn.execute(
                f"SELECT camera_id, AVG(motion_score) FROM vlm_logs {where} AND motion_score IS NOT NULL GROUP BY camera_id",
                params,
            ).fetchall()
        }

        # Traffic state distribution
        traffic_states = {
            r[0] or "null": r[1]
            for r in conn.execute(
                f"SELECT traffic_state, COUNT(*) FROM vlm_logs {where} GROUP BY traffic_state",
                params,
            ).fetchall()
        }

        # Hourly VLM call trend (24h buckets)
        hourly_trend = [
            {"hour": r[0], "count": r[1]}
            for r in conn.execute(
                f"SELECT substr(created_at, 1, 13) as hour_bucket, COUNT(*) "
                f"FROM vlm_logs {where} GROUP BY hour_bucket ORDER BY hour_bucket",
                params,
            ).fetchall()
        ]

        # Total log count in window
        total_logs = conn.execute(
            f"SELECT COUNT(*) FROM vlm_logs {where}", params
        ).fetchone()[0]

        # Recent 50 log entries with debug fields
        recent_rows = conn.execute(
            f"SELECT id, created_at, camera_id, camera_name, traffic_state, "
            f"motion_score, anomaly_detected, anomaly_reason, vlm_call_reason, "
            f"source_type, error, skipped_reason, vehicle_count "
            f"FROM vlm_logs {where} ORDER BY created_at DESC LIMIT 50",
            params,
        ).fetchall()
        recent_logs = [
            {
                "id": r[0],
                "created_at": r[1],
                "camera_id": r[2],
                "camera_name": r[3],
                "traffic_state": r[4],
                "motion_score": r[5],
                "anomaly_detected": r[6],
                "anomaly_reason": r[7],
                "vlm_call_reason": r[8],
                "source_type": r[9],
                "error": sanitize_error_message(r[10]),
                "skipped_reason": sanitize_error_message(r[11]),
                "vehicle_count": r[12],
            }
            for r in recent_rows
        ]

    return {
        "motion_stats": motion_stats,
        "motion_scores": motion_scores,
        "vlm_reasons": vlm_reasons,
        "source_types": source_types,
        "error_reasons": error_reasons,
        "skip_reasons": skip_reasons,
        "anomaly_count": anomaly_count,
        "camera_motion": camera_motion,
        "traffic_states": traffic_states,
        "hourly_trend": hourly_trend,
        "total_logs": total_logs,
        "recent_logs": recent_logs,
        "vehicle_stats": vehicle_stats,
    }


def list_logs(limit=100, camera_id=None):
    query = (
        "SELECT id, created_at, captured_at, camera_id, camera_name, corridor, "
        "direction, observed_direction, traffic_state, incidents_json, notes, "
        "overall_confidence, image_path, vlm_model, raw_response, error, skipped_reason, "
        "frame_hash, last_seen_at, last_processed_at "
        "FROM vlm_logs"
    )
    params = []
    if camera_id:
        query += " WHERE camera_id = ?"
        params.append(camera_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    results = []
    for row in rows:
        incidents = []
        if row[9]:
            try:
                incidents = json.loads(row[9])
            except json.JSONDecodeError:
                incidents = []
        error = sanitize_error_message(row[15])
        skipped_reason = sanitize_error_message(row[16])
        results.append(
            {
                "id": row[0],
                "created_at": row[1],
                "captured_at": row[2],
                "camera_id": row[3],
                "camera_name": row[4],
                "corridor": row[5],
                "direction": row[6],
                "observed_direction": row[7],
                "traffic_state": row[8],
                "incidents": incidents,
                "notes": row[10],
                "overall_confidence": row[11],
                "image_path": row[12],
                "vlm_model": row[13],
                "raw_response": row[14],
                "error": error,
                "skipped_reason": skipped_reason,
                "frame_hash": row[17],
                "last_seen_at": row[18],
                "last_processed_at": row[19],
            }
        )
    return results


def list_latest_log(camera_id=None):
    query = (
        "SELECT id, created_at, captured_at, camera_id, camera_name, corridor, "
        "direction, observed_direction, traffic_state, incidents_json, notes, "
        "overall_confidence, image_path, vlm_model, raw_response, error, skipped_reason, "
        "frame_hash, last_seen_at, last_processed_at "
        "FROM vlm_logs"
    )
    params = []
    if camera_id:
        query += " WHERE camera_id = ?"
        params.append(camera_id)
    query += " ORDER BY created_at DESC LIMIT 1"
    with _connect() as conn:
        row = conn.execute(query, params).fetchone()
    if not row:
        return None
    incidents = []
    if row[9]:
        try:
            incidents = json.loads(row[9])
        except json.JSONDecodeError:
            incidents = []
    error = sanitize_error_message(row[15])
    skipped_reason = sanitize_error_message(row[16])
    return {
        "id": row[0],
        "created_at": row[1],
        "captured_at": row[2],
        "camera_id": row[3],
        "camera_name": row[4],
        "corridor": row[5],
        "direction": row[6],
        "observed_direction": row[7],
        "traffic_state": row[8],
        "incidents": incidents,
        "notes": row[10],
        "overall_confidence": row[11],
        "image_path": row[12],
        "vlm_model": row[13],
        "raw_response": row[14],
        "error": error,
        "skipped_reason": skipped_reason,
        "frame_hash": row[17],
        "last_seen_at": row[18],
        "last_processed_at": row[19],
    }


def get_status_summary(cameras=None):
    cameras = cameras or list_cameras()
    with _connect() as conn:
        latest_rows = conn.execute(
            """
            SELECT l.camera_id, l.created_at, l.captured_at, l.traffic_state,
                   l.incidents_json, l.overall_confidence, l.error, l.skipped_reason,
                   l.observed_direction, l.notes, l.image_path, l.frame_hash,
                   l.last_seen_at, l.last_processed_at
            FROM vlm_logs l
            INNER JOIN (
                SELECT camera_id, MAX(created_at) AS max_created
                FROM vlm_logs
                GROUP BY camera_id
            ) latest
            ON l.camera_id = latest.camera_id AND l.created_at = latest.max_created
            """
        ).fetchall()
        analysis_rows = conn.execute(
            """
            SELECT l.camera_id, l.created_at, l.captured_at, l.traffic_state,
                   l.incidents_json, l.overall_confidence, l.error, l.skipped_reason,
                   l.observed_direction, l.notes, l.image_path, l.frame_hash,
                   l.last_seen_at, l.last_processed_at
            FROM vlm_logs l
            INNER JOIN (
                SELECT camera_id, MAX(created_at) AS max_created
                FROM vlm_logs
                WHERE traffic_state IS NOT NULL
                GROUP BY camera_id
            ) latest
            ON l.camera_id = latest.camera_id AND l.created_at = latest.max_created
            """
        ).fetchall()

    def _row_to_log(row):
        incidents = []
        if row[4]:
            try:
                incidents = json.loads(row[4])
            except json.JSONDecodeError:
                incidents = []
        error = sanitize_error_message(row[6])
        skipped_reason = sanitize_error_message(row[7])
        return {
            "created_at": row[1],
            "captured_at": row[2],
            "traffic_state": row[3],
            "incidents": incidents,
            "overall_confidence": row[5],
            "error": error,
            "skipped_reason": skipped_reason,
            "observed_direction": row[8],
            "notes": row[9],
            "image_path": row[10],
            "frame_hash": row[11],
            "last_seen_at": row[12],
            "last_processed_at": row[13],
        }

    latest_by_camera = {row[0]: _row_to_log(row) for row in latest_rows}
    analysis_by_camera = {row[0]: _row_to_log(row) for row in analysis_rows}
    summary = []
    for camera in cameras:
        camera_id = camera.get("camera_id")
        latest = latest_by_camera.get(camera_id)
        analysis = analysis_by_camera.get(camera_id)
        summary.append(
            {
                "camera_id": camera_id,
                "name": camera.get("name"),
                "corridor": camera.get("corridor"),
                "direction": camera.get("direction"),
                "latest_log": latest,
                "analysis_log": analysis,
            }
        )
    return summary


def list_incident_events(limit=200, camera_id=None, include_false_alarms=False):
    query = (
        "SELECT id, created_at, captured_at, camera_id, camera_name, corridor, direction, "
        "observed_direction, traffic_state, incident_type, severity, description, notes, "
        "overall_confidence, image_path, vlm_model, clip_path, false_alarm, annotated_image_path "
        "FROM incident_events"
    )
    params = []
    where = []
    if camera_id:
        where.append("camera_id = ?")
        params.append(camera_id)
    if not include_false_alarms:
        where.append("false_alarm = 0")
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [
        {
            "id": row[0],
            "created_at": row[1],
            "captured_at": row[2],
            "camera_id": row[3],
            "camera_name": row[4],
            "corridor": row[5],
            "direction": row[6],
            "observed_direction": row[7],
            "traffic_state": row[8],
            "incident_type": row[9],
            "severity": row[10],
            "description": row[11],
            "notes": row[12],
            "overall_confidence": row[13],
            "image_path": row[14],
            "vlm_model": row[15],
            "clip_path": row[16],
            "false_alarm": row[17],
            "annotated_image_path": row[18],
        }
        for row in rows
    ]


def list_hourly_snapshots(limit=336, camera_id=None):
    query = (
        "SELECT id, camera_id, camera_name, corridor, direction, hour_bucket, created_at, captured_at, "
        "image_path, frame_hash, traffic_state, incident_count, status, summary, error, skipped_reason "
        "FROM hourly_snapshots"
    )
    params = []
    if camera_id:
        query += " WHERE camera_id = ?"
        params.append(camera_id)
    query += " ORDER BY hour_bucket DESC, id DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
        report_params = []
        report_query = (
            "SELECT camera_id, hour_bucket, report_kind, incident_type, severity, description, "
            "notes, overall_confidence, created_at, captured_at, image_path, traffic_state "
            "FROM hourly_incident_reports"
        )
        if camera_id:
            report_query += " WHERE camera_id = ?"
            report_params.append(camera_id)
        report_query += " ORDER BY created_at DESC, id DESC"
        report_rows = conn.execute(report_query, report_params).fetchall()
    reports_by_bucket = {}
    for row in report_rows:
        key = (row[0], row[1])
        reports_by_bucket.setdefault(key, []).append(
            {
                "camera_id": row[0],
                "hour_bucket": row[1],
                "report_kind": row[2],
                "incident_type": row[3],
                "severity": row[4],
                "description": row[5],
                "notes": row[6],
                "overall_confidence": row[7],
                "created_at": row[8],
                "captured_at": row[9],
                "image_path": row[10],
                "traffic_state": row[11],
            }
        )
    results = []
    for row in rows:
        key = (row[1], row[5])
        results.append(
            {
                "id": row[0],
                "camera_id": row[1],
                "camera_name": row[2],
                "corridor": row[3],
                "direction": row[4],
                "hour_bucket": row[5],
                "created_at": row[6],
                "captured_at": row[7],
                "image_path": row[8],
                "frame_hash": row[9],
                "traffic_state": row[10],
                "incident_count": row[11],
                "status": row[12],
                "summary": row[13],
                "error": sanitize_error_message(row[14]),
                "skipped_reason": sanitize_error_message(row[15]),
                "incident_reports": reports_by_bucket.get(key, []),
            }
        )
    return results


def get_archive_overview(camera_id=None, include_false_alarms=False):
    incident_clauses = []
    incident_params = []
    if camera_id:
        incident_clauses.append("camera_id = ?")
        incident_params.append(camera_id)
    if not include_false_alarms:
        incident_clauses.append("false_alarm = 0")
    incidents_where = (
        " WHERE " + " AND ".join(incident_clauses) if incident_clauses else ""
    )
    hourly_where = " WHERE camera_id = ?" if camera_id else ""
    hourly_params = [camera_id] if camera_id else []
    with _connect() as conn:
        incident_total = conn.execute(
            f"SELECT COUNT(*) FROM incident_events{incidents_where}",
            incident_params,
        ).fetchone()[0]
        hourly_total = conn.execute(
            f"SELECT COUNT(*) FROM hourly_snapshots{hourly_where}",
            hourly_params,
        ).fetchone()[0]
        latest_incident_at = conn.execute(
            f"SELECT MAX(created_at) FROM incident_events{incidents_where}",
            incident_params,
        ).fetchone()[0]
        latest_hourly_bucket = conn.execute(
            f"SELECT MAX(hour_bucket) FROM hourly_snapshots{hourly_where}",
            hourly_params,
        ).fetchone()[0]
    return {
        "camera_id": camera_id,
        "incident_total": incident_total or 0,
        "hourly_total": hourly_total or 0,
        "latest_incident_at": latest_incident_at,
        "latest_hour_bucket": latest_hourly_bucket,
    }

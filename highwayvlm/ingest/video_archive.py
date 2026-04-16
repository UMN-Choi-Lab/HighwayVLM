"""Background HLS video archive writer for manual incident review."""

from __future__ import annotations

import json
import re
import subprocess
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from highwayvlm.settings import (
    get_hls_timeout_seconds,
    get_system_interval_seconds,
    get_video_archive_align_to_hour,
    get_video_archive_camera_ids,
    get_video_archive_duration_seconds,
    get_video_archive_enabled,
    get_video_archive_max_workers,
    get_video_archive_root,
    get_video_archive_timezone,
)

_ARCHIVE_LOCK = threading.Lock()
_ARCHIVE_EXECUTOR: ThreadPoolExecutor | None = None
_ACTIVE_RECORDINGS: dict[str, Future] = {}
_SCHEDULED_SLOTS: dict[str, str] = {}
_TIMEZONE_OBJ = None


def _aligned_start_window_seconds() -> int:
    # Keep this window wide enough to absorb scheduler jitter around HH:00.
    return max(60, get_system_interval_seconds() * 4)


def _slugify(value: str | None, fallback: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return fallback
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or fallback


def _parse_captured_at(captured_at: str | None) -> datetime:
    if captured_at:
        try:
            return datetime.strptime(captured_at, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _resolve_timezone():
    global _TIMEZONE_OBJ
    if _TIMEZONE_OBJ is not None:
        return _TIMEZONE_OBJ
    tz_name = get_video_archive_timezone()
    try:
        _TIMEZONE_OBJ = ZoneInfo(tz_name)
        return _TIMEZONE_OBJ
    except Exception:
        if tz_name == "America/Chicago":
            try:
                _TIMEZONE_OBJ = ZoneInfo("US/Central")
                return _TIMEZONE_OBJ
            except Exception:
                print(
                    "Unable to load IANA timezone 'America/Chicago'; "
                    "falling back to fixed CST (-06:00)."
                )
                _TIMEZONE_OBJ = timezone(timedelta(hours=-6), name="CST")
                return _TIMEZONE_OBJ
        print(f"Invalid VIDEO_ARCHIVE_TIMEZONE='{tz_name}', falling back to UTC")
        _TIMEZONE_OBJ = timezone.utc
        return _TIMEZONE_OBJ


def _build_segment_plan(captured_at: str | None) -> dict:
    now_utc = _parse_captured_at(captured_at)
    tz = _resolve_timezone()
    timezone_name = getattr(tz, "key", str(tz))
    now_local = now_utc.astimezone(tz)
    align_to_hour = get_video_archive_align_to_hour()
    configured_duration = max(5, get_video_archive_duration_seconds())

    if align_to_hour:
        slot_start_local = now_local.replace(minute=0, second=0, microsecond=0)
        slot_end_local = slot_start_local + timedelta(seconds=configured_duration)
        slot_start_utc = slot_start_local.astimezone(timezone.utc)
        slot_end_utc = slot_end_local.astimezone(timezone.utc)
        duration_seconds = configured_duration
        slot_id = slot_start_local.strftime("%Y%m%dT%H00")
        slot_label = (
            f"{slot_start_local.strftime('%Y-%m-%d %H:%M')} to "
            f"{slot_end_local.strftime('%H:%M')} {slot_start_local.tzname() or timezone_name}"
        )
    else:
        duration_seconds = configured_duration
        slot_start_utc = now_utc
        slot_end_utc = now_utc + timedelta(seconds=duration_seconds)
        slot_start_local = slot_start_utc.astimezone(tz)
        slot_end_local = slot_end_utc.astimezone(tz)
        slot_id = slot_start_utc.strftime("%Y%m%dT%H%M%SZ")
        slot_label = f"rolling_{duration_seconds}s"

    return {
        "slot_id": slot_id,
        "slot_start_utc": slot_start_utc,
        "slot_end_utc": slot_end_utc,
        "slot_start_local": slot_start_local,
        "slot_end_local": slot_end_local,
        "duration_seconds": duration_seconds,
        "timezone": timezone_name,
        "slot_label": slot_label,
        "align_to_hour": align_to_hour,
    }


def _get_executor() -> ThreadPoolExecutor:
    global _ARCHIVE_EXECUTOR
    if _ARCHIVE_EXECUTOR is None:
        _ARCHIVE_EXECUTOR = ThreadPoolExecutor(
            max_workers=max(1, get_video_archive_max_workers()),
            thread_name_prefix="video-archive",
        )
    return _ARCHIVE_EXECUTOR


def _is_camera_enabled(camera_id: str) -> bool:
    configured = get_video_archive_camera_ids()
    if not configured:
        return True
    return camera_id in configured


def _archive_paths(
    camera: dict,
    captured_at: str | None,
    segment_plan: dict,
) -> tuple[Path, Path, dict]:
    root = get_video_archive_root()
    slot_start_utc = segment_plan["slot_start_utc"]
    slot_start_local = segment_plan["slot_start_local"]
    slot_end_local = segment_plan["slot_end_local"]
    date_str = slot_start_local.strftime("%Y-%m-%d")
    ts_str = slot_start_utc.strftime("%Y%m%dT%H%M%SZ")
    tz_label = _slugify(slot_start_local.tzname() or segment_plan["timezone"], "tz")

    camera_id = str(camera.get("camera_id") or "unknown")
    corridor = _slugify(str(camera.get("corridor") or ""), "corridor")
    direction = _slugify(str(camera.get("direction") or ""), "unknown")
    location = _slugify(str(camera.get("name") or ""), "camera")
    start_hm = slot_start_local.strftime("%H%M")
    end_hm = slot_end_local.strftime("%H%M")

    parent = root / date_str / corridor / direction / camera_id
    filename = (
        f"{ts_str}_{camera_id}_{corridor}_{direction}_{location}"
        f"_{start_hm}_{end_hm}_{tz_label}.mp4"
    )
    video_path = parent / filename
    metadata_path = video_path.with_suffix(".json")

    metadata = {
        "camera_id": camera_id,
        "camera_name": camera.get("name"),
        "corridor": camera.get("corridor"),
        "direction": camera.get("direction"),
        "captured_at": captured_at,
        "recording_started_at": _parse_captured_at(captured_at).isoformat(),
        "recording_date": date_str,
        "recording_time_utc": ts_str,
        "slot_id": segment_plan["slot_id"],
        "slot_label": segment_plan["slot_label"],
        "slot_start_utc": segment_plan["slot_start_utc"].isoformat(),
        "slot_end_utc": segment_plan["slot_end_utc"].isoformat(),
        "slot_start_local": segment_plan["slot_start_local"].isoformat(),
        "slot_end_local": segment_plan["slot_end_local"].isoformat(),
        "timezone": segment_plan["timezone"],
        "align_to_hour": segment_plan["align_to_hour"],
        "location_slug": location,
        "video_path": str(video_path),
    }
    return video_path, metadata_path, metadata


def _cleanup_output(destination: Path) -> None:
    try:
        if destination.exists():
            destination.unlink()
    except Exception:
        pass


def _run_command(command: list[str], timeout_seconds: int) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        return False, str(exc)
    except subprocess.TimeoutExpired:
        return False, f"command_timeout_after_{timeout_seconds}s"
    except Exception as exc:
        return False, str(exc)

    if result.returncode == 0:
        return True, ""
    error_text = (result.stderr or result.stdout or f"exit_code_{result.returncode}").strip()
    return False, error_text[:400]


def _validate_output(destination: Path, duration_seconds: int) -> tuple[bool, str]:
    if not destination.exists():
        return False, "output_missing"
    if destination.stat().st_size < 1024:
        return False, "output_too_small"

    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name",
        "-show_entries",
        "format=duration,format_name",
        "-of",
        "json",
        str(destination),
    ]
    try:
        result = subprocess.run(
            probe_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        # Keep archive quality strict: ffprobe must be present for post-write validation.
        return False, "ffprobe_missing"
    except subprocess.TimeoutExpired:
        return False, "ffprobe_timeout"
    except Exception as exc:
        return False, f"ffprobe_exception:{exc}"

    if result.returncode != 0:
        error_text = (result.stderr or result.stdout or "ffprobe_failed").strip()
        return False, error_text[:200]

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False, "ffprobe_invalid_json"

    streams = payload.get("streams") or []
    if not streams:
        return False, "no_video_stream"
    video_codecs = [
        str(stream.get("codec_name") or "").lower()
        for stream in streams
        if str(stream.get("codec_type") or "").lower() == "video"
    ]
    audio_codecs = [
        str(stream.get("codec_name") or "").lower()
        for stream in streams
        if str(stream.get("codec_type") or "").lower() == "audio"
    ]
    if not video_codecs:
        return False, "no_video_stream"
    if "h264" not in video_codecs:
        return False, f"unsupported_video_codec:{','.join(video_codecs)}"
    if audio_codecs and "aac" not in audio_codecs:
        return False, f"unsupported_audio_codec:{','.join(audio_codecs)}"

    format_name = str((payload.get("format") or {}).get("format_name") or "").lower()
    if "mp4" not in format_name:
        return False, f"unsupported_container:{format_name or 'unknown'}"

    duration_raw = (payload.get("format") or {}).get("duration")
    try:
        actual_duration = float(duration_raw)
    except (TypeError, ValueError):
        return False, "duration_unavailable"

    min_expected = max(5.0, float(duration_seconds) * 0.95)
    if actual_duration < min_expected:
        return False, f"duration_too_short:{actual_duration:.2f}s"
    return True, ""


def _run_ffmpeg(stream_url: str, destination: Path, duration_seconds: int) -> tuple[bool, str]:
    timeout_seconds = max(
        duration_seconds + get_hls_timeout_seconds() + 120,
        int(duration_seconds * 4),
        600,
    )
    encode_cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-fflags",
        "+genpts",
        "-i",
        stream_url,
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-t",
        str(duration_seconds),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-sn",
        "-dn",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        "-shortest",
        str(destination),
    ]
    encode_ok, encode_error = _run_command(encode_cmd, timeout_seconds)
    if encode_ok:
        valid, validation_error = _validate_output(destination, duration_seconds)
        if valid:
            return True, ""
        encode_error = f"encode_invalid:{validation_error}"
        _cleanup_output(destination)
    else:
        _cleanup_output(destination)

    error_text = encode_error if encode_error else "unknown_ffmpeg_failure"
    return False, error_text[:400]


def _append_manifest(root: Path, payload: dict) -> None:
    manifest_path = root / "video_archive_manifest.jsonl"
    root.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _record_segment(
    camera: dict,
    stream_url: str,
    captured_at: str | None,
    segment_plan: dict,
) -> dict:
    video_path, metadata_path, metadata = _archive_paths(camera, captured_at, segment_plan)
    duration_seconds = segment_plan["duration_seconds"]

    video_path.parent.mkdir(parents=True, exist_ok=True)
    ok, error_text = _run_ffmpeg(stream_url, video_path, duration_seconds)
    if not ok:
        raise RuntimeError(
            f"video_archive_failed camera={camera.get('camera_id')} duration={duration_seconds}s error={error_text}"
        )

    metadata["duration_seconds"] = duration_seconds
    metadata["saved_at"] = datetime.now(timezone.utc).isoformat()
    metadata["stream_url"] = stream_url

    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    _append_manifest(get_video_archive_root(), metadata)
    return metadata


def _on_done(camera_id: str, slot_id: str, future: Future) -> None:
    failed = False
    with _ARCHIVE_LOCK:
        current = _ACTIVE_RECORDINGS.get(camera_id)
        if current is future:
            _ACTIVE_RECORDINGS.pop(camera_id, None)
    try:
        payload = future.result()
        print(
            f"Video archive saved for {camera_id}: {payload.get('video_path')} "
            f"(duration={payload.get('duration_seconds')}s)"
        )
    except Exception as exc:
        failed = True
        print(f"Video archive failed for {camera_id}: {exc}")
    finally:
        if failed:
            with _ARCHIVE_LOCK:
                if _SCHEDULED_SLOTS.get(camera_id) == slot_id:
                    _SCHEDULED_SLOTS.pop(camera_id, None)


def schedule_hls_video_archive(camera: dict, stream_url: str, captured_at: str | None) -> tuple[bool, str]:
    if not get_video_archive_enabled():
        return False, "disabled"
    camera_id = str(camera.get("camera_id") or "").strip()
    if not camera_id:
        return False, "missing_camera_id"
    if not _is_camera_enabled(camera_id):
        return False, "camera_not_enabled"
    segment_plan = _build_segment_plan(captured_at)
    if segment_plan["align_to_hour"]:
        now_local = _parse_captured_at(captured_at).astimezone(_resolve_timezone())
        slot_start_local = segment_plan["slot_start_local"]
        seconds_into_slot = (now_local - slot_start_local).total_seconds()
        if seconds_into_slot < 0 or seconds_into_slot > _aligned_start_window_seconds():
            return False, "waiting_for_hour_window"
    slot_id = segment_plan["slot_id"]

    with _ARCHIVE_LOCK:
        active = _ACTIVE_RECORDINGS.get(camera_id)
        if active is not None and not active.done():
            return False, "already_recording"
        if _SCHEDULED_SLOTS.get(camera_id) == slot_id:
            return False, "slot_already_scheduled"
        future = _get_executor().submit(
            _record_segment,
            camera,
            stream_url,
            captured_at,
            segment_plan,
        )
        _ACTIVE_RECORDINGS[camera_id] = future
        _SCHEDULED_SLOTS[camera_id] = slot_id
        future.add_done_callback(
            lambda f, cid=camera_id, sid=slot_id: _on_done(cid, sid, f)
        )
    return True, "scheduled"

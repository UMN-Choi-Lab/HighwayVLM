from dataclasses import dataclass
from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None
try:
    from dotenv import dotenv_values
except Exception:
    dotenv_values = None

if load_dotenv:
    # Load .env once at import for local/dev runs.
    load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
FRAMES_DIR = DATA_DIR / "frames"
LIVE_FRAMES_DIR = FRAMES_DIR / "live"
HOURLY_FRAMES_DIR = FRAMES_DIR / "hourly"
RAW_VLM_OUTPUT_DIR = DATA_DIR / "raw_vlm_outputs"
INCIDENT_CLIPS_DIR = FRAMES_DIR / "clips"
INCIDENT_REPORTS_DIR = DATA_DIR / "incident_reports"
LOGS_DIR = ROOT / "logs"
INCIDENTS_LOG_PATH = LOGS_DIR / "incidents.jsonl"
DEFAULT_DB_PATH = DATA_DIR / "highwayvlm.db"


@dataclass(frozen=True)
class PipelineRuntimeConfig:
    interval_seconds: int
    vlm_error_cooldown_seconds: int
    hls_enabled: bool
    hls_max_consecutive_failures: int
    hls_retry_backoff_seconds: int


def get_db_path():
    return Path(
        os.getenv(
            "SQLITE_DB_PATH",
            os.getenv("HIGHWAYVLM_DB_PATH", str(DEFAULT_DB_PATH)),
        )
    )


def get_camera_config_path():
    return Path(os.getenv("HIGHWAYVLM_CAMERA_CONFIG", str(CONFIG_DIR / "cameras.yaml")))


def get_system_interval_seconds():
    """
    Single source of truth for all app cadence.
    This drives both backend scan ticks and frontend auto-refresh timers.
    """
    return int(os.getenv("SYSTEM_INTERVAL_SECONDS", "30"))


def get_run_interval_seconds():
    # Legacy alias; keeps older code paths working while using centralized cadence.
    return get_system_interval_seconds()


def get_snapshot_interval_seconds():
    # Legacy alias; keeps older script loop behavior aligned to centralized cadence.
    return get_system_interval_seconds()


def get_vlm_interval_seconds():
    # Legacy alias; keeps older script loop behavior aligned to centralized cadence.
    return get_system_interval_seconds()


def get_dashboard_refresh_seconds():
    # Legacy alias; UI now reads SYSTEM_INTERVAL_SECONDS from runtime settings API.
    return get_system_interval_seconds()


def get_debug_refresh_seconds():
    # Legacy alias; UI now reads SYSTEM_INTERVAL_SECONDS from runtime settings API.
    return get_system_interval_seconds()


def get_min_vlm_interval_seconds():
    # Legacy alias retained for compatibility with legacy docs/debug terminology.
    return get_system_interval_seconds()


def get_request_timeout_seconds():
    return int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))


def get_vlm_timeout_seconds():
    return int(os.getenv("VLM_TIMEOUT_SECONDS", "30"))


def get_vlm_max_retries():
    return int(os.getenv("VLM_MAX_RETRIES", "3"))



def get_vlm_max_tokens():
    return int(os.getenv("VLM_MAX_TOKENS", "800"))


def get_vlm_max_calls_per_run():
    return int(os.getenv("VLM_MAX_CALLS_PER_RUN", "0"))


def get_vlm_error_cooldown_seconds():
    return int(os.getenv("VLM_ERROR_COOLDOWN_SECONDS", "10"))


def get_camera_metadata_url_template():
    return os.getenv("CAMERA_METADATA_URL_TEMPLATE")


def get_snapshot_url_template():
    return os.getenv("SNAPSHOT_URL_TEMPLATE")


def get_image_url_regex():
    return os.getenv("IMAGE_URL_REGEX")


def get_vlm_model():
    return os.getenv("VLM_MODEL", "gpt-4o-mini")


def get_vlm_api_key():
    if dotenv_values:
        env_path = ROOT / ".env"
        values = dotenv_values(env_path)
        if values.get("OPENAI_API_KEY"):
            return values["OPENAI_API_KEY"]
        if values.get("VLM_API_KEY"):
            return values["VLM_API_KEY"]
    return os.getenv("OPENAI_API_KEY") or os.getenv("VLM_API_KEY")


def get_hls_enabled():
    return os.getenv("HLS_ENABLED", "true").lower() in ("true", "1", "yes")


def get_hls_url_template():
    return os.getenv(
        "HLS_URL_TEMPLATE",
        "https://video.dot.state.mn.us/public/{camera_id}.stream/playlist.m3u8",
    )


def get_hls_num_frames():
    return int(os.getenv("HLS_NUM_FRAMES", "5"))


def get_hls_frame_interval():
    return float(os.getenv("HLS_FRAME_INTERVAL", "5.0"))


def get_hls_timeout_seconds():
    return int(os.getenv("HLS_TIMEOUT_SECONDS", "30"))


def get_hls_max_consecutive_failures():
    return int(os.getenv("HLS_MAX_CONSECUTIVE_FAILURES", "5"))


def get_hls_retry_backoff_seconds():
    # Reuse the same centralized cadence for HLS retry backoff.
    return int(os.getenv("HLS_RETRY_BACKOFF_SECONDS", str(get_system_interval_seconds())))


def get_motion_diff_threshold():
    return int(os.getenv("MOTION_DIFF_THRESHOLD", "30"))


def get_motion_high_threshold():
    return float(os.getenv("MOTION_HIGH_THRESHOLD", "0.05"))


def get_motion_low_threshold():
    return float(os.getenv("MOTION_LOW_THRESHOLD", "0.005"))


def get_periodic_vlm_interval_seconds():
    # Disabled in strict CV-first flow.
    return 0


def get_yolo_enabled():
    return os.getenv("YOLO_ENABLED", "true").lower() in ("true", "1", "yes")


def get_yolo_confidence():
    return float(os.getenv("YOLO_CONFIDENCE", "0.25"))


def get_yolo_vehicle_classes():
    raw = os.getenv("YOLO_VEHICLE_CLASSES", "2,3,5,7")
    return [int(c.strip()) for c in raw.split(",") if c.strip()]


def get_incident_confirm_cycles():
    return int(os.getenv("INCIDENT_CONFIRM_CYCLES", "2"))


def get_incident_high_confidence():
    return float(os.getenv("INCIDENT_HIGH_CONFIDENCE", "0.85"))


def get_incident_low_confidence():
    return float(os.getenv("INCIDENT_LOW_CONFIDENCE", "0.4"))


def get_vlm_base_url():
    if dotenv_values:
        env_path = ROOT / ".env"
        values = dotenv_values(env_path)
        if values.get("OPENAI_BASE_URL"):
            return values["OPENAI_BASE_URL"]
        if values.get("VLM_BASE_URL"):
            return values["VLM_BASE_URL"]
    return os.getenv("OPENAI_BASE_URL", os.getenv("VLM_BASE_URL", "https://api.openai.com/v1"))


def get_pipeline_runtime_config():
    return PipelineRuntimeConfig(
        interval_seconds=get_system_interval_seconds(),
        vlm_error_cooldown_seconds=get_vlm_error_cooldown_seconds(),
        hls_enabled=get_hls_enabled(),
        hls_max_consecutive_failures=get_hls_max_consecutive_failures(),
        hls_retry_backoff_seconds=get_hls_retry_backoff_seconds(),
    )


def get_runtime_settings_snapshot():
    runtime = get_pipeline_runtime_config()
    return {
        "SYSTEM_INTERVAL_SECONDS": runtime.interval_seconds,
        "VLM_ERROR_COOLDOWN_SECONDS": runtime.vlm_error_cooldown_seconds,
        "HLS_ENABLED": runtime.hls_enabled,
        "HLS_NUM_FRAMES": get_hls_num_frames(),
        "HLS_FRAME_INTERVAL": get_hls_frame_interval(),
        "HLS_TIMEOUT_SECONDS": get_hls_timeout_seconds(),
        "HLS_MAX_CONSECUTIVE_FAILURES": runtime.hls_max_consecutive_failures,
        "HLS_RETRY_BACKOFF_SECONDS": runtime.hls_retry_backoff_seconds,
        "MOTION_DIFF_THRESHOLD": get_motion_diff_threshold(),
        "MOTION_HIGH_THRESHOLD": get_motion_high_threshold(),
        "MOTION_LOW_THRESHOLD": get_motion_low_threshold(),
        "VLM_MODEL": get_vlm_model(),
    }

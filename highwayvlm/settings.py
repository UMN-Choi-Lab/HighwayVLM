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
INCIDENT_REPORTS_DIR = DATA_DIR / "incident_reports"
LOGS_DIR = ROOT / "logs"
INCIDENTS_LOG_PATH = LOGS_DIR / "incidents.jsonl"
DEFAULT_DB_PATH = DATA_DIR / "highwayvlm.db"


def get_db_path():
    return Path(
        os.getenv(
            "SQLITE_DB_PATH",
            os.getenv("HIGHWAYVLM_DB_PATH", str(DEFAULT_DB_PATH)),
        )
    )


def get_camera_config_path():
    return Path(os.getenv("HIGHWAYVLM_CAMERA_CONFIG", str(CONFIG_DIR / "cameras.yaml")))


def get_run_interval_seconds():
    return int(os.getenv("RUN_INTERVAL_SECONDS", "30"))


def get_snapshot_interval_seconds():
    return int(os.getenv("SNAPSHOT_INTERVAL_SECONDS", "60"))


def get_vlm_interval_seconds():
    return int(os.getenv("VLM_INTERVAL_SECONDS", "120"))


def get_min_vlm_interval_seconds():
    return int(
        os.getenv(
            "MIN_VLM_INTERVAL_SECONDS",
            os.getenv("VLM_FORCE_INTERVAL_SECONDS", "30"),
        )
    )


def get_request_timeout_seconds():
    return int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))


def get_vlm_timeout_seconds():
    return int(os.getenv("VLM_TIMEOUT_SECONDS", "30"))


def get_vlm_max_retries():
    return int(os.getenv("VLM_MAX_RETRIES", "3"))



def get_vlm_max_tokens():
    return int(os.getenv("VLM_MAX_TOKENS", "512"))


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


def get_vlm_base_url():
    if dotenv_values:
        env_path = ROOT / ".env"
        values = dotenv_values(env_path)
        if values.get("OPENAI_BASE_URL"):
            return values["OPENAI_BASE_URL"]
        if values.get("VLM_BASE_URL"):
            return values["VLM_BASE_URL"]
    return os.getenv("OPENAI_BASE_URL", os.getenv("VLM_BASE_URL", "https://api.openai.com/v1"))

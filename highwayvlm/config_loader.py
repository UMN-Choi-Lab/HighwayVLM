from pathlib import Path
import yaml

from highwayvlm.settings import get_camera_config_path


def _to_optional_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_cameras(config_path=None):
    path = Path(config_path) if config_path else get_camera_config_path()
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or []
    cameras = []
    for entry in payload:
        if not entry:
            continue
        cameras.append({
            "camera_id": str(entry.get("camera_id", "")).strip(),
            "name": str(entry.get("name", "")).strip(),
            "snapshot_url": str(entry.get("snapshot_url", "")).strip(),
            "source_url": str(entry.get("source_url", "")).strip(),
            "corridor": str(entry.get("corridor", "")).strip(),
            "direction": str(entry.get("direction", "")).strip(),
            "latitude": _to_optional_float(entry.get("latitude")),
            "longitude": _to_optional_float(entry.get("longitude")),
        })
    return cameras

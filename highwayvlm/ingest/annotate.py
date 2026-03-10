"""Draw incident bounding-box annotations on snapshot images (side-by-side)."""

import cv2
import numpy as np

from highwayvlm.settings import FRAMES_DIR

# Colors per severity (BGR)
_SEVERITY_COLORS = {
    "high": (0, 0, 255),      # red
    "medium": (0, 165, 255),   # orange
    "low": (0, 255, 255),      # yellow
}
_DEFAULT_COLOR = (0, 255, 255)


def _decode_image(image_bytes: bytes):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _draw_boxes(img, incidents: list[dict]) -> int:
    """Draw bbox rectangles + labels on an image in-place. Returns count drawn."""
    h, w = img.shape[:2]
    drawn = 0

    for incident in incidents:
        bbox = incident.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        x1, y1, x2, y2 = bbox
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)

        if px2 <= px1 or py2 <= py1:
            continue

        severity = (incident.get("severity") or "low").lower()
        color = _SEVERITY_COLORS.get(severity, _DEFAULT_COLOR)
        incident_type = (incident.get("type") or "incident").replace("_", " ").title()

        cv2.rectangle(img, (px1, py1), (px2, py2), color, 2)

        label = f"{incident_type} ({severity})"
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.5
        thickness = 1
        (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
        label_y = max(py1 - 6, th + 4)
        cv2.rectangle(img, (px1, label_y - th - 4), (px1 + tw + 6, label_y + 2), color, -1)
        cv2.putText(img, label, (px1 + 3, label_y - 2), font, scale, (0, 0, 0), thickness)

        drawn += 1

    return drawn


def _draw_frame_label(img, text: str):
    """Draw a translucent label bar at the top-left of the image."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.6
    thickness = 1
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    cv2.rectangle(img, (0, 0), (tw + 12, th + 12), (0, 0, 0), -1)
    cv2.putText(img, text, (6, th + 6), font, scale, (255, 255, 255), thickness)


def save_annotated_image(
    camera_id: str,
    captured_at: str,
    early_bytes: bytes,
    late_bytes: bytes,
    incidents: list[dict],
) -> str | None:
    """Create a side-by-side annotated image from two frames.

    Both frames get incident bboxes drawn on them so the user can compare
    vehicle positions between frames. Returns relative path for serving, or None.
    """
    img_early = _decode_image(early_bytes)
    img_late = _decode_image(late_bytes)
    if img_early is None or img_late is None:
        return None

    # Resize late frame to match early frame dimensions
    h, w = img_early.shape[:2]
    if img_late.shape[:2] != (h, w):
        img_late = cv2.resize(img_late, (w, h))

    drawn_early = _draw_boxes(img_early, incidents)
    drawn_late = _draw_boxes(img_late, incidents)

    if drawn_early == 0 and drawn_late == 0:
        return None

    _draw_frame_label(img_early, "EARLIER")
    _draw_frame_label(img_late, "LATER")

    # 2px white divider between frames
    divider = np.full((h, 2, 3), 255, dtype=np.uint8)
    composite = np.hstack([img_early, divider, img_late])

    out_dir = FRAMES_DIR / "annotated"
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{camera_id}_{captured_at}.jpg"
    full_path = out_dir / filename
    _, buf = cv2.imencode(".jpg", composite, [cv2.IMWRITE_JPEG_QUALITY, 92])
    full_path.write_bytes(buf.tobytes())
    return f"annotated/{filename}"

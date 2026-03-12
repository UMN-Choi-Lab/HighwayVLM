"""Save HLS captured frames as a browser-playable MP4 video clip (H.264)."""

import subprocess
import tempfile

import cv2
import numpy as np

from highwayvlm.settings import INCIDENT_CLIPS_DIR


def save_incident_clip(
    camera_id: str,
    captured_at: str,
    frames: list,
    fps: float = 2.0,
) -> str | None:
    """Encode a list of StreamFrame objects into an H.264 MP4 file.

    Uses ffmpeg for browser-compatible encoding.
    Returns the relative clip path (under frames/) for serving, or None on failure.
    """
    if not frames:
        return None

    INCIDENT_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{camera_id}_{captured_at}.mp4"
    full_path = INCIDENT_CLIPS_DIR / filename

    # Decode first frame to get dimensions
    first_arr = np.frombuffer(frames[0].image_bytes, dtype=np.uint8)
    first_img = cv2.imdecode(first_arr, cv2.IMREAD_COLOR)
    if first_img is None:
        return None

    height, width = first_img.shape[:2]

    # Write frames as raw video to a temp file, then encode with ffmpeg
    with tempfile.NamedTemporaryFile(suffix=".raw", delete=True) as tmp:
        tmp.write(first_img.tobytes())
        for frame in frames[1:]:
            arr = np.frombuffer(frame.image_bytes, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is not None:
                if img.shape[:2] != (height, width):
                    img = cv2.resize(img, (width, height))
                tmp.write(img.tobytes())
        tmp.flush()

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-pixel_format", "bgr24",
                "-video_size", f"{width}x{height}",
                "-framerate", str(fps),
                "-i", tmp.name,
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(full_path),
            ],
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            print(f"ffmpeg clip encode failed: {result.stderr.decode(errors='replace')[:200]}")
            return None

    return f"clips/{filename}"

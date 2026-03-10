import time
from dataclasses import dataclass, field

import cv2

from highwayvlm.settings import (
    get_hls_frame_interval,
    get_hls_num_frames,
    get_hls_timeout_seconds,
    get_hls_url_template,
)


@dataclass
class StreamFrame:
    image_bytes: bytes
    content_type: str
    timestamp_offset: float
    width: int
    height: int


@dataclass
class StreamCapture:
    camera_id: str
    stream_url: str
    frames: list[StreamFrame] = field(default_factory=list)
    error: str | None = None


def build_stream_url(camera_id: str) -> str:
    template = get_hls_url_template()
    return template.format(camera_id=camera_id)


def extract_frames(
    camera_id: str,
    stream_url: str,
    num_frames: int | None = None,
    frame_interval_seconds: float | None = None,
    timeout_seconds: int | None = None,
) -> StreamCapture:
    num_frames = num_frames if num_frames is not None else get_hls_num_frames()
    frame_interval_seconds = (
        frame_interval_seconds
        if frame_interval_seconds is not None
        else get_hls_frame_interval()
    )
    timeout_seconds = (
        timeout_seconds if timeout_seconds is not None else get_hls_timeout_seconds()
    )

    capture = StreamCapture(camera_id=camera_id, stream_url=stream_url)
    cap = None
    try:
        cap = cv2.VideoCapture(stream_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_seconds * 1000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_seconds * 1000)

        if not cap.isOpened():
            capture.error = f"Failed to open HLS stream: {stream_url}"
            return capture

        start_time = time.monotonic()
        deadline = start_time + timeout_seconds
        last_grab_time = 0.0

        while len(capture.frames) < num_frames:
            now = time.monotonic()
            if now >= deadline:
                if not capture.frames:
                    capture.error = "HLS stream timed out before capturing any frames"
                break

            # Wait for the interval between frames (skip for first frame)
            if capture.frames and (now - last_grab_time) < frame_interval_seconds:
                # Read and discard frames to keep the stream advancing
                cap.grab()
                time.sleep(0.05)
                continue

            ret, frame = cap.read()
            if not ret:
                if not capture.frames:
                    capture.error = "Failed to read frame from HLS stream"
                break

            last_grab_time = time.monotonic()
            offset = last_grab_time - start_time

            height, width = frame.shape[:2]
            success, encoded = cv2.imencode(".jpg", frame)
            if not success:
                continue

            capture.frames.append(
                StreamFrame(
                    image_bytes=encoded.tobytes(),
                    content_type="image/jpeg",
                    timestamp_offset=offset,
                    width=width,
                    height=height,
                )
            )
    except Exception as exc:
        capture.error = f"HLS extraction error: {exc}"
    finally:
        if cap is not None:
            cap.release()

    return capture

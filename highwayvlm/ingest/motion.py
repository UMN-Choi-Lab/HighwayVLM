from dataclasses import dataclass, field

import cv2
import numpy as np

from highwayvlm.settings import (
    get_motion_diff_threshold,
    get_motion_high_threshold,
    get_motion_low_threshold,
)


@dataclass
class MotionAnalysis:
    changed_pixel_fraction: float = 0.0
    traffic_state: str = "unknown"
    mean_brightness: float = 0.0
    is_nighttime: bool = False
    anomaly_detected: bool = False
    anomaly_reason: str | None = None
    contour_count: int = 0
    largest_contour_area: float = 0.0


def analyze_motion(
    frames: list[bytes],
    diff_threshold: int | None = None,
    high_threshold: float | None = None,
    low_threshold: float | None = None,
) -> MotionAnalysis:
    diff_threshold = diff_threshold if diff_threshold is not None else get_motion_diff_threshold()
    high_threshold = high_threshold if high_threshold is not None else get_motion_high_threshold()
    low_threshold = low_threshold if low_threshold is not None else get_motion_low_threshold()

    result = MotionAnalysis()

    if len(frames) < 2:
        return result

    # Decode frames
    decoded = []
    for frame_bytes in frames:
        arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is not None:
            decoded.append(img)

    if len(decoded) < 2:
        return result

    # Convert to grayscale
    grays = [cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) for img in decoded]

    # Compute mean brightness from first frame
    result.mean_brightness = float(np.mean(grays[0]))
    result.is_nighttime = result.mean_brightness < 40

    # Nighttime adaptation: increase threshold to reduce noise
    effective_threshold = 50 if result.is_nighttime else diff_threshold

    # Compute frame differences across consecutive pairs
    total_changed = 0.0
    total_contours = 0
    max_contour_area = 0.0
    pair_count = 0

    for i in range(len(grays) - 1):
        blurred_a = cv2.GaussianBlur(grays[i], (21, 21), 0)
        blurred_b = cv2.GaussianBlur(grays[i + 1], (21, 21), 0)

        diff = cv2.absdiff(blurred_a, blurred_b)
        _, thresh = cv2.threshold(diff, effective_threshold, 255, cv2.THRESH_BINARY)

        total_pixels = thresh.shape[0] * thresh.shape[1]
        changed_pixels = np.count_nonzero(thresh)
        total_changed += changed_pixels / total_pixels

        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        total_contours += len(contours)

        for contour in contours:
            area = cv2.contourArea(contour)
            if area > max_contour_area:
                max_contour_area = area

        pair_count += 1

    result.changed_pixel_fraction = total_changed / pair_count if pair_count > 0 else 0.0
    result.contour_count = total_contours
    result.largest_contour_area = max_contour_area

    # traffic_state is no longer derived from motion — vehicle detector handles it.
    # Keep changed_pixel_fraction for anomaly detection and VLM context.

    # Anomaly detection: large stationary contour in center band of image
    height, width = decoded[0].shape[:2]
    center_left = width // 4
    center_right = 3 * width // 4
    image_area = height * width

    # Check for large stationary objects in center band across all pairs
    for i in range(len(grays) - 1):
        blurred_a = cv2.GaussianBlur(grays[i], (21, 21), 0)
        blurred_b = cv2.GaussianBlur(grays[i + 1], (21, 21), 0)
        diff = cv2.absdiff(blurred_a, blurred_b)
        # Invert: find areas with NO motion (stationary objects)
        _, static_mask = cv2.threshold(diff, effective_threshold, 255, cv2.THRESH_BINARY_INV)
        # Mask to center band only
        static_center = static_mask[:, center_left:center_right]
        # Find large contours in the static center region
        contours, _ = cv2.findContours(static_center, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        center_area = height * (center_right - center_left)
        for contour in contours:
            area = cv2.contourArea(contour)
            fraction = area / center_area if center_area else 0
            # Must be a distinct object (5-70% of center band).
            # Over 70% means nearly the entire center is static — that's
            # an empty road, not a stationary object.
            if 0.05 < fraction < 0.70 and result.traffic_state != "free":
                result.anomaly_detected = True
                result.anomaly_reason = (
                    f"Large stationary object detected in center band "
                    f"(area={area:.0f}, {fraction * 100:.1f}% of center)"
                )
                break
        if result.anomaly_detected:
            break

    return result


def should_call_vlm(
    analysis: MotionAnalysis,
    last_vlm_call_age_seconds: float | None,
    periodic_interval: int,
) -> tuple[bool, str]:
    if analysis.anomaly_detected:
        return True, f"anomaly_detected: {analysis.anomaly_reason}"

    # Optional periodic heartbeat; set to 0 to run strict CV-first gating.
    if periodic_interval > 0 and (
        last_vlm_call_age_seconds is None or last_vlm_call_age_seconds >= periodic_interval
    ):
        return True, "periodic_heartbeat"

    return False, "local_motion_normal"

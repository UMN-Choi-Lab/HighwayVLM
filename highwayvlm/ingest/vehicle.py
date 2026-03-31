from dataclasses import dataclass, field
import threading

import cv2
import numpy as np

from highwayvlm.settings import (
    get_yolo_confidence,
    get_yolo_enabled,
    get_yolo_vehicle_classes,
)


@dataclass
class VehicleDetection:
    vehicle_count: int = 0
    vehicle_details: list[dict] = field(default_factory=list)
    traffic_state: str = "unknown"


def _traffic_state_from_count(count: int) -> str:
    if count <= 4:
        return "smooth"
    if count <= 12:
        return "slow"
    return "congested"


_singleton_detector = None


class VehicleDetector:
    def __init__(self):
        self._model = None
        self._infer_lock = threading.Lock()
        self._confidence = get_yolo_confidence()
        self._vehicle_classes = get_yolo_vehicle_classes()

    def _ensure_model(self):
        if self._model is not None:
            return
        from ultralytics import YOLO

        self._model = YOLO("yolov8n.pt")

    def detect(self, frame_bytes: bytes) -> VehicleDetection:
        if not get_yolo_enabled():
            return VehicleDetection()

        try:
            self._ensure_model()
        except Exception:
            # Keep pipeline alive if model bootstrap fails in a given environment.
            return VehicleDetection()

        arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return VehicleDetection()

        # Ultralytics model inference is not reliably thread-safe across parallel calls.
        # Serialize only the model invocation while allowing the rest of camera work
        # to remain concurrent.
        with self._infer_lock:
            results = self._model(img, conf=self._confidence, verbose=False)

        vehicle_details = []
        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                if cls_id not in self._vehicle_classes:
                    continue
                conf = float(box.conf[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                vehicle_details.append(
                    {
                        "class_id": cls_id,
                        "class_name": r.names[cls_id],
                        "confidence": round(conf, 3),
                        "bbox": [round(v, 1) for v in (x1, y1, x2, y2)],
                    }
                )

        count = len(vehicle_details)
        return VehicleDetection(
            vehicle_count=count,
            vehicle_details=vehicle_details,
            traffic_state=_traffic_state_from_count(count),
        )


    def detect_stopped(
        self, early_bytes: bytes, late_bytes: bytes, iou_threshold: float = 0.5
    ) -> list[dict]:
        """Compare YOLO detections between two frames to find stopped vehicles.

        Returns a list of vehicle detections that appear in the same position
        in both frames (IoU > threshold), indicating the vehicle hasn't moved.
        """
        if not get_yolo_enabled():
            return []

        early = self.detect(early_bytes)
        late = self.detect(late_bytes)

        if not early.vehicle_details or not late.vehicle_details:
            return []

        stopped = []
        used_late = set()

        for det_e in early.vehicle_details:
            best_iou = 0.0
            best_idx = -1
            for j, det_l in enumerate(late.vehicle_details):
                if j in used_late:
                    continue
                if det_e["class_id"] != det_l["class_id"]:
                    continue
                iou = _compute_iou(det_e["bbox"], det_l["bbox"])
                if iou > best_iou:
                    best_iou = iou
                    best_idx = j

            if best_iou >= iou_threshold and best_idx >= 0:
                used_late.add(best_idx)
                stopped.append({
                    "class_name": det_e["class_name"],
                    "confidence": det_e["confidence"],
                    "bbox_early": det_e["bbox"],
                    "bbox_late": late.vehicle_details[best_idx]["bbox"],
                    "iou": round(best_iou, 3),
                })

        return stopped


def _compute_iou(box_a: list[float], box_b: list[float]) -> float:
    """Compute IoU between two [x1, y1, x2, y2] bboxes."""
    x1 = max(box_a[0], box_b[0])
    y1 = max(box_a[1], box_b[1])
    x2 = min(box_a[2], box_b[2])
    y2 = min(box_a[3], box_b[3])

    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0

    area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
    area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
    union = area_a + area_b - inter

    return inter / union if union > 0 else 0.0


def get_detector() -> VehicleDetector:
    global _singleton_detector
    if _singleton_detector is None:
        _singleton_detector = VehicleDetector()
    return _singleton_detector

from highwayvlm.ingest.motion import MotionAnalysis
from highwayvlm.pipeline import CameraState, _decide_vlm_call


def test_stopped_vehicle_escalates_to_vlm():
    call_vlm, reason = _decide_vlm_call(
        MotionAnalysis(),
        CameraState(),
        stopped_vehicles=[{"class_name": "car"}],
    )

    assert call_vlm is True
    assert reason == "stopped_vehicle_detected"


def test_motion_anomaly_keeps_priority_over_stopped_vehicle():
    call_vlm, reason = _decide_vlm_call(
        MotionAnalysis(anomaly_detected=True, anomaly_reason="large contour"),
        CameraState(),
        stopped_vehicles=[{"class_name": "car"}],
    )

    assert call_vlm is True
    assert reason == "anomaly_detected: large contour"


def test_pending_incident_still_escalates_without_stopped_vehicle():
    state = CameraState()
    state.pending_incident = object()

    call_vlm, reason = _decide_vlm_call(
        MotionAnalysis(),
        state,
        stopped_vehicles=[],
    )

    assert call_vlm is True
    assert reason == "pending_incident_confirmation"


def test_pending_incident_keeps_priority_over_stopped_vehicle():
    state = CameraState()
    state.pending_incident = object()

    call_vlm, reason = _decide_vlm_call(
        MotionAnalysis(),
        state,
        stopped_vehicles=[{"class_name": "car"}],
    )

    assert call_vlm is True
    assert reason == "pending_incident_confirmation"


def test_normal_motion_without_incident_stays_local():
    call_vlm, reason = _decide_vlm_call(
        MotionAnalysis(),
        CameraState(),
        stopped_vehicles=[],
    )

    assert call_vlm is False
    assert reason == "local_motion_normal"

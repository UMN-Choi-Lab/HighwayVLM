import base64
import json
import time

import cv2
import numpy as np
import openai
from pydantic import BaseModel, Field, ValidationError, field_validator

from highwayvlm.settings import (
    get_vlm_api_key,
    get_vlm_base_url,
    get_vlm_max_retries,
    get_vlm_max_tokens,
    get_vlm_timeout_seconds,
)


def _crop_incident_region(image_bytes, bbox, padding=0.25):
    """Crop and enlarge the bbox region from an image.

    bbox: [x1, y1, x2, y2] as fractions (0.0-1.0).
    padding: fraction of bbox size to add around it.
    Returns JPEG bytes of the cropped region, or None.
    """
    if not bbox or len(bbox) != 4:
        return None
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    h, w = img.shape[:2]
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    # Add padding
    px1 = max(0.0, x1 - bw * padding)
    py1 = max(0.0, y1 - bh * padding)
    px2 = min(1.0, x2 + bw * padding)
    py2 = min(1.0, y2 + bh * padding)

    crop = img[int(py1 * h):int(py2 * h), int(px1 * w):int(px2 * w)]
    if crop.size == 0:
        return None

    _, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return buf.tobytes()

class Incident(BaseModel):
    type: str
    severity: str
    description: str
    bbox: list[float] | None = None

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, value):
        allowed = {"low", "medium", "high"}
        if value not in allowed:
            raise ValueError("severity must be low, medium, or high")
        return value

    @field_validator("bbox")
    @classmethod
    def _validate_bbox(cls, value):
        if value is None:
            return None
        if len(value) != 4:
            return None
        # Clamp to [0, 1] range
        return [max(0.0, min(1.0, float(v))) for v in value]


class VLMResult(BaseModel):
    observed_direction: str
    traffic_state: str
    incidents: list[Incident] = Field(default_factory=list)
    notes: str | None = None
    overall_confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("traffic_state")
    @classmethod
    def _validate_traffic_state(cls, value):
        allowed = {"smooth", "slow", "congested", "unknown"}
        if value not in allowed:
            raise ValueError("traffic_state must be smooth, slow, congested, or unknown")
        return value


class VLMClient:
    def __init__(self, model, timeout_seconds=None, max_retries=None, max_tokens=None, base_url=None, api_key=None):
        self.model = model
        self.timeout_seconds = timeout_seconds or get_vlm_timeout_seconds()
        self.max_retries = max_retries or get_vlm_max_retries()
        self.max_tokens = max_tokens or get_vlm_max_tokens()
        self.base_url = (base_url or get_vlm_base_url()).rstrip("/")
        self.api_key = api_key or get_vlm_api_key()
        if not self.api_key:
            raise ValueError("Missing VLM API key. Set OPENAI_API_KEY or VLM_API_KEY.")
        self.client = openai.OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            max_retries=0,
        )

    def _build_prompt(self, camera, captured_at):
        system = (
            "You are a freeway traffic incident detection system. Analyze camera images and respond with JSON only.\n"
            "\n"
            "TRAFFIC STATES (based on vehicle count and spacing on the PRIMARY freeway lanes ONLY):\n"
            "- smooth: few or no vehicles visible, open lanes, traffic flowing freely\n"
            "- slow: noticeable traffic, vehicles moving at reduced speed, some congestion\n"
            "- congested: dense traffic, vehicles closely spaced, stopped or barely moving\n"
            "- unknown: cannot determine (e.g. obstructed view, night with no visible vehicles)\n"
            "\n"
            "INCIDENT TYPES: crash, stopped_vehicle_lane, stalled_vehicle, debris, emergency_response, pedestrian, traffic_anomaly\n"
            "SEVERITY: high (crashes, vehicles in lanes, pedestrians), medium (debris in lanes, lane closures), low (minor anomalies)\n"
            "\n"
            "CRITICAL RULES:\n"
            "- Focus ONLY on the PRIMARY freeway lanes (the main road this camera monitors). Ignore background roads, "
            "cross streets, overpasses, ramps, and any traffic on other roadways.\n"
            "- If the primary freeway lanes are empty or have very few vehicles, traffic_state MUST be \"smooth\" — "
            "do NOT use congested just because background roads have traffic.\n"
            "- Vehicles on the shoulder are NORMAL - do NOT report them as incidents.\n"
            "- traffic_state MUST be consistent with your notes. If you note \"no vehicles\" or \"empty road\", "
            "traffic_state must be \"smooth\".\n"
            "\n"
            "JSON SCHEMA:\n"
            "{\"observed_direction\": \"EB|WB|NB|SB\", \"traffic_state\": \"smooth|slow|congested|unknown\", "
            "\"incidents\": [{\"type\": \"string\", \"severity\": \"low|medium|high\", \"description\": \"string\", "
            "\"bbox\": [x1, y1, x2, y2]}], "
            "\"notes\": \"brief scene summary\", \"overall_confidence\": 0.0-1.0}\n"
            "\n"
            "BBOX: For each incident, provide a bounding box [x1, y1, x2, y2] as fractions of image width/height "
            "(0.0 to 1.0). x1,y1 = top-left corner, x2,y2 = bottom-right corner. "
            "The bbox should tightly enclose the vehicle or object involved in the incident."
        )
        user_text = (
            "Analyze this freeway camera image for traffic incidents and conditions.\n"
            "\n"
            f"Camera: {camera.get('name')}\n"
            f"Location: {camera.get('corridor')} {camera.get('direction')}bound\n"
            f"Camera ID: {camera.get('camera_id')}\n"
            f"Timestamp: {captured_at}\n"
            "\n"
            "Examine the image carefully for:\n"
            "1. Any stopped or unusual vehicles in lanes or on shoulders\n"
            "2. Traffic flow patterns and density\n"
            "3. Visible incidents, debris, or anomalies\n"
            "4. Emergency response presence\n"
            "\n"
            "Provide your analysis as JSON only."
        )
        return system, user_text

    def _image_to_data_url(self, image_bytes, content_type):
        content_type = (content_type or "image/jpeg").split(";")[0]
        encoded = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    def _parse_json(self, text):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Extract top-level JSON objects using bracket counting so nested
        # braces (e.g. incidents: [{...}]) don't truncate the match.
        for start in range(len(text)):
            if text[start] != "{":
                continue
            depth = 0
            in_string = False
            escape = False
            for i in range(start, len(text)):
                ch = text[i]
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"' and not escape:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            break
        raise ValueError("No valid JSON found in VLM response")


    def _normalize_parsed(self, camera, parsed):
        if isinstance(parsed, list):
            parsed = {"incidents": parsed}
        if isinstance(parsed, dict):
            if {"type", "severity", "description"}.issubset(parsed) and "incidents" not in parsed:
                parsed = {"incidents": [parsed]}
            incidents = parsed.get("incidents")
            if incidents is None:
                parsed["incidents"] = []
            elif not isinstance(incidents, list):
                parsed["incidents"] = [incidents]
            normalized_incidents = []
            for incident in parsed["incidents"]:
                if isinstance(incident, dict):
                    item = dict(incident)
                else:
                    item = {"description": str(incident)}
                item.setdefault("type", "incident")
                item.setdefault("description", "unspecified")
                # Normalize bbox
                bbox = item.get("bbox")
                if bbox is not None:
                    try:
                        bbox = [float(v) for v in bbox]
                        if len(bbox) != 4:
                            bbox = None
                    except (TypeError, ValueError):
                        bbox = None
                item["bbox"] = bbox
                severity = item.get("severity")
                severity_value = str(severity).strip().lower() if severity is not None else ""
                severity_map = {
                    "low": "low",
                    "minor": "low",
                    "medium": "medium",
                    "moderate": "medium",
                    "high": "high",
                    "severe": "high",
                    "critical": "high",
                }
                item["severity"] = severity_map.get(severity_value, "low")
                normalized_incidents.append(item)
            parsed["incidents"] = normalized_incidents
            traffic_state = parsed.get("traffic_state")
            if isinstance(traffic_state, str):
                normalized_ts = traffic_state.strip().lower().replace(" ", "_")
                # Map legacy 4-state labels to new 3-state labels
                ts_map = {
                    "free": "smooth",
                    "moderate": "slow",
                    "heavy": "congested",
                    "stop_and_go": "congested",
                }
                parsed["traffic_state"] = ts_map.get(normalized_ts, normalized_ts)
            confidence = parsed.get("overall_confidence")
            if confidence is not None:
                try:
                    parsed["overall_confidence"] = float(confidence)
                except (TypeError, ValueError):
                    parsed["overall_confidence"] = 0.2
            parsed.setdefault("observed_direction", camera.get("direction") or "unknown")
            parsed.setdefault("traffic_state", "unknown")
            parsed.setdefault("overall_confidence", 0.2)
            parsed.setdefault("notes", None)
        return parsed

    def _summary_notes(self, incidents, traffic_state=None, observed_direction=None):
        if not incidents:
            direction = (observed_direction or "unknown").upper()
            flow = (traffic_state or "unknown").replace("_", " ")
            return (
                f"No active incidents are visible in this frame; {direction} traffic appears {flow} with vehicles "
                "moving through open lanes and no clear lane-blocking hazards. Vehicle presence appears typical for "
                "the corridor, lane usage looks orderly, and no obvious stopped vehicles or debris are visible in "
                "active travel lanes. Weather and visibility appear adequate for monitoring in this snapshot, with "
                "no clear environmental factor causing abnormal operations."
            )
        parts = []
        for incident in incidents:
            kind = (incident.type or "incident").replace("_", " ").strip()
            label = " ".join(word.capitalize() for word in kind.split())
            if incident.severity:
                label = f"{label} ({incident.severity})"
            parts.append(label)
        return ", ".join(parts)

    def _is_generic_clear_note(self, note):
        if not note:
            return True
        normalized = " ".join(str(note).strip().lower().split())
        generic = {
            "clear traffic",
            "no incidents",
            "no incident",
            "none",
            "no issues",
            "no incidents detected",
            "clear",
            "traffic is clear",
            "normal traffic",
        }
        return normalized in generic

    def _build_comparison_prompt(self, camera, captured_at, motion_context=None):
        system = (
            "You are a freeway traffic incident detection system. You are seeing TWO frames ~5-10 seconds apart "
            "from the same camera. Analyze the pair together and respond with JSON only.\n"
            "\n"
            "MULTI-FRAME ANALYSIS RULES:\n"
            "- CRITICAL: A vehicle in the same LANE POSITION across two frames does NOT mean it is stopped. "
            "On a busy freeway, DIFFERENT vehicles often occupy the same spot seconds apart. "
            "To confirm a stopped vehicle, look for THE EXACT SAME vehicle (same color, shape, size) "
            "that has NOT moved at all between frames.\n"
            "- Shifting headlights = MOVING traffic, NOT emergency lights\n"
            "- Compare vehicle positions between frames to determine actual movement\n"
            "- If traffic is flowing (vehicles appear in different positions), do NOT report stopped vehicles\n"
            "\n"
            "NIGHTTIME FALSE POSITIVE RULES (CRITICAL — most false alarms happen at night):\n"
            "- At night you can ONLY see headlights and taillights, NOT vehicle shapes. "
            "You CANNOT determine if a vehicle is stopped just from lights alone.\n"
            "- Headlights/taillights in the same lane position across frames are almost always DIFFERENT vehicles "
            "in normal flowing traffic — NOT one stopped vehicle.\n"
            "- Do NOT report 'stopped_vehicle_lane' at night unless you can clearly see a dark vehicle shape "
            "with hazard lights or a vehicle visibly blocking traffic with cars swerving around it.\n"
            "- Do NOT report 'emergency_response' unless you see CLEARLY ALTERNATING red/blue flashing patterns "
            "that are distinctly different from normal headlights or brake lights. "
            "Regular bright headlights or clusters of taillights are NOT emergency lights.\n"
            "- When in doubt at night, report NO incidents. It is far better to miss a marginal incident "
            "than to report a false alarm.\n"
            "\n"
            "TRAFFIC STATES (based on vehicle count and spacing on the PRIMARY freeway lanes ONLY):\n"
            "- smooth: few or no vehicles visible, open lanes, traffic flowing freely\n"
            "- slow: noticeable traffic, vehicles moving at reduced speed, some congestion\n"
            "- congested: dense traffic, vehicles closely spaced, stopped or barely moving\n"
            "- unknown: cannot determine (e.g. obstructed view, night with no visible vehicles)\n"
            "\n"
            "INCIDENT TYPES: crash, stopped_vehicle_lane, stalled_vehicle, debris, emergency_response, pedestrian, traffic_anomaly\n"
            "SEVERITY: high (crashes, vehicles in lanes, pedestrians), medium (debris in lanes, lane closures), low (minor anomalies)\n"
            "\n"
            "CRITICAL RULES:\n"
            "- Focus ONLY on the PRIMARY freeway lanes (the main road this camera monitors). Ignore background roads, "
            "cross streets, overpasses, ramps, and any traffic on other roadways.\n"
            "- If the primary freeway lanes are empty or have very few vehicles, traffic_state MUST be \"smooth\" — "
            "do NOT use congested just because background roads have traffic.\n"
            "- Vehicles on the shoulder are NORMAL - do NOT report them as incidents.\n"
            "- traffic_state MUST be consistent with your notes. If you note \"no vehicles\" or \"empty road\", "
            "traffic_state must be \"smooth\".\n"
            "\n"
            "JSON SCHEMA:\n"
            "{\"observed_direction\": \"EB|WB|NB|SB\", \"traffic_state\": \"smooth|slow|congested|unknown\", "
            "\"incidents\": [{\"type\": \"string\", \"severity\": \"low|medium|high\", \"description\": \"string\", "
            "\"bbox\": [x1, y1, x2, y2]}], "
            "\"notes\": \"brief scene summary\", \"overall_confidence\": 0.0-1.0}\n"
            "\n"
            "BBOX: For each incident, provide a bounding box [x1, y1, x2, y2] as fractions of image width/height "
            "(0.0 to 1.0). x1,y1 = top-left corner, x2,y2 = bottom-right corner of the FIRST frame. "
            "The bbox should tightly enclose the vehicle or object involved in the incident."
        )
        motion_line = ""
        if motion_context:
            vehicle_count = motion_context.get('vehicle_count')
            vehicle_part = f", vehicle_count={vehicle_count}" if vehicle_count is not None else ""
            brightness = motion_context.get('mean_brightness', 128)
            is_night = brightness < 40
            night_part = ""
            if is_night:
                night_part = (
                    "\n*** NIGHTTIME SCENE (low brightness). Apply strict nighttime false positive rules. "
                    "Do NOT report stopped vehicles or emergency response unless evidence is UNMISTAKABLE. ***"
                )
            motion_line = (
                f"\nLocal motion analysis: changed_pixel_fraction={motion_context.get('changed_pixel_fraction', 'N/A')}, "
                f"anomaly={motion_context.get('anomaly_detected', False)}{vehicle_part}, "
                f"mean_brightness={brightness} ({'NIGHTTIME' if is_night else 'daytime'})"
                f"{night_part}"
                "\nNote: motion analysis measures pixel changes only — it cannot distinguish an empty road from "
                "stopped traffic. vehicle_count is from YOLOv8 object detection. "
                "YOU must determine traffic_state from what you SEE in the images."
            )
            # YOLO stopped vehicle cross-check
            stopped_vehicles = motion_context.get("stopped_vehicles")
            if stopped_vehicles is not None:
                if stopped_vehicles:
                    descriptions = []
                    for sv in stopped_vehicles:
                        descriptions.append(
                            f"{sv['class_name']} (IoU={sv['iou']:.2f})"
                        )
                    motion_line += (
                        f"\nYOLO cross-frame check: {len(stopped_vehicles)} vehicle(s) detected at "
                        f"same position in both frames: {', '.join(descriptions)}. "
                        "These MAY be genuinely stopped — verify visually."
                    )
                else:
                    motion_line += (
                        "\nYOLO cross-frame check: NO vehicles detected at the same position in both frames. "
                        "All vehicles appear to have moved. Be VERY cautious about reporting stopped vehicles."
                    )
            # False alarm feedback
            false_alarm_context = motion_context.get("false_alarm_context")
            if false_alarm_context:
                motion_line += f"\n{false_alarm_context}"
        user_text = (
            "Analyze these TWO freeway camera frames (earlier and later, ~5-10s apart) for traffic incidents.\n"
            "\n"
            f"Camera: {camera.get('name')}\n"
            f"Location: {camera.get('corridor')} {camera.get('direction')}bound\n"
            f"Camera ID: {camera.get('camera_id')}\n"
            f"Timestamp: {captured_at}\n"
            f"{motion_line}\n"
            "\n"
            "Compare the two frames carefully for:\n"
            "1. Vehicles that have NOT moved between frames (stopped in lanes)\n"
            "2. Traffic flow patterns — are vehicles progressing or stationary?\n"
            "3. Visible incidents, debris, or anomalies\n"
            "4. Emergency response presence (stationary flashing lights vs. moving headlights)\n"
            "\n"
            "IMPORTANT: Think step by step before concluding. In your notes field, include your reasoning:\n"
            "1. What do you see in each frame?\n"
            "2. Did any specific vehicle stay in the exact same position?\n"
            "3. Is this nighttime? If so, can you actually see vehicle shapes or only lights?\n"
            "4. What is your confidence that each incident is REAL and not a false positive?\n"
            "\n"
            "Provide your analysis as JSON only."
        )
        return system, user_text

    def _call_vlm(self, messages, max_tokens=None):
        """Single VLM API call with retries. Returns response text."""
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=max_tokens or self.max_tokens,
                    timeout=self.timeout_seconds,
                )
                text = response.choices[0].message.content
                if not text:
                    raise ValueError("No response text found in VLM response")
                return text
            except (ValidationError, ValueError) as exc:
                last_error = exc
            except openai.APIError as exc:
                last_error = exc
            time.sleep(1.0 * attempt)
        raise RuntimeError(f"VLM call failed after {self.max_retries} attempts: {last_error}")

    def _postprocess_result(self, camera, result):
        """Common post-processing for VLM results."""
        if result.traffic_state == "unknown":
            result.traffic_state = "slow" if result.incidents else "smooth"
        if not result.incidents and self._is_generic_clear_note(result.notes):
            result.notes = self._summary_notes(
                result.incidents,
                traffic_state=result.traffic_state,
                observed_direction=result.observed_direction,
            )
        elif not result.notes or not result.notes.strip():
            result.notes = self._summary_notes(
                result.incidents,
                traffic_state=result.traffic_state,
                observed_direction=result.observed_direction,
            )
        return result

    def verify_incidents(self, camera, image_bytes_early, image_bytes_late,
                         incidents, content_type=None):
        """Stage 2: Crop each incident region from both frames and verify.

        Returns list of verified Incident objects (subset of input).
        """
        if not incidents:
            return []

        verified = []
        for incident in incidents:
            if not incident.bbox:
                # No bbox → can't crop → skip verification, keep as-is
                verified.append(incident)
                continue

            crop_early = _crop_incident_region(image_bytes_early, incident.bbox)
            crop_late = _crop_incident_region(image_bytes_late, incident.bbox)
            if not crop_early or not crop_late:
                continue

            early_url = self._image_to_data_url(crop_early, content_type)
            late_url = self._image_to_data_url(crop_late, content_type)

            prompt = (
                f"You are verifying a potential traffic incident detected by an AI system.\n\n"
                f"The system detected: {incident.type} ({incident.severity})\n"
                f"Description: {incident.description}\n"
                f"Camera: {camera.get('name')} — {camera.get('corridor')} {camera.get('direction')}bound\n\n"
                "You are seeing CROPPED and ZOOMED views of the incident region from TWO frames "
                "(earlier and later, ~5-20 seconds apart).\n\n"
                "Answer these questions:\n"
                "1. Can you see the SAME vehicle in BOTH crops? (same shape, color, size)\n"
                "2. Has this vehicle clearly NOT moved between the two frames?\n"
                "3. If nighttime: can you see the actual vehicle shape, or only lights?\n"
                "4. Could this be a DIFFERENT vehicle that happens to be in the same lane position?\n"
                "5. For emergency_response: are there clearly alternating red/blue flashing lights?\n\n"
                "Respond with JSON only:\n"
                "{\"is_real_incident\": true/false, \"reasoning\": \"your explanation\"}"
            )
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": early_url}},
                        {"type": "image_url", "image_url": {"url": late_url}},
                    ],
                },
            ]
            try:
                text = self._call_vlm(messages, max_tokens=256)
                parsed = self._parse_json(text)
                is_real = parsed.get("is_real_incident", False)
                reasoning = parsed.get("reasoning", "")
                if is_real:
                    verified.append(incident)
                    print(f"  Incident VERIFIED: {incident.type} — {reasoning[:80]}")
                else:
                    print(f"  Incident REJECTED: {incident.type} — {reasoning[:80]}")
            except Exception as exc:
                # On verification failure, keep the incident (fail-open for false negatives)
                print(f"  Verification call failed for {incident.type}: {exc}")
                verified.append(incident)

        return verified

    def reflect_on_assessment(self, camera, image_bytes_early, image_bytes_late,
                              stage1_result, verified_incidents, content_type=None):
        """Stage 3: Self-reflection. Show VLM its assessment and ask for final decision.

        Returns a final VLMResult with potentially revised incidents.
        """
        early_url = self._image_to_data_url(image_bytes_early, content_type)
        late_url = self._image_to_data_url(image_bytes_late, content_type)

        stage1_summary = json.dumps(stage1_result.model_dump(), indent=2)
        verified_types = [i.type for i in verified_incidents]

        prompt = (
            "You are performing a FINAL REVIEW of a traffic incident assessment.\n\n"
            f"Camera: {camera.get('name')} — {camera.get('corridor')} {camera.get('direction')}bound\n\n"
            f"INITIAL ASSESSMENT:\n{stage1_summary}\n\n"
            f"After cropped-image verification, these incidents were confirmed: {verified_types}\n\n"
            "Look at the full frames again. For your FINAL DECISION, consider:\n"
            "1. Are the confirmed incidents TRULY visible and unambiguous?\n"
            "2. Would a human traffic operator agree these are real incidents?\n"
            "3. Are there any incidents you MISSED in the initial scan?\n"
            "4. Should any confirmed incidents be downgraded or removed?\n\n"
            "Return your FINAL assessment as JSON:\n"
            "{\"observed_direction\": \"EB|WB|NB|SB\", \"traffic_state\": \"smooth|slow|congested|unknown\", "
            "\"incidents\": [{\"type\": \"string\", \"severity\": \"low|medium|high\", \"description\": \"string\", "
            "\"bbox\": [x1, y1, x2, y2]}], "
            "\"notes\": \"brief scene summary with reasoning\", \"overall_confidence\": 0.0-1.0}"
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": early_url}},
                    {"type": "image_url", "image_url": {"url": late_url}},
                ],
            },
        ]

        text = self._call_vlm(messages)
        parsed = self._parse_json(text)
        parsed = self._normalize_parsed(camera, parsed)
        result = VLMResult.model_validate(parsed)
        return self._postprocess_result(camera, result), text

    def analyze_comparison(self, camera, image_bytes_early, image_bytes_late, captured_at,
                           content_type=None, motion_context=None):
        system, user_text = self._build_comparison_prompt(camera, captured_at, motion_context)
        early_url = self._image_to_data_url(image_bytes_early, content_type)
        late_url = self._image_to_data_url(image_bytes_late, content_type)
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": early_url},
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": late_url},
                    },
                ],
            },
        ]
        text = self._call_vlm(messages)
        parsed = self._parse_json(text)
        parsed = self._normalize_parsed(camera, parsed)
        result = VLMResult.model_validate(parsed)
        result = self._postprocess_result(camera, result)

        # --- Multi-stage reasoning when incidents detected ---
        if result.incidents:
            print(f"  Stage 1: {len(result.incidents)} candidate incident(s), verifying...")

            # Stage 2: Crop & Verify each incident
            verified = self.verify_incidents(
                camera, image_bytes_early, image_bytes_late,
                result.incidents, content_type,
            )

            if not verified:
                # All incidents rejected by verification
                print(f"  Stage 2: All incidents rejected. Clearing.")
                result.incidents = []
                result.notes = (
                    f"Initial scan detected incidents but cropped verification rejected all. "
                    f"Original notes: {result.notes}"
                )
            elif len(verified) < len(result.incidents):
                # Some rejected
                print(f"  Stage 2: {len(verified)}/{len(result.incidents)} incidents verified.")
                result.incidents = verified
            else:
                print(f"  Stage 2: All {len(verified)} incident(s) verified.")

            # Stage 3: Self-reflection (only if incidents survive Stage 2)
            if result.incidents:
                try:
                    print(f"  Stage 3: Self-reflection...")
                    final_result, final_text = self.reflect_on_assessment(
                        camera, image_bytes_early, image_bytes_late,
                        result, verified, content_type,
                    )
                    if not final_result.incidents:
                        print(f"  Stage 3: Reflection removed all incidents.")
                    else:
                        print(f"  Stage 3: {len(final_result.incidents)} incident(s) in final assessment.")
                    result = final_result
                    text = text + "\n--- REFLECTION ---\n" + final_text
                except Exception as exc:
                    print(f"  Stage 3 reflection failed: {exc}, keeping Stage 2 result")

        return result, text

    def analyze(self, camera, image_bytes, captured_at, content_type=None):
        system, user_text = self._build_prompt(camera, captured_at)
        image_url = self._image_to_data_url(image_bytes, content_type)
        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    },
                ],
            },
        ]
        text = self._call_vlm(messages)
        parsed = self._parse_json(text)
        parsed = self._normalize_parsed(camera, parsed)
        result = VLMResult.model_validate(parsed)
        return self._postprocess_result(camera, result), text

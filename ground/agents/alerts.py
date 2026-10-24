"""Beach alert writer. Triggers on a rip candidate or people in a water zone, sends Claude the frame plus the
detections, and stores a short alert with an explicit uncertainty line. Every alert starts as needs_review:
a person confirms before it goes anywhere.
"""
import base64
import json

import cv2
import numpy as np

from agents.llm import VISION_MODEL, Claude

MAX_SIDE_PX = 1024
JPEG_QUALITY = 85
MIN_INTERVAL_S = 120.0
NEAR_RIP_MARGIN = 0.5
LOW_CONFIDENCE = 0.5

ALERT_SCHEMA = {
    "type": "object",
    "properties": {
        "alert": {"type": "string"},
        "uncertainty": {"type": "string"},
        "rip_visible": {"type": "string", "enum": ["yes", "no", "unclear"]},
        "people_in_water": {"type": ["integer", "null"]},
    },
    "required": ["alert", "uncertainty", "rip_visible", "people_in_water"],
    "additionalProperties": False,
}

SYSTEM = (
    "You write beach safety alerts from a tethered balloon camera over Ocean Beach, San Francisco, for a beach "
    "patrol member or a parent to read on a phone. You get one aerial frame, the object detector's boxes "
    "(pixel coordinates in this image), and counts. Rip currents look like dark gaps or channels in the line of "
    "breaking waves. Write the alert in at most two short sentences: what and where in the frame (use visible "
    "landmarks or frame position; the camera heading is unknown, so do not claim compass directions), and how "
    "many people are in the water near it. Then give one uncertainty sentence: what could make this wrong "
    "(glare, fog, tilt, small or occluded swimmers, detector errors). People are a few pixels across: count them, "
    "never describe or identify anyone (no clothing, age, gender or appearance). If the frame does not support "
    "the detector's claim, say so plainly. A human reviews this before it is sent."
)


def downscale(image: np.ndarray, max_side: int = MAX_SIDE_PX) -> tuple[np.ndarray, float]:
    h, w = image.shape[:2]
    factor = min(1.0, max_side / max(h, w))
    if factor == 1.0:
        return image, factor
    return cv2.resize(image, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA), factor


def image_block(image: np.ndarray) -> tuple[dict, float]:
    small, factor = downscale(image)
    ok, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("could not encode frame as JPEG")
    data = base64.standard_b64encode(jpeg.tobytes()).decode("ascii")
    block = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
             "_size": (small.shape[1], small.shape[0])}
    return block, factor


def _near(center: tuple[float, float], box: list[float], margin: float) -> bool:
    x1, y1, x2, y2 = box
    mx, my = (x2 - x1) * margin, (y2 - y1) * margin
    return x1 - mx <= center[0] <= x2 + mx and y1 - my <= center[1] <= y2 + my


def people_near_rip(detections: list[dict], rips: list[dict], margin: float = NEAR_RIP_MARGIN) -> int:
    people = [((d["xyxy"][0] + d["xyxy"][2]) / 2, (d["xyxy"][1] + d["xyxy"][3]) / 2)
              for d in detections if d["cls"] == "person"]
    return sum(1 for p in people if any(_near(p, r["xyxy"], margin) for r in rips))


def water_people(obs: dict, water_zones: list[str]) -> int:
    return sum(obs.get("zones", {}).get(z, {}).get("person", 0) for z in water_zones)


def busiest_zone(obs: dict, water_zones: list[str]) -> str | None:
    """The water zone with the most people, for the patrol's Jira dedupe; the first one when all are empty."""
    if not water_zones:
        return None
    return max(water_zones, key=lambda z: obs.get("zones", {}).get(z, {}).get("person", 0))


def trigger(obs: dict, detections: list[dict], water_zones: list[str]) -> dict | None:
    in_water = water_people(obs, water_zones)
    if not obs["rip"] and in_water == 0:
        return None
    return {"rip_candidates": len(obs["rip"]), "people_in_water_zone": in_water,
            "people_near_rip": people_near_rip(detections, obs["rip"])}


def engine_alert(trig: dict, obs: dict) -> dict:
    parts = []
    if trig["rip_candidates"]:
        parts.append(f"Detector flags {trig['rip_candidates']} possible rip current(s) in this frame")
    if trig["people_near_rip"]:
        parts.append(f"{trig['people_near_rip']} people in the water near it")
    elif trig["people_in_water_zone"]:
        parts.append(f"{trig['people_in_water_zone']} people counted in the water zone")
    return {"alert": "; ".join(parts) + ".",
            "uncertainty": f"Detector only, not reviewed by Claude; frame confidence {obs['confidence']:.2f}.",
            "rip_visible": "unclear", "people_in_water": trig["people_in_water_zone"] or None}


def _scaled(detections: list[dict], factor: float) -> list[dict]:
    return [{"cls": d["cls"], "conf": d["conf"], "xyxy": [round(v * factor) for v in d["xyxy"]]}
            for d in detections if d["cls"] in ("person", "rip")]


class AlertWriter:
    def __init__(self, claude: Claude | None, site: dict | None):
        self.claude = claude
        self.water_zones = [z["id"] for z in (site or {}).get("zones", []) if z["kind"] == "water"]
        self.last_alert_t: float | None = None

    def _write(self, image: np.ndarray, detections: list[dict], trig: dict, obs: dict) -> tuple[dict, str]:
        if not self.claude:
            return engine_alert(trig, obs), "engine"
        block, factor = image_block(image)
        facts = {"trigger": trig, "counts": obs["counts"], "frame_confidence": obs["confidence"],
                 "tilt_deg": obs["tilt_deg"], "alt_m": obs["alt_m"], "detections": _scaled(detections, factor)}
        reply = self.claude.ask(purpose="alerts", model=VISION_MODEL, system=SYSTEM, effort="medium",
                                max_tokens=2000, schema=ALERT_SCHEMA,
                                content=[block, {"type": "text", "text": json.dumps(facts)}])
        if reply.data:
            return reply.data, reply.model
        return engine_alert(trig, obs), f"engine ({reply.skipped})"

    def check(self, obs: dict, detections: list[dict], image: np.ndarray) -> dict | None:
        trig = trigger(obs, detections, self.water_zones)
        if trig is None:
            return None
        if self.last_alert_t is not None and obs["t"] - self.last_alert_t < MIN_INTERVAL_S:
            return None
        self.last_alert_t = obs["t"]
        written, author = self._write(image, detections, trig, obs)
        low = obs["confidence"] < LOW_CONFIDENCE
        uncertainty = written["uncertainty"]
        if low:
            uncertainty = f"Low-confidence frame ({obs['confidence']:.2f}); treat as a lead, not a finding. {uncertainty}"
        return {"agent": "alerts", "t": obs["t"], "session": obs["session"], "frame": obs["frame"],
                "zone": busiest_zone(obs, self.water_zones), "status": "needs_review", "alert": written["alert"], "uncertainty": uncertainty,
                "rip_visible": written["rip_visible"], "people_in_water": written["people_in_water"],
                "trigger": trig, "counts": obs["counts"], "rip": obs["rip"], "confidence": obs["confidence"],
                "low_confidence": low, "written_by": author}

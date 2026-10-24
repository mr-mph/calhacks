import base64

import cv2
import numpy as np

from agents.alerts import MAX_SIDE_PX, AlertWriter, image_block, people_near_rip, trigger

SITE = {"zones": [{"id": "surf", "kind": "water", "polygon": [[0, 0], [10, 0], [10, 10]]}]}
DETECTIONS = [
    {"cls": "person", "conf": 0.6, "xyxy": [100, 100, 104, 108]},
    {"cls": "person", "conf": 0.6, "xyxy": [900, 900, 904, 908]},
    {"cls": "rip", "conf": 0.7, "xyxy": [80, 80, 140, 200]},
]


def obs(t: float = 100.0, rip: bool = True, in_water: int = 2, confidence: float = 0.8) -> dict:
    return {"t": t, "session": "s", "frame": "stills/x.jpg", "alt_m": 90.0, "tilt_deg": 4.0,
            "confidence": confidence, "counts": {"car": 0, "person": 2}, "zones": {"surf": {"person": in_water}},
            "rip": [{"xyxy": [80, 80, 140, 200], "conf": 0.7}] if rip else []}


def test_people_near_rip_counts_only_nearby_people():
    assert people_near_rip(DETECTIONS, obs()["rip"]) == 1


def test_trigger_on_rip_or_people_in_water():
    assert trigger(obs(rip=False, in_water=0), DETECTIONS, ["surf"]) is None
    assert trigger(obs(rip=False, in_water=1), DETECTIONS, ["surf"])["people_in_water_zone"] == 1
    assert trigger(obs(), DETECTIONS, ["surf"])["rip_candidates"] == 1


def test_real_frame_is_downscaled_before_sending(real_images):
    image = cv2.imread(str(real_images["street_a"]))
    block, factor = image_block(image)
    assert max(block["_size"]) <= MAX_SIDE_PX and factor < 1.0
    decoded = cv2.imdecode(np.frombuffer(base64.b64decode(block["source"]["data"]), np.uint8), cv2.IMREAD_COLOR)
    assert max(decoded.shape[:2]) <= MAX_SIDE_PX


def test_engine_alert_needs_review_and_states_uncertainty(real_images):
    writer = AlertWriter(claude=None, site=SITE)
    image = cv2.imread(str(real_images["street_a"]))
    alert = writer.check(obs(), DETECTIONS, image)
    assert alert["status"] == "needs_review"
    assert alert["uncertainty"] and alert["written_by"] == "engine"
    assert "1 people in the water near it" in alert["alert"]


def test_alerts_are_rate_limited_and_low_confidence_is_flagged(real_images):
    writer = AlertWriter(claude=None, site=SITE)
    image = cv2.imread(str(real_images["street_a"]))
    assert writer.check(obs(t=0), DETECTIONS, image)
    assert writer.check(obs(t=60), DETECTIONS, image) is None
    late = writer.check(obs(t=200, confidence=0.3), DETECTIONS, image)
    assert late["low_confidence"] and late["uncertainty"].startswith("Low-confidence frame")

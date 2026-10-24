import json

import numpy as np
import pytest

from align import Alignment
from observe import SiteError, build_observation, confidence, load_site, stability_factor, tilt_factor, validate_site

SQUARE = [[0, 0], [100, 0], [100, 100], [0, 100]]
SITE = {
    "site": "test-lot",
    "reference_frame": "ref.jpg",
    "zones": [
        {"id": "lot-a", "kind": "lot", "polygon": SQUARE, "capacity": 4},
        {"id": "water", "kind": "water", "polygon": [[200, 0], [300, 0], [300, 100], [200, 100]]},
    ],
    "spaces": [
        {"id": "A01", "zone": "lot-a", "polygon": [[0, 0], [50, 0], [50, 50], [0, 50]]},
        {"id": "A02", "zone": "lot-a", "polygon": [[50, 0], [100, 0], [100, 50], [50, 50]]},
    ],
}
IDENTITY = Alignment(True, np.eye(3), 0.6, 80)
DETECTIONS = [
    {"cls": "car", "conf": 0.9, "xyxy": [10, 10, 30, 30]},
    {"cls": "car", "conf": 0.8, "xyxy": [20, 60, 40, 80]},
    {"cls": "person", "conf": 0.5, "xyxy": [240, 40, 244, 48]},
    {"cls": "person", "conf": 0.5, "xyxy": [400, 400, 404, 408]},
    {"cls": "rip", "conf": 0.7, "xyxy": [210, 0, 260, 90]},
]


def observe(alignment=IDENTITY, tilt=3.0, history=()):
    return build_observation(t=1.0, session="s", frame="stills/1.jpg", alt_m=90.0, tilt_deg=tilt, model="m",
                             detections=DETECTIONS, site=SITE, alignment=alignment, history=list(history))


def test_record_has_exactly_the_documented_fields():
    assert set(observe()) == {"t", "session", "frame", "alt_m", "tilt_deg", "model", "aligned", "confidence",
                              "counts", "zones", "spaces", "rip"}


def test_counts_zones_spaces_and_rip():
    rec = observe()
    assert rec["counts"] == {"car": 2, "person": 2}
    assert rec["zones"]["lot-a"] == {"car": 2, "occupancy": 0.5}
    assert rec["zones"]["water"] == {"person": 1}
    assert rec["spaces"] == {"A01": True, "A02": False}
    assert rec["rip"] == [{"xyxy": [210, 0, 260, 90], "conf": 0.7}]


def test_detections_are_mapped_through_the_alignment():
    shift = np.array([[1, 0, 200], [0, 1, 0], [0, 0, 1]], float)
    rec = observe(alignment=Alignment(True, shift, 0.6, 80))
    assert rec["zones"]["lot-a"]["car"] == 0
    assert rec["zones"]["water"] == {"person": 0}


def test_capacity_sets_occupancy_when_lot_has_no_spaces():
    site = {**SITE, "spaces": []}
    rec = build_observation(t=1.0, session="s", frame="f", alt_m=None, tilt_deg=None, model="m",
                            detections=DETECTIONS, site=site, alignment=IDENTITY, history=[])
    assert rec["zones"]["lot-a"]["occupancy"] == 0.5


def test_failed_alignment_drops_zones_and_confidence():
    rec = observe(alignment=Alignment(False, None, 0.1, 3, "3 inliers"))
    assert rec["aligned"] is False and rec["zones"] == {} and rec["spaces"] == {}
    assert rec["confidence"] < 0.5


def test_tilt_over_fifteen_degrees_is_low_confidence():
    assert tilt_factor(20.0) * 1.0 < 0.5
    assert observe(tilt=20.0)["confidence"] < 0.5
    assert observe(tilt=2.0)["confidence"] > 0.5


def test_unstable_counts_lower_confidence():
    steady = [{"car": 2, "person": 2}] * 5
    assert stability_factor({"car": 2, "person": 2}, steady) == 1.0
    assert stability_factor({"car": 40, "person": 2}, steady) == 0.5
    assert confidence(IDENTITY, 0.0, {"car": 2, "person": 2}, steady) == 1.0


def test_no_site_ignores_alignment_term():
    rec = build_observation(t=1.0, session="s", frame="f", alt_m=None, tilt_deg=0.0, model="m",
                            detections=DETECTIONS, site=None, alignment=None, history=[{"car": 2, "person": 2}] * 3)
    assert rec["aligned"] is False and rec["confidence"] == 1.0


def test_site_file_roundtrip(tmp_path):
    path = tmp_path / "site.json"
    path.write_text(json.dumps(SITE))
    assert load_site(path)["site"] == "test-lot"


@pytest.mark.parametrize("mutate, message", [
    (lambda s: s["zones"][0].update(kind="field"), "kind"),
    (lambda s: s["zones"][0].update(polygon=[[0, 0], [1, 1]]), "at least 3"),
    (lambda s: s["zones"][0].update(capacity=-1), "capacity"),
    (lambda s: s["spaces"][0].update(zone="water"), "lot zone"),
    (lambda s: s["spaces"].append(dict(s["spaces"][0])), "unique"),
])
def test_site_validation(mutate, message):
    site = json.loads(json.dumps(SITE))
    mutate(site)
    with pytest.raises(SiteError, match=message):
        validate_site(site)

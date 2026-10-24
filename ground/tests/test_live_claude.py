"""One real Claude call per agent, only when a key is available. Each test makes at most one call."""
import cv2
import pytest

from agents.alerts import AlertWriter
from agents.llm import Claude, SpendLedger, load_api_key
from agents.markets import MarketAgent
from agents.pricing import PricingAgent

pytestmark = pytest.mark.skipif(not load_api_key(), reason="no ANTHROPIC_API_KEY; agents run engine only")

LIVE_CAP_USD = 0.50


@pytest.fixture
def claude(tmp_path):
    return Claude(SpendLedger(tmp_path / "spend.json", "live-test", LIVE_CAP_USD))


def test_pricing_explanation(claude):
    obs = {"t": 0.0, "session": "s", "frame": "f", "aligned": True, "confidence": 0.9,
           "zones": {"lot-a": {"car": 43, "occupancy": 0.9}}}
    change = PricingAgent(claude).step(obs, ["lot-a"])[0]
    assert change["action"] == "raise"
    assert not change["explained_by"].startswith("engine"), change["explained_by"]
    assert "3.75" in change["explanation"]


def test_market_proposals(claude):
    site = {"zones": [{"id": "lot-a", "kind": "lot", "capacity": 48, "polygon": [[0, 0], [1, 0], [1, 1]]}]}
    history = [{"t": float(t), "confidence": 0.9, "counts": {"car": 30 + t % 5, "person": 4},
                "zones": {"lot-a": {"car": 30 + t % 5, "occupancy": (30 + t % 5) / 48}}} for t in range(0, 1200, 20)]
    records = MarketAgent(claude, site).propose(history, now=1200.0)
    assert records and not records[0]["proposed_by"].startswith("engine"), records
    assert any(r["accepted"] for r in records)


def test_beach_alert(claude, real_images):
    image = cv2.imread(str(real_images["street_a"]))
    obs = {"t": 0.0, "session": "s", "frame": "f", "alt_m": 60.0, "tilt_deg": 3.0, "confidence": 0.8,
           "counts": {"car": 9, "person": 6}, "zones": {}, "rip": [{"xyxy": [500, 300, 700, 500], "conf": 0.4}]}
    alert = AlertWriter(claude, None).check(obs, [], image)
    assert alert["status"] == "needs_review"
    assert not alert["written_by"].startswith("engine"), alert["written_by"]
    assert alert["uncertainty"]

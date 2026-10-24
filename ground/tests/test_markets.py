import math

import pytest

from agents.markets import (
    MarketAgent,
    lmsr_buy,
    lmsr_cost,
    lmsr_max_loss,
    lmsr_opening_q,
    lmsr_prices,
    settle,
    validate_proposal,
)

ZONES = {"lot-a": {"id": "lot-a", "kind": "lot", "capacity": 48}, "water": {"id": "water", "kind": "water"}}
MARKET = {"id": "m1", "question": "40 or more cars in lot-a", "zone": "lot-a", "field": "car",
          "comparator": ">=", "threshold": 40, "close_t": 10_000.0}


def frame(t: float, cars: int, confidence: float = 0.9) -> dict:
    return {"t": t, "confidence": confidence, "counts": {"car": cars, "person": 0},
            "zones": {"lot-a": {"car": cars, "occupancy": cars / 48}}}


def test_prices_sum_to_one_and_start_even():
    assert lmsr_prices([0, 0], 100) == [0.5, 0.5]
    assert sum(lmsr_prices([37.0, 5.0], 100)) == pytest.approx(1.0)


def test_opening_odds():
    for p in (0.1, 0.5, 0.73):
        q = lmsr_opening_q(p, 100)
        assert min(q) >= 0
        assert lmsr_prices(q, 100)[0] == pytest.approx(p)


def test_buy_cost_is_cost_difference_and_moves_price():
    q, b = [0.0, 0.0], 100.0
    new_q, cost = lmsr_buy(q, b, 0, 10)
    assert cost == pytest.approx(lmsr_cost(new_q, b) - lmsr_cost(q, b))
    assert 0 < cost < 10
    assert lmsr_prices(new_q, b)[0] > 0.5
    back_q, refund = lmsr_buy(new_q, b, 0, -10)
    assert back_q == q and refund == pytest.approx(-cost)


def test_max_loss_bound():
    b = 100.0
    q, _ = lmsr_buy([0.0, 0.0], b, 0, 10_000)
    paid = lmsr_cost(q, b) - lmsr_cost([0.0, 0.0], b)
    assert 10_000 - paid <= lmsr_max_loss(b) + 1e-6
    assert lmsr_max_loss(b) == pytest.approx(b * math.log(2))


def test_cost_is_stable_for_large_quantities():
    assert math.isfinite(lmsr_cost([1e6, 0.0], 10))


def test_settles_on_median_within_window():
    frames = [frame(10_000 + dt, cars) for dt, cars in [(-50, 39), (-10, 41), (0, 42), (30, 38), (55, 45)]]
    frames.append(frame(10_000 + 61, 0))
    result = settle(MARKET, frames)
    assert result["status"] == "yes" and result["value"] == 41
    assert result["frames_used"] == 5


def test_low_confidence_frames_are_ignored():
    frames = [frame(10_000 + dt, 45) for dt in (-20, 0, 20)] + [frame(10_000 + dt, 0, 0.3) for dt in (-5, 5, 10, 15)]
    result = settle(MARKET, frames)
    assert result["status"] == "yes" and result["frames_used"] == 3 and result["frames_rejected"] == 4


def test_void_without_enough_good_frames():
    frames = [frame(10_000, 45), frame(10_010, 45, 0.2), frame(10_200, 45)]
    result = settle(MARKET, frames)
    assert result["status"] == "void" and result["value"] is None
    assert "stakes returned" in result["reason"]


def test_unaligned_frames_without_zone_values_do_not_count():
    frames = [{"t": 10_000 + dt, "confidence": 0.9, "counts": {"car": 45}, "zones": {}} for dt in (-10, 0, 10)]
    assert settle(MARKET, frames)["status"] == "void"


def good_proposal(**overrides) -> dict:
    base = {"zone": "lot-a", "field": "car", "comparator": ">=", "threshold": 40, "close_in_minutes": 30,
            "open_prob": 0.5, "rationale": "median 38"}
    return {**base, **overrides}


@pytest.mark.parametrize("overrides, problem", [
    ({"zone": "lot-z"}, "unknown zone"),
    ({"zone": "water", "field": "car"}, "person counts"),
    ({"field": "occupancy", "threshold": 1.5}, "0..1"),
    ({"threshold": 60}, "capacity"),
    ({"zone": None, "threshold": 500}, "far above"),
    ({"close_in_minutes": 5}, "minutes out"),
    ({"open_prob": 0.99}, "probability"),
    ({"comparator": "=="}, "comparator"),
])
def test_proposal_guardrails(overrides, problem):
    market, why = validate_proposal(good_proposal(**overrides), ZONES, 45, 0.0, [])
    assert market is None and problem in why


def test_valid_proposal_builds_market_and_rejects_duplicate():
    market, why = validate_proposal(good_proposal(), ZONES, 45, 0.0, [])
    assert why is None
    assert market["close_t"] == 1800 and market["question"].startswith("40 or more cars in lot-a")
    assert lmsr_prices(market["q"], market["b"])[0] == pytest.approx(0.5)
    _, dup = validate_proposal(good_proposal(), ZONES, 45, 0.0, [market])
    assert dup == "duplicate of an open market"


def test_engine_only_agent_proposes_and_settles():
    agent = MarketAgent(claude=None, site={"zones": list(ZONES.values())})
    history = [frame(t, 30 + (t // 60) % 3) for t in range(0, 1200, 2)]
    records = agent.propose(history, now=1200.0)
    assert records and records[0]["accepted"] and records[0]["proposed_by"] == "engine"
    close = agent.open[0]["close_t"]
    later = history + [frame(close + dt, 31) for dt in range(-30, 31, 2)]
    settled = agent.settle_due(later, close + 61)
    assert settled[0]["status"] in ("yes", "no") and settled[0]["explained_by"].startswith("engine")
    assert agent.open == []

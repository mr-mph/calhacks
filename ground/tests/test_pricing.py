import pytest

from agents.pricing import PricePolicy, PricingAgent, ZoneState, decide, step_price, target_price

POLICY = PricePolicy()


def obs(t: float, occupancy: float | None, confidence: float = 0.9, aligned: bool = True) -> dict:
    zone = {"car": 10} if occupancy is None else {"car": 10, "occupancy": occupancy}
    return {"t": t, "session": "s", "frame": f"stills/{t}.jpg", "aligned": aligned, "confidence": confidence,
            "zones": {"lot-a": zone}}


@pytest.mark.parametrize("occ", [0.0, 0.3, 0.6])
def test_base_price_at_or_below_sixty_percent(occ):
    assert target_price(occ, POLICY) == POLICY.base


def test_target_rises_monotonically_to_cap():
    targets = [target_price(o / 10, POLICY) for o in range(6, 11)]
    assert targets == sorted(targets)
    assert targets[-1] == POLICY.cap
    assert target_price(1.4, POLICY) == POLICY.cap


def test_step_never_exceeds_25_percent():
    for price in (2.0, 3.0, 3.33, 7.77):
        for target in (0.5, 2.5, 50.0):
            new = step_price(price, target, POLICY)
            assert abs(new - price) <= price * POLICY.max_step + 1e-9


def test_floor_and_ceiling():
    assert step_price(2.1, 0.0, POLICY) == POLICY.floor
    assert step_price(14.5, 100.0, POLICY) == POLICY.ceiling


def test_low_confidence_holds():
    d = decide("lot-a", obs(0, 0.95, confidence=0.4), ZoneState(3.0), POLICY)
    assert d["action"] == "hold" and d["code"] == "low_confidence"
    assert d["new_price"] == 3.0


def test_unaligned_frame_holds():
    d = decide("lot-a", obs(0, 0.95, aligned=False), ZoneState(3.0), POLICY)
    assert d["code"] == "not_aligned"


def test_rate_limit_one_change_per_five_minutes():
    state = ZoneState(3.0, last_change_t=1000.0)
    assert decide("lot-a", obs(1000 + 299, 0.95), state, POLICY)["code"] == "rate_limited"
    assert decide("lot-a", obs(1000 + 300, 0.95), state, POLICY)["action"] == "raise"


def test_decision_records_inputs():
    d = decide("lot-a", obs(0, 0.9), ZoneState(3.0), POLICY)
    assert d["action"] == "raise"
    assert d["new_price"] == 3.75
    assert d["inputs"]["occupancy"] == 0.9 and d["inputs"]["confidence"] == 0.9
    assert d["policy"]["max_step"] == 0.25


def test_agent_logs_changes_and_only_new_hold_reasons():
    agent = PricingAgent(claude=None)
    logged = []
    for i in range(10):
        logged += agent.step(obs(i * 2.0, 0.95), ["lot-a"])
    assert [d["action"] for d in logged] == ["raise", "hold"]
    assert logged[0]["explained_by"].startswith("engine")
    assert "3.00" in logged[0]["explanation"] and "3.75" in logged[0]["explanation"]
    assert agent.prices() == {"lot-a": 3.75}


def test_price_falls_when_lot_empties():
    agent = PricingAgent(claude=None)
    agent.step(obs(0, 1.0), ["lot-a"])
    agent.step(obs(400, 1.0), ["lot-a"])
    high = agent.prices()["lot-a"]
    changes = agent.step(obs(800, 0.2), ["lot-a"])
    assert changes[0]["action"] == "lower"
    assert agent.prices()["lot-a"] < high

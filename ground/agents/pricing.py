"""Surge pricing for lot zones. The engine sets every number; Claude only writes the explanation of a change.

Rules (docs/architecture.md section 4): base price below 60% occupancy, rising linearly to the cap at 100%;
at most one change per 5 minutes; at most 25% per step; never outside floor and ceiling; hold when the frame's
confidence is below 0.5 or the frame did not align.
"""
import json
import math
from dataclasses import asdict, dataclass, replace

from agents.llm import TEXT_MODEL, Claude

EPSILON = 1e-9


@dataclass(frozen=True)
class PricePolicy:
    base: float = 3.00
    cap: float = 12.00
    floor: float = 2.00
    ceiling: float = 15.00
    surge_from: float = 0.60
    min_interval_s: float = 300.0
    max_step: float = 0.25
    min_confidence: float = 0.5


@dataclass(frozen=True)
class ZoneState:
    price: float
    last_change_t: float | None = None
    last_logged_code: str | None = None


def target_price(occupancy: float, policy: PricePolicy) -> float:
    occ = min(max(occupancy, 0.0), 1.0)
    if occ <= policy.surge_from:
        return policy.base
    surge = (occ - policy.surge_from) / (1.0 - policy.surge_from)
    return policy.base + (policy.cap - policy.base) * surge


def _toward(price: float, value: float) -> float:
    """Round to cents without overshooting the step limit."""
    cents = value * 100
    return (math.floor(cents + EPSILON) if value > price else math.ceil(cents - EPSILON)) / 100


def step_price(price: float, target: float, policy: PricePolicy) -> float:
    limit = price * policy.max_step
    stepped = price + min(max(target - price, -limit), limit)
    bounded = min(max(stepped, policy.floor), policy.ceiling)
    return _toward(price, bounded)


def _hold(obs: dict, zone: str, policy: PricePolicy) -> tuple[str, str] | None:
    if not obs.get("aligned"):
        return "not_aligned", "hold: frame did not align to the site, zones unknown"
    if obs["confidence"] < policy.min_confidence:
        return "low_confidence", f"hold: low confidence {obs['confidence']:.2f} < {policy.min_confidence:.2f}"
    if "occupancy" not in obs.get("zones", {}).get(zone, {}):
        return "no_reading", "hold: no occupancy reading for this zone"
    return None


def decide(zone: str, obs: dict, state: ZoneState, policy: PricePolicy) -> dict:
    """Pure: one pricing decision for one lot zone, with every input that produced it."""
    occupancy = obs.get("zones", {}).get(zone, {}).get("occupancy")
    target = target_price(occupancy, policy) if occupancy is not None else None
    decision = {
        "agent": "pricing", "t": obs["t"], "session": obs["session"], "zone": zone, "frame": obs["frame"],
        "action": "hold", "old_price": state.price, "new_price": state.price,
        "target_price": round(target, 2) if target is not None else None,
        "inputs": {"occupancy": occupancy, "confidence": obs["confidence"], "aligned": obs.get("aligned"),
                   "cars": obs.get("zones", {}).get(zone, {}).get("car"), "last_change_t": state.last_change_t},
        "policy": asdict(policy),
    }
    hold = _hold(obs, zone, policy)
    if hold:
        return {**decision, "code": hold[0], "reason": hold[1]}
    if abs(target - state.price) < 0.01:
        return {**decision, "code": "at_target", "reason": "hold: price already at target"}
    since = obs["t"] - state.last_change_t if state.last_change_t is not None else None
    if since is not None and since < policy.min_interval_s:
        return {**decision, "code": "rate_limited",
                "reason": f"hold: last change {since:.0f} s ago, minimum {policy.min_interval_s:.0f} s"}
    new_price = step_price(state.price, target, policy)
    if new_price == state.price:
        return {**decision, "code": "bounded", "reason": "hold: price at floor or ceiling"}
    action = "raise" if new_price > state.price else "lower"
    limited = " (limited by the 25% step or the floor/ceiling)" if abs(new_price - target) >= 0.01 else ""
    reason = f"{action}: occupancy {occupancy:.0%} sets target ${target:.2f}{limited}"
    return {**decision, "action": action, "code": action, "new_price": new_price, "reason": reason}


def engine_explanation(decision: dict) -> str:
    occ = decision["inputs"]["occupancy"]
    return (f"The price for {decision['zone']} moved from ${decision['old_price']:.2f} to ${decision['new_price']:.2f} "
            f"because the balloon counted the lot {occ:.0%} full (frame confidence "
            f"{decision['inputs']['confidence']:.2f}). Prices start rising above "
            f"{decision['policy']['surge_from']:.0%} full and move at most 25% every 5 minutes.")


EXPLAIN_SYSTEM = (
    "You explain parking price changes to drivers and to judges auditing an autonomous pricing agent. "
    "Write one short paragraph (2 to 4 sentences, plain text). Use only the numbers in the decision record; "
    "never invent, round differently, or predict numbers. Say what the balloon observed, which rule applied, "
    "and how sure the observation is."
)


class PricingAgent:
    def __init__(self, claude: Claude | None, policy: PricePolicy = PricePolicy()):
        self.claude = claude
        self.policy = policy
        self.states: dict[str, ZoneState] = {}

    def _explain(self, decision: dict) -> dict:
        reply = None
        if self.claude:
            record = json.dumps({k: decision[k] for k in ("zone", "old_price", "new_price", "target_price",
                                                         "reason", "inputs", "policy")})
            reply = self.claude.ask(purpose="pricing", model=TEXT_MODEL, system=EXPLAIN_SYSTEM, effort="low",
                                    max_tokens=1200, content=[{"type": "text", "text": record}])
        if reply and reply.text:
            return {**decision, "explanation": reply.text, "explained_by": reply.model}
        skipped = reply.skipped if reply else "engine only"
        return {**decision, "explanation": engine_explanation(decision), "explained_by": f"engine ({skipped})"}

    def step(self, obs: dict, lot_zones: list[str]) -> list[dict]:
        """Decisions worth logging: every change, and a hold only when its reason code differs from the last one logged."""
        logged = []
        for zone in lot_zones:
            state = self.states.get(zone, ZoneState(price=self.policy.base))
            decision = decide(zone, obs, state, self.policy)
            if decision["action"] != "hold":
                self.states[zone] = ZoneState(decision["new_price"], obs["t"], decision["code"])
                logged.append(self._explain(decision))
                continue
            if decision["code"] != state.last_logged_code:
                self.states[zone] = replace(state, last_logged_code=decision["code"])
                logged.append(decision)
        return logged

    def prices(self) -> dict[str, float]:
        return {zone: s.price for zone, s in self.states.items()}

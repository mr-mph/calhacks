"""Binary prediction markets on counts the balloon can settle.

LMSR helpers are pure functions on plain lists so the Spacetime module can mirror them line for line.
Settlement: median of the observations within +/-60 s of close whose confidence is at least 0.5; too few good
frames voids the market. Claude proposes markets and explains settlements; the engine validates every proposal
and computes every settlement value.
"""
import json
import math
import statistics
from collections.abc import Sequence
from datetime import datetime

from agents.llm import TEXT_MODEL, Claude

SETTLE_WINDOW_S = 60.0
MIN_SETTLE_CONFIDENCE = 0.5
MIN_SETTLE_FRAMES = 3
COMPARATORS = {">=": "or more", ">": "more than", "<=": "or fewer", "<": "fewer than"}
FIELDS = ("car", "person", "occupancy")
LOT_FIELDS = ("car", "occupancy")
MIN_CLOSE_MIN = 10
MAX_CLOSE_MIN = 360
PROB_RANGE = (0.05, 0.95)
DEFAULT_B = 100.0
MAX_PROPOSALS = 3
THRESHOLD_HEADROOM = 3.0


def lmsr_cost(q: Sequence[float], b: float) -> float:
    top = max(q)
    return top + b * math.log(sum(math.exp((qi - top) / b) for qi in q))


def lmsr_prices(q: Sequence[float], b: float) -> list[float]:
    top = max(q)
    weights = [math.exp((qi - top) / b) for qi in q]
    total = sum(weights)
    return [w / total for w in weights]


def lmsr_buy(q: Sequence[float], b: float, outcome: int, shares: float) -> tuple[list[float], float]:
    """Returns (new quantities, cost charged). Negative shares sell back."""
    new_q = [qi + shares if i == outcome else qi for i, qi in enumerate(q)]
    return new_q, lmsr_cost(new_q, b) - lmsr_cost(q, b)


def lmsr_opening_q(prob_yes: float, b: float) -> list[float]:
    """[yes, no] quantities that open the market at prob_yes, both non-negative."""
    logit = b * math.log(prob_yes / (1.0 - prob_yes))
    return [max(logit, 0.0), max(-logit, 0.0)]


def lmsr_max_loss(b: float, outcomes: int = 2) -> float:
    return b * math.log(outcomes)


def metric_value(obs: dict, zone: str | None, field: str) -> float | None:
    if zone is None:
        return obs.get("counts", {}).get(field)
    return obs.get("zones", {}).get(zone, {}).get(field)


def resolves_yes(value: float, comparator: str, threshold: float) -> bool:
    return {">=": value >= threshold, ">": value > threshold,
            "<=": value <= threshold, "<": value < threshold}[comparator]


def settle(market: dict, observations: Sequence[dict], window_s: float = SETTLE_WINDOW_S,
           min_confidence: float = MIN_SETTLE_CONFIDENCE, min_frames: int = MIN_SETTLE_FRAMES) -> dict:
    close = market["close_t"]
    in_window = [o for o in observations if abs(o["t"] - close) <= window_s]
    good = [o for o in in_window if o.get("confidence", 0.0) >= min_confidence]
    values = [v for v in (metric_value(o, market.get("zone"), market["field"]) for o in good) if v is not None]
    result = {
        "agent": "markets", "kind": "settlement", "market_id": market["id"], "question": market["question"],
        "close_t": close, "window_s": window_s, "frames_in_window": len(in_window),
        "frames_used": len(values), "frames_rejected": len(in_window) - len(values), "min_frames": min_frames,
    }
    if len(values) < min_frames:
        reason = f"void: {len(values)} good frames within {window_s:.0f} s of close, need {min_frames}; stakes returned"
        return {**result, "status": "void", "value": None, "reason": reason}
    value = statistics.median(values)
    outcome = "yes" if resolves_yes(value, market["comparator"], market["threshold"]) else "no"
    reason = f"{outcome}: median {value:g} over {len(values)} frames vs {market['comparator']} {market['threshold']:g}"
    return {**result, "status": outcome, "value": value, "reason": reason}


def _clock(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%-I:%M %p")


def market_question(zone: str | None, field: str, comparator: str, threshold: float, close_t: float) -> str:
    where = f" in {zone}" if zone else " in view"
    if field == "occupancy":
        return f"{zone or 'The lot'} {COMPARATORS[comparator]} {threshold:.0%} full at {_clock(close_t)}"
    noun = "cars" if field == "car" else "people"
    return f"{threshold:g} {COMPARATORS[comparator]} {noun}{where} at {_clock(close_t)}"


def _check_target(p: dict, zones: dict[str, dict]) -> str | None:
    zone, field = p.get("zone"), p.get("field")
    if field not in FIELDS:
        return f"field must be one of {FIELDS}"
    if zone is None:
        return "occupancy needs a lot zone" if field == "occupancy" else None
    if zone not in zones:
        return f"unknown zone {zone!r}"
    kind = zones[zone]["kind"]
    if kind == "lot" and field not in LOT_FIELDS:
        return f"lot zones settle on {LOT_FIELDS}"
    if kind != "lot" and field != "person":
        return f"{kind} zones settle on person counts"
    return None


def _check_numbers(p: dict, history_max: float | None, zones: dict[str, dict]) -> str | None:
    if p.get("comparator") not in COMPARATORS:
        return f"comparator must be one of {list(COMPARATORS)}"
    threshold = p.get("threshold")
    if not isinstance(threshold, (int, float)) or threshold < 0:
        return "threshold must be a non-negative number"
    if p["field"] == "occupancy" and threshold > 1:
        return "occupancy threshold must be within 0..1"
    capacity = zones.get(p.get("zone"), {}).get("capacity")
    if p["field"] == "car" and capacity and threshold > capacity:
        return f"threshold above lot capacity {capacity}"
    if p["field"] != "occupancy" and history_max is not None and threshold > THRESHOLD_HEADROOM * history_max + 10:
        return f"threshold far above anything observed (max {history_max:g})"
    close_in = p.get("close_in_minutes")
    if not isinstance(close_in, int) or not MIN_CLOSE_MIN <= close_in <= MAX_CLOSE_MIN:
        return f"close must be {MIN_CLOSE_MIN} to {MAX_CLOSE_MIN} minutes out"
    prob = p.get("open_prob")
    if not isinstance(prob, (int, float)) or not PROB_RANGE[0] <= prob <= PROB_RANGE[1]:
        return f"opening probability must be within {PROB_RANGE}"
    return None


def validate_proposal(p: dict, zones: dict[str, dict], history_max: float | None, now: float,
                      existing: Sequence[dict]) -> tuple[dict | None, str | None]:
    """Returns (market, None) when the proposal passes every guardrail, else (None, why it was rejected)."""
    problem = _check_target(p, zones) or _check_numbers(p, history_max, zones)
    if problem:
        return None, problem
    close_t = round(now + p["close_in_minutes"] * 60)
    key = (p.get("zone"), p["field"], p["comparator"], float(p["threshold"]), close_t)
    if any((m.get("zone"), m["field"], m["comparator"], float(m["threshold"]), m["close_t"]) == key for m in existing):
        return None, "duplicate of an open market"
    question = market_question(p.get("zone"), p["field"], p["comparator"], p["threshold"], close_t)
    market = {
        "id": f"{p.get('zone') or 'all'}-{p['field']}-{p['comparator']}{p['threshold']:g}-{close_t}",
        "question": question, "zone": p.get("zone"), "field": p["field"], "comparator": p["comparator"],
        "threshold": p["threshold"], "close_t": close_t, "open_prob": p["open_prob"], "b": DEFAULT_B,
        "q": lmsr_opening_q(p["open_prob"], DEFAULT_B), "rationale": p.get("rationale", ""),
    }
    return market, None


def history_summary(observations: Sequence[dict], zones: dict[str, dict]) -> dict:
    good = [o for o in observations if o.get("confidence", 0.0) >= MIN_SETTLE_CONFIDENCE]
    series: dict[str, list[float]] = {}
    for o in good:
        for field in ("car", "person"):
            series.setdefault(f"all.{field}", []).append(o["counts"].get(field, 0))
        for zone, stats in o.get("zones", {}).items():
            for field, v in stats.items():
                series.setdefault(f"{zone}.{field}", []).append(v)
    stats = {k: {"n": len(v), "min": min(v), "median": statistics.median(v), "max": max(v), "last": v[-1]}
             for k, v in series.items()}
    span = (good[0]["t"], good[-1]["t"]) if good else None
    return {"frames": len(observations), "good_frames": len(good), "span_t": span, "series": stats,
            "zones": {z: {"kind": d["kind"], "capacity": d.get("capacity")} for z, d in zones.items()}}


PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {"markets": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "zone": {"type": ["string", "null"]},
            "field": {"type": "string", "enum": list(FIELDS)},
            "comparator": {"type": "string", "enum": list(COMPARATORS)},
            "threshold": {"type": "number"},
            "close_in_minutes": {"type": "integer"},
            "open_prob": {"type": "number"},
            "rationale": {"type": "string"},
        },
        "required": ["zone", "field", "comparator", "threshold", "close_in_minutes", "open_prob", "rationale"],
        "additionalProperties": False,
    }}},
    "required": ["markets"],
    "additionalProperties": False,
}

PROPOSE_SYSTEM = (
    "You are the market maker for binary prediction markets settled by a tethered balloon camera. "
    f"Propose up to {MAX_PROPOSALS} markets on counts the balloon can observe at a single moment: cars or "
    "occupancy in a lot zone, people in a beach, water or crossing zone, or cars/people in the whole view "
    "(zone null). Each settles on the median of frames within 60 s of close, so pick thresholds near the "
    "observed medians so the outcome is genuinely uncertain, and set open_prob to your honest probability "
    f"(between {PROB_RANGE[0]} and {PROB_RANGE[1]}). Close {MIN_CLOSE_MIN} to {MAX_CLOSE_MIN} minutes from now. "
    "Never propose markets about identifiable people. Keep each rationale to one sentence that cites the history."
)

EXPLAIN_SYSTEM = (
    "You explain prediction market settlements to traders. Write 2 to 3 plain sentences. Use only the numbers "
    "in the settlement record. If the market is void, say why and that stakes are returned."
)


def engine_proposals(summary: dict) -> list[dict]:
    """Deterministic fallback: one market per lot at its median car count, 30 minutes out, even odds."""
    proposals = []
    for zone, info in summary["zones"].items():
        stats = summary["series"].get(f"{zone}.car")
        if info["kind"] != "lot" or not stats:
            continue
        proposals.append({"zone": zone, "field": "car", "comparator": ">=", "threshold": max(1, round(stats["median"])),
                          "close_in_minutes": 30, "open_prob": 0.5, "rationale": "engine: median of observed cars"})
    return proposals[:MAX_PROPOSALS]


class MarketAgent:
    def __init__(self, claude: Claude | None, site: dict | None):
        self.claude = claude
        self.zones = {z["id"]: z for z in (site or {}).get("zones", [])}
        self.open: list[dict] = []

    def _raw_proposals(self, summary: dict, now: float) -> tuple[list[dict], str]:
        if self.claude:
            prompt = json.dumps({"now": _clock(now), "history": summary,
                                 "open_markets": [m["question"] for m in self.open]})
            reply = self.claude.ask(purpose="markets.propose", model=TEXT_MODEL, system=PROPOSE_SYSTEM,
                                    effort="medium", max_tokens=3000, schema=PROPOSAL_SCHEMA,
                                    content=[{"type": "text", "text": prompt}])
            if reply.data:
                return reply.data["markets"][:MAX_PROPOSALS], reply.model
            return engine_proposals(summary), f"engine ({reply.skipped})"
        return engine_proposals(summary), "engine"

    def propose(self, observations: Sequence[dict], now: float) -> list[dict]:
        """Decision records for every proposal, accepted or rejected; accepted ones join self.open."""
        summary = history_summary(observations, self.zones)
        history_max = max((s["max"] for k, s in summary["series"].items() if not k.endswith("occupancy")), default=None)
        raw, proposer = self._raw_proposals(summary, now)
        records = []
        for p in raw:
            market, problem = validate_proposal(p, self.zones, history_max, now, self.open)
            if market:
                self.open = [*self.open, market]
            records.append({"agent": "markets", "kind": "proposal", "t": now, "proposed_by": proposer,
                            "proposal": p, "accepted": market is not None, "market": market, "rejected_because": problem})
        return records

    def settle_due(self, observations: Sequence[dict], now: float) -> list[dict]:
        due = [m for m in self.open if now >= m["close_t"] + SETTLE_WINDOW_S]
        self.open = [m for m in self.open if m not in due]
        return [self.explain(settle(m, observations)) for m in due]

    def explain(self, settlement: dict) -> dict:
        reply = None
        if self.claude:
            reply = self.claude.ask(purpose="markets.explain", model=TEXT_MODEL, system=EXPLAIN_SYSTEM,
                                    effort="low", max_tokens=1000,
                                    content=[{"type": "text", "text": json.dumps(settlement)}])
        if reply and reply.text:
            return {**settlement, "explanation": reply.text, "explained_by": reply.model}
        skipped = reply.skipped if reply else "engine only"
        return {**settlement, "explanation": settlement["reason"], "explained_by": f"engine ({skipped})"}

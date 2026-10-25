"""Claude access for the agents: key loading, a per-session spend guard, and one call helper.

Agents call Claude only on events (a price change, a settlement, a beach-alert candidate), never per frame.
When there is no key, or the session's budget is spent, `ask` returns a skipped Reply and the agent falls back
to its deterministic wording.
"""
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import anthropic

log = logging.getLogger("agents.llm")

TEXT_MODEL = os.environ.get("BALLOON_TEXT_MODEL", "claude-haiku-5-5")
VISION_MODEL = os.environ.get("BALLOON_VISION_MODEL", "claude-sonnet-5-5")
DEFAULT_CAP_USD = 10.0
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
CHARS_PER_TOKEN = 3.5
IMAGE_PIXELS_PER_TOKEN = 750

PRICES_PER_MTOK = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
}
UNKNOWN_MODEL_PRICE = (10.00, 50.00)


def load_api_key(name: str = "ANTHROPIC_API_KEY") -> str | None:
    key = os.environ.get(name)
    if key:
        return key
    env_file = Path(os.environ.get("BALLOON_ENV_FILE", DEFAULT_ENV_FILE))
    if not env_file.is_file():
        return None
    from dotenv import dotenv_values
    return dotenv_values(env_file).get(name) or None


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES_PER_MTOK.get(model, UNKNOWN_MODEL_PRICE)
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


def estimate_input_tokens(content: list[dict], system: str) -> int:
    tokens = len(system) / CHARS_PER_TOKEN
    for block in content:
        if block["type"] == "text":
            tokens += len(block["text"]) / CHARS_PER_TOKEN
        elif block["type"] == "image":
            width, height = block.get("_size", (1024, 1024))
            tokens += width * height / IMAGE_PIXELS_PER_TOKEN
    return int(tokens) + 1


class SpendLedger:
    """Running USD total per session in ground/out/spend.json; refuses calls past the cap."""

    def __init__(self, path: str | Path, session: str, cap_usd: float):
        self.path = Path(path)
        self.session = session
        self.cap_usd = cap_usd

    def _read(self) -> dict:
        if not self.path.is_file():
            return {"sessions": {}}
        with open(self.path) as f:
            return json.load(f)

    def spent(self) -> float:
        return self._read()["sessions"].get(self.session, {}).get("usd", 0.0)

    def allows(self, estimate_usd: float) -> bool:
        return self.spent() + estimate_usd <= self.cap_usd

    def record(self, purpose: str, model: str, usd: float, refused: bool = False) -> None:
        data = self._read()
        entry = data["sessions"].get(self.session, {"usd": 0.0, "calls": 0, "refused": 0, "by_purpose": {}})
        by_purpose = dict(entry["by_purpose"])
        by_purpose[purpose] = round(by_purpose.get(purpose, 0.0) + usd, 6)
        updated = {
            "usd": round(entry["usd"] + usd, 6),
            "calls": entry["calls"] + (0 if refused else 1),
            "refused": entry["refused"] + (1 if refused else 0),
            "by_purpose": by_purpose,
            "cap_usd": self.cap_usd,
            "last_model": model,
            "updated_t": time.time(),
        }
        sessions = {**data["sessions"], self.session: updated}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"sessions": sessions}, indent=1))
        tmp.replace(self.path)


@dataclass(frozen=True)
class Reply:
    text: str | None = None
    data: dict | None = None
    model: str | None = None
    usd: float = 0.0
    skipped: str | None = None


class Claude:
    def __init__(self, ledger: SpendLedger, api_key: str | None = None):
        self.ledger = ledger
        key = api_key or load_api_key()
        self.client = anthropic.Anthropic(api_key=key) if key else None
        self.mode = "claude" if self.client else "engine only (no ANTHROPIC_API_KEY)"

    @property
    def available(self) -> bool:
        return self.client is not None

    def ask(self, *, purpose: str, model: str, system: str, content: list[dict], max_tokens: int = 2000,
            effort: str = "low", schema: dict | None = None) -> Reply:
        if not self.client:
            return Reply(skipped=self.mode)
        worst_case = cost_usd(model, estimate_input_tokens(content, system), max_tokens)
        if not self.ledger.allows(worst_case):
            self.ledger.record(purpose, model, 0.0, refused=True)
            log.warning("spend cap $%.2f reached for %s; %s runs engine only", self.ledger.cap_usd,
                        self.ledger.session, purpose)
            return Reply(skipped=f"spend cap ${self.ledger.cap_usd:.2f} reached")
        output_config: dict = {"effort": effort}
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        api_content = [{k: v for k, v in block.items() if not k.startswith("_")} for block in content]
        try:
            response = self.client.beta.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": api_content}],
                output_config=output_config, betas=[FALLBACK_BETA], fallbacks="default",
            )
        except anthropic.APIError as e:
            log.warning("%s: Claude call failed (%s)", purpose, type(e).__name__)
            return Reply(skipped=f"API error: {type(e).__name__}")
        usage = response.usage
        input_tokens = usage.input_tokens + (usage.cache_creation_input_tokens or 0) + (usage.cache_read_input_tokens or 0)
        usd = cost_usd(response.model, input_tokens, usage.output_tokens)
        self.ledger.record(purpose, response.model, usd)
        if response.stop_reason == "refusal":
            return Reply(model=response.model, usd=usd, skipped="model declined")
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if not schema:
            return Reply(text=text, model=response.model, usd=usd)
        try:
            return Reply(text=text, data=json.loads(text), model=response.model, usd=usd)
        except json.JSONDecodeError:
            return Reply(model=response.model, usd=usd, skipped="unparseable JSON")


def spend_ledger(out_root: str | Path, session: str) -> SpendLedger:
    cap = float(os.environ.get("BALLOON_SPEND_CAP_USD", DEFAULT_CAP_USD))
    return SpendLedger(Path(out_root) / "spend.json", session, cap)

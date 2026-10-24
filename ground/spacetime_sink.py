"""Send live counts, new markets and settlements to the Spacetime market module (market/README.md) over HTTP.

Every write only queues work; one background thread makes the reducer calls in order, so a slow or unreachable
Spacetime never stalls the station. Counts are throttled per zone and metric: posted when the value changes, or
every 10 s otherwise. The market agent uses its own oracle identity, separate from the station's.

Config: ~/.config/balloon/spacetime.json (chmod 600)
    {"host", "database", "oracle_secret", "station_identity", "station_token", "agent_token"}
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger("spacetime_sink")

CONFIG_PATH = Path.home() / ".config/balloon/spacetime.json"
HTTP_TIMEOUT_S = 10.0
POST_EVERY_S = 10.0
WHOLE_VIEW = "whole-view"
MARKET_B = 100
MAX_EXPLANATION = 1000
MAX_RATIONALE = 300
DEFAULT_RATIONALE = "Proposed by the market agent from today's counts."
METRICS = {"car": ("car_count", 1.0), "person": ("person_count", 1.0), "occupancy": ("occupancy_pct", 100.0)}


class SpacetimeRejected(RuntimeError):
    pass


def load_config(path: Path = CONFIG_PATH) -> dict[str, str]:
    cfg = json.loads(path.read_text())
    missing = [k for k in ("host", "database", "station_token") if not cfg.get(k)]
    if missing:
        raise ValueError(f"{path} is missing {', '.join(missing)}")
    if not cfg["host"].startswith(("https://", "http://127.0.0.1", "http://localhost")):
        raise ValueError(f"{path}: host must be https (tokens travel in headers)")
    return cfg


def sql_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


class SpacetimeClient:
    def __init__(self, host: str, database: str, token: str | None = None, http: requests.Session | None = None):
        self.base = host.rstrip("/")
        self.database = database
        self.token = token
        self.http = http or requests.Session()

    def new_token(self) -> str:
        response = self.http.post(f"{self.base}/v1/identity", timeout=HTTP_TIMEOUT_S)
        response.raise_for_status()
        return response.json()["token"]

    def call(self, reducer: str, *args: Any) -> None:
        response = self.http.post(
            f"{self.base}/v1/database/{self.database}/call/{reducer}",
            data=json.dumps(list(args)),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            timeout=HTTP_TIMEOUT_S,
        )
        if response.status_code != 200:
            raise SpacetimeRejected(f"{reducer} rejected ({response.status_code}): {response.text[:300]}")

    def sql(self, query: str) -> list[dict]:
        response = self.http.post(f"{self.base}/v1/database/{self.database}/sql", data=query, timeout=HTTP_TIMEOUT_S)
        response.raise_for_status()
        table = response.json()[0]
        names = [e["name"]["some"] for e in table["schema"]["elements"]]
        return [dict(zip(names, row)) for row in table["rows"]]


def ensure_agent_token(cfg: dict, path: Path, client: SpacetimeClient) -> str:
    """The market agent's own oracle identity, created and claimed once, then kept in the config file."""
    if cfg.get("agent_token"):
        return cfg["agent_token"]
    if not cfg.get("oracle_secret"):
        log.warning("no oracle_secret in %s; the market agent shares the station identity", path)
        return cfg["station_token"]
    token = client.new_token()
    secret = cfg["oracle_secret"]
    try:
        SpacetimeClient(client.base, client.database, token, client.http).call("claim_oracle", secret)
    except SpacetimeRejected as e:
        raise SpacetimeRejected(str(e).replace(secret, "***")) from None
    cfg["agent_token"] = token
    os.chmod(path, 0o600)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_CREAT, 0o600), "w") as f:
        f.write(json.dumps(cfg, indent=2))
    log.info("market agent claimed its own oracle identity")
    return token


def market_target(zone: str | None, field: str) -> tuple[str, str, float]:
    metric, scale = METRICS[field]
    return zone or WHOLE_VIEW, metric, scale


def readings(obs: dict) -> list[tuple[str, str, float]]:
    """(zone, metric, value) for every count a market can settle on: each zone's fields plus the whole view."""
    out = []
    for zone, stats in sorted(obs.get("zones", {}).items()):
        for field, value in sorted(stats.items()):
            if field in METRICS:
                _, metric, scale = market_target(zone, field)
                out.append((zone, metric, round(value * scale, 1)))
    for field in ("car", "person"):
        if field in obs.get("counts", {}):
            out.append((WHOLE_VIEW, METRICS[field][0], float(obs["counts"][field])))
    return out


class Throttle:
    def __init__(self, every_s: float = POST_EVERY_S, clock: Callable[[], float] = time.monotonic):
        self.every_s = every_s
        self.clock = clock
        self.last: dict[tuple[str, str], tuple[float, float]] = {}

    def due(self, zone: str, metric: str, value: float) -> bool:
        now = self.clock()
        previous = self.last.get((zone, metric))
        if previous and previous[0] == value and now - previous[1] < self.every_s:
            return False
        self.last[(zone, metric)] = (value, now)
        return True


def rationale_text(market: dict) -> str:
    text = (market.get("rationale") or "").strip() or DEFAULT_RATIONALE
    return text[:MAX_RATIONALE]


class SpacetimeSink:
    """write(kind, record) like the other sinks. Observations post counts; market decisions create and settle."""

    def __init__(self, station: SpacetimeClient, agent: SpacetimeClient, throttle: Throttle | None = None):
        self.station = station
        self.agent = agent
        self.throttle = throttle or Throttle()
        self.market_ids: dict[str, tuple[int, float]] = {}
        self.sent = {"observations": 0, "created": 0, "settled": 0, "voided": 0, "failed": 0}
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spacetime")

    @classmethod
    def from_config(cls, path: Path = CONFIG_PATH) -> SpacetimeSink:
        cfg = load_config(path)
        station = SpacetimeClient(cfg["host"], cfg["database"], cfg["station_token"])
        agent_token = ensure_agent_token(cfg, path, station)
        return cls(station, SpacetimeClient(cfg["host"], cfg["database"], agent_token, station.http))

    def write(self, kind: str, record: dict) -> None:
        if kind == "observations":
            self._queue_observation(record)
        elif kind == "decisions" and record.get("agent") == "markets":
            self._queue_market(record)

    def close(self) -> None:
        self._worker.shutdown(wait=True)

    def _submit(self, label: str, fn: Callable[[], None]) -> None:
        def run() -> None:
            try:
                fn()
            except (requests.RequestException, SpacetimeRejected, KeyError, ValueError) as e:
                self.sent["failed"] += 1
                log.warning("spacetime %s failed: %s", label, e)
        self._worker.submit(run)

    def _queue_observation(self, obs: dict) -> None:
        for zone, metric, value in readings(obs):
            if self.throttle.due(zone, metric, value):
                args = (obs["t"], zone, metric, value, obs["confidence"], obs["frame"])
                self._submit("post_observation", lambda a=args: self._post(a))

    def _post(self, args: tuple) -> None:
        self.station.call("post_observation", *args)
        self.sent["observations"] += 1

    def _queue_market(self, record: dict) -> None:
        if record.get("kind") == "proposal" and record.get("accepted"):
            self._submit("create_market", lambda: self._create(record["market"]))
        elif record.get("kind") == "settlement":
            self._submit("settle", lambda: self._settle(record))

    def _create(self, market: dict) -> None:
        zone, metric, scale = market_target(market.get("zone"), market["field"])
        threshold = round(market["threshold"] * scale, 4)
        self.agent.call("create_market", market["question"], zone, metric, market["comparator"], threshold,
                        float(market["close_t"]), MARKET_B, rationale_text(market))
        self.market_ids[market["id"]] = (self._find_id(market["question"], zone, metric, threshold), scale)
        self.sent["created"] += 1

    def _find_id(self, question: str, zone: str, metric: str, threshold: float) -> int:
        rows = self.agent.sql(f"SELECT * FROM market WHERE zone = {sql_quote(zone)} AND metric = {sql_quote(metric)}")
        ids = [r["id"] for r in rows if r["question"] == question and r["threshold"] == threshold
               and r["status"] == "open"]
        if not ids:
            raise KeyError(f"created market {question!r} not found")
        return max(ids)

    def _settle(self, record: dict) -> None:
        known = self.market_ids.pop(record["market_id"], None)
        if known is None:
            log.warning("settlement for a market Spacetime never created: %s", record["market_id"])
            return
        market_id, scale = known
        explanation = (record.get("explanation") or record["reason"])[:MAX_EXPLANATION]
        if record["status"] == "void":
            self.agent.call("void_market", market_id, explanation)
            self.sent["voided"] += 1
            return
        self.agent.call("settle", market_id, record["value"] * scale, explanation)
        self.sent["settled"] += 1

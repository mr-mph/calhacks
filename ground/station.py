"""Ground station loop: stills from the Pi (live) or a session folder (replay) -> observations -> sinks and agents.

    python station.py --replay ~/balloon-data/20261024-153000 --site sites/marina.json --agents
    python station.py --pi http://balloon.local:8080 --site sites/marina.json --agents
"""
import argparse
import csv
import io
import logging
import re
import sys
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import requests

from align import Aligner
from observe import STABILITY_FRAMES, build_observation, load_site, resolve_reference
from sinks import JsonlSink

log = logging.getLogger("station")

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "out"
HISTORY_FRAMES = 3600
FIRST_PROPOSAL_S = 600.0
HTTP_TIMEOUT_S = 5.0
SESSION_NAME = re.compile(r"[\w-]+")
STILL_NAME = re.compile(r"\w[\w.-]*\.jpe?g")


@dataclass(frozen=True)
class Still:
    session: str
    file: str
    t: float
    alt_m: float | None
    tilt_deg: float | None
    jpeg: bytes


def _num(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _valid_row(row: dict) -> bool:
    return bool(STILL_NAME.fullmatch(row.get("file") or "")) and _num(row.get("t_unix")) is not None


def parse_index(text: str) -> list[dict]:
    """Rows with a plain still file name and a timestamp; anything else (including path tricks) is dropped."""
    return [row for row in csv.DictReader(io.StringIO(text)) if _valid_row(row)]


def _still(session: str, row: dict, jpeg: bytes) -> Still:
    return Still(session, row["file"], float(row["t_unix"]), _num(row.get("altitude_m")),
                 _num(row.get("tilt_deg")), jpeg)


def replay_stills(session_dir: Path, every: int = 1) -> Iterator[Still]:
    index = session_dir / "stills" / "index.csv"
    rows = parse_index(index.read_text())[::every]
    for row in rows:
        path = session_dir / "stills" / row["file"]
        if path.is_file():
            yield _still(session_dir.name, row, path.read_bytes())


class PiSource:
    """Polls /api/status for the session, then stills/index.csv, and fetches only stills it has not seen.
    On start it skips the backlog and begins at the newest still."""

    def __init__(self, base_url: str, poll_s: float = 2.0):
        self.base = base_url.rstrip("/")
        self.poll_s = poll_s
        self.http = requests.Session()

    def _get(self, path: str) -> requests.Response:
        response = self.http.get(f"{self.base}{path}", timeout=HTTP_TIMEOUT_S)
        response.raise_for_status()
        return response

    def _new_rows(self, session: str, seen: set[str]) -> list[dict]:
        rows = parse_index(self._get(f"/data/sessions/{session}/stills/index.csv").text)
        if not seen and rows:
            seen.update(r["file"] for r in rows[:-1])
        return [r for r in rows if r["file"] not in seen]

    def __iter__(self) -> Iterator[Still]:
        session, seen = None, set()
        while True:
            try:
                current = self._get("/api/status").json().get("session")
                if current and not SESSION_NAME.fullmatch(current):
                    log.warning("ignoring unexpected session name from the Pi")
                    current = None
                if current != session:
                    session, seen = current, set()
                    log.info("Pi session %s", session)
                for row in self._new_rows(session, seen) if session else []:
                    seen.add(row["file"])
                    yield _still(session, row, self._get(f"/data/sessions/{session}/stills/{row['file']}").content)
            except requests.RequestException as e:
                log.warning("Pi unreachable (%s); retrying in %.0f s", type(e).__name__, self.poll_s)
            time.sleep(self.poll_s)


class Agents:
    def __init__(self, out_root: Path, session: str, site: dict | None, market_every_s: float):
        from agents.alerts import AlertWriter
        from agents.llm import Claude, spend_ledger
        from agents.markets import MarketAgent
        from agents.pricing import PricingAgent

        self.claude = Claude(spend_ledger(out_root, session))
        claude = self.claude if self.claude.available else None
        self.pricing = PricingAgent(claude)
        self.markets = MarketAgent(claude, site)
        self.alerts = AlertWriter(claude, site)
        self.lots = [z["id"] for z in (site or {}).get("zones", []) if z["kind"] == "lot"]
        self.market_every_s = market_every_s
        self.last_proposal_t: float | None = None

    def _proposal_due(self, history: deque) -> bool:
        if not history:
            return False
        now, start = history[-1]["t"], history[0]["t"]
        if self.last_proposal_t is None:
            return now - start >= FIRST_PROPOSAL_S
        return now - self.last_proposal_t >= self.market_every_s

    def run(self, obs: dict, detections: list[dict], image: np.ndarray, history: deque) -> tuple[list, list]:
        decisions = self.pricing.step(obs, self.lots)
        decisions += self.markets.settle_due(history, obs["t"])
        if self._proposal_due(history):
            self.last_proposal_t = obs["t"]
            decisions += self.markets.propose(history, obs["t"])
        alert = self.alerts.check(obs, detections, image)
        return decisions, [alert] if alert else []


class Station:
    def __init__(self, detector, site: dict | None, aligner: Aligner | None, out_root: Path, session: str,
                 agents: Agents | None):
        self.detector = detector
        self.site = site
        self.aligner = aligner
        self.session = session
        self.sink = JsonlSink(out_root, session)
        self.agents = agents
        self.history: deque = deque(maxlen=HISTORY_FRAMES)
        self.recent_counts: deque = deque(maxlen=STABILITY_FRAMES)

    def process(self, still: Still) -> dict | None:
        image = cv2.imdecode(np.frombuffer(still.jpeg, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            log.warning("%s: not a readable JPEG, skipped", still.file)
            return None
        detections = self.detector.detect(image)
        alignment = self.aligner.align(image) if self.aligner else None
        obs = build_observation(t=still.t, session=still.session, frame=f"stills/{still.file}", alt_m=still.alt_m,
                                tilt_deg=still.tilt_deg, model=self.detector.name, detections=detections,
                                site=self.site, alignment=alignment, history=list(self.recent_counts))
        self.recent_counts.append(obs["counts"])
        self.history.append(obs)
        self.sink.write("observations", obs)
        if self.agents:
            decisions, alerts = self.agents.run(obs, detections, image, self.history)
            for record in decisions:
                self.sink.write("decisions", record)
            for record in alerts:
                self.sink.write("alerts", record)
        log.info("%s cars=%d people=%d aligned=%s conf=%.2f", still.file, obs["counts"]["car"],
                 obs["counts"]["person"], obs["aligned"], obs["confidence"])
        return obs

    def close(self) -> None:
        self.sink.close()


def make_aligner(site: dict | None, site_path: Path | None, session_dir: Path | None, mode: str) -> Aligner | None:
    if not site:
        return None
    ref = resolve_reference(site, site_path, session_dir)
    if ref is None:
        raise SystemExit(f"reference frame {site.get('reference_frame')!r} not found next to {site_path} "
                         f"or in the session folder")
    image = cv2.imread(str(ref))
    if image is None:
        raise SystemExit(f"reference frame {ref} is not a readable image")
    return Aligner(image, mode=mode)


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pi", metavar="URL", help="live mode, e.g. http://balloon.local:8080")
    src.add_argument("--replay", metavar="SESSION_DIR", type=Path, help="session folder with stills/index.csv")
    ap.add_argument("--site", type=Path, help="site JSON drawn with sites/editor.html")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output root (default ground/out)")
    ap.add_argument("--weights", help="YOLO weights (default $BALLOON_WEIGHTS or yolo11n.pt)")
    ap.add_argument("--every", type=int, default=1, help="replay: process every Nth still")
    ap.add_argument("--agents", action="store_true", help="run pricing, market and alert agents")
    ap.add_argument("--market-every", type=float, default=30.0, help="minutes between market proposals")
    ap.add_argument("--poll", type=float, default=2.0, help="live: seconds between polls")
    ap.add_argument("--align-mode", choices=("similarity", "homography"), default="similarity")
    return ap.parse_args(argv)


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = parse_args(argv)
    if args.replay and not (args.replay / "stills" / "index.csv").is_file():
        raise SystemExit(f"{args.replay} has no stills/index.csv")
    from infer import Detector

    site = load_site(args.site) if args.site else None
    aligner = make_aligner(site, args.site, args.replay, args.align_mode)
    detector = Detector(args.weights)
    log.info("detector %s on %s", detector.name, detector.device)
    stills = replay_stills(args.replay, args.every) if args.replay else iter(PiSource(args.pi, args.poll))
    station = None
    try:
        for still in stills:
            if station is None or station.session != still.session:
                if station:
                    station.close()
                agents = Agents(args.out, still.session, site, args.market_every * 60) if args.agents else None
                if agents:
                    log.info("agents: %s", agents.claude.mode)
                station = Station(detector, site, aligner, args.out, still.session, agents)
            station.process(still)
    except KeyboardInterrupt:
        log.info("stopped")
    finally:
        if station:
            station.close()
            log.info("wrote %s", station.sink.dir)


if __name__ == "__main__":
    main(sys.argv[1:])

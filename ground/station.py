"""Ground station loop: stills from the Pi (live) or a session folder (replay) -> observations -> sinks and agents.

    python station.py --replay ~/balloon-data/20261024-153000 --site sites/marina.json --agents
    python station.py --pi http://balloon.local:8080 --site sites/marina.json --agents --prod

Convex (live map) and Spacetime (markets) are on whenever their config file exists; --no-convex / --no-spacetime
turn them off.
"""
import argparse
import csv
import io
import logging
import re
import sys
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import numpy as np
import requests

from align import Aligner
from observe import STABILITY_FRAMES, build_observation, load_site, resolve_reference
import convex_sink
import spacetime_sink
from pi_sink import PiDashboardSink
from sinks import JsonlSink, Sink

log = logging.getLogger("station")

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "out"
HISTORY_FRAMES = 3600
FIRST_PROPOSAL_S = 600.0
HTTP_TIMEOUT_S = 5.0
LOOP_GAP_S = 2.0
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


def paced_replay(session_dir: Path, every: int = 1, loop: bool = False, clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep) -> Iterator[Still]:
    """Replays a session as if it were live: timestamps shift so the first still is now, and each still is released
    at its shifted time. Spacetime only accepts current timestamps and market closes in the future."""
    while True:
        start, shift = clock(), None
        for still in replay_stills(session_dir, every):
            shift = start - still.t if shift is None else shift
            t = still.t + shift
            sleep(max(0.0, t - clock()))
            yield replace(still, t=t)
        if not loop or shift is None:
            return
        sleep(LOOP_GAP_S)


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
        from agents.voice import GrokVoice

        self.claude = Claude(spend_ledger(out_root, session))
        self.voice = GrokVoice(self.claude.ledger)
        self.audio_dir = Path(out_root) / session / "audio"
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
        return decisions, [self._voiced(alert)] if alert else []

    def _voiced(self, alert: dict) -> dict:
        """Read the alert aloud once with Grok and keep the MP3 beside the JSONL; the Convex sink uploads it."""
        audio = self.voice.speak(alert)
        if audio is None:
            return alert
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        path = self.audio_dir / f"alert-{alert['t']:.3f}.mp3"
        path.write_bytes(audio)
        return {**alert, "audio": {"file": str(path.resolve()), "voice": self.voice.label, "bytes": len(audio)}}


class Station:
    """One session. Cloud sinks outlive it (they are shared across sessions), so close() only closes the JSONL."""

    def __init__(self, detector, site: dict | None, aligner: Aligner | None, out_root: Path, session: str,
                 agents: Agents | None, cloud: list[Sink] | None = None,
                 convex: convex_sink.ConvexSink | None = None, pi_sink: PiDashboardSink | None = None):
        self.detector = detector
        self.pi_sink = pi_sink
        self.site = site
        self.aligner = aligner
        self.session = session
        self.sink = JsonlSink(out_root, session)
        self.cloud = cloud or []
        self.convex = convex
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
        if self.pi_sink:
            self.pi_sink.post(obs, detections, image.shape)
        if self.convex:
            self.convex.upload_frame(still.jpeg, still.session, still.t, (image.shape[1], image.shape[0]),
                                     name=obs["frame"])
        self._write("observations", obs)
        if self.agents:
            decisions, alerts = self.agents.run(obs, detections, image, self.history)
            for record in decisions:
                self._write("decisions", record)
            for record in alerts:
                self._write("alerts", record)
        log.info("%s cars=%d people=%d aligned=%s conf=%.2f", still.file, obs["counts"]["car"],
                 obs["counts"]["person"], obs["aligned"], obs["confidence"])
        return obs

    def _write(self, kind: str, record: dict) -> None:
        self.sink.write(kind, record)
        for sink in self.cloud:
            sink.write(kind, record)

    def close(self) -> None:
        self.sink.close()


def load_reference(site: dict, site_path: Path, session_dir: Path | None) -> np.ndarray:
    ref = resolve_reference(site, site_path, session_dir)
    if ref is None:
        raise SystemExit(f"reference frame {site.get('reference_frame')!r} not found next to {site_path} "
                         f"or in the session folder")
    image = cv2.imread(str(ref))
    if image is None:
        raise SystemExit(f"reference frame {ref} is not a readable image")
    return image


def make_convex(args: argparse.Namespace, site: dict | None, reference: np.ndarray | None):
    env = "prod" if args.prod else "dev"
    try:
        sink = convex_sink.ConvexSink(args.convex_config, env=env)
    except (OSError, ValueError) as e:
        raise SystemExit(f"Convex: {e}") from e
    if site:
        size = (reference.shape[1], reference.shape[0]) if reference is not None else None
        sink.set_site(convex_sink.convex_site(site, size))
    log.info("convex: sending to the %s deployment", env)
    return sink


def make_spacetime(args: argparse.Namespace) -> spacetime_sink.SpacetimeSink:
    try:
        sink = spacetime_sink.SpacetimeSink.from_config(args.spacetime_config)
    except (OSError, ValueError, KeyError, spacetime_sink.SpacetimeRejected) as e:
        raise SystemExit(f"Spacetime: {e}") from e
    log.info("spacetime: sending to %s", sink.station.database)
    return sink


def resolve_cloud_flags(args: argparse.Namespace) -> argparse.Namespace:
    """--convex / --spacetime default to on exactly when their config file exists."""
    convex = args.convex_config.is_file() if args.convex is None else args.convex
    spacetime = args.spacetime_config.is_file() if args.spacetime is None else args.spacetime
    return argparse.Namespace(**{**vars(args), "convex": convex, "spacetime": spacetime})


def parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--pi", metavar="URL", help="live mode, e.g. http://balloon.local:8080")
    src.add_argument("--replay", metavar="SESSION_DIR", type=Path, help="session folder with stills/index.csv")
    ap.add_argument("--site", type=Path, help="site JSON drawn with sites/editor.html")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output root (default ground/out)")
    ap.add_argument("--weights", help="YOLO weights (default $BALLOON_WEIGHTS or yolo11n.pt)")
    ap.add_argument("--every", type=int, default=1, help="replay: process every Nth still")
    ap.add_argument("--realtime", action="store_true",
                    help="replay: shift timestamps to now and play at the recorded pace (needed for markets)")
    ap.add_argument("--loop", action="store_true", help="replay: start over at the end (implies --realtime)")
    ap.add_argument("--agents", action="store_true", help="run pricing, market and alert agents")
    ap.add_argument("--market-every", type=float, default=30.0, help="minutes between market proposals")
    ap.add_argument("--poll", type=float, default=2.0, help="live: seconds between polls")
    ap.add_argument("--align-mode", choices=("similarity", "homography"), default="similarity")
    ap.add_argument("--pi-overlay", action=argparse.BooleanOptionalAction, default=True,
                    help="live mode: post detections back to the Pi so its dashboard draws boxes on the video (default on)")
    ap.add_argument("--convex", action=argparse.BooleanOptionalAction, help="send to the Convex live map")
    ap.add_argument("--prod", action="store_true", help="Convex: the production deployment instead of dev")
    ap.add_argument("--convex-config", type=Path, default=convex_sink.CONFIG_PATH)
    ap.add_argument("--spacetime", action=argparse.BooleanOptionalAction, help="send to the Spacetime markets")
    ap.add_argument("--spacetime-config", type=Path, default=spacetime_sink.CONFIG_PATH)
    return resolve_cloud_flags(ap.parse_args(argv))


def still_source(args: argparse.Namespace) -> Iterator[Still]:
    if args.pi:
        return iter(PiSource(args.pi, args.poll))
    if args.realtime or args.loop:
        return paced_replay(args.replay, args.every, args.loop)
    return replay_stills(args.replay, args.every)


def main(argv: list[str]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    args = parse_args(argv)
    if args.replay and not (args.replay / "stills" / "index.csv").is_file():
        raise SystemExit(f"{args.replay} has no stills/index.csv")
    from infer import Detector

    site = load_site(args.site) if args.site else None
    reference = load_reference(site, args.site, args.replay) if site else None
    aligner = Aligner(reference, mode=args.align_mode) if reference is not None else None
    detector = Detector(args.weights)
    log.info("detector %s on %s", detector.name, detector.device)
    convex = make_convex(args, site, reference) if args.convex else None
    cloud: list[Sink] = [s for s in (convex, make_spacetime(args) if args.spacetime else None) if s]
    pi_sink = PiDashboardSink(args.pi) if (args.pi and args.pi_overlay) else None
    if pi_sink:
        log.info("pi dashboard overlay: posting detections to %s", pi_sink.url)
    station = None
    try:
        for still in still_source(args):
            if station is None or station.session != still.session:
                if station:
                    station.close()
                agents = Agents(args.out, still.session, site, args.market_every * 60) if args.agents else None
                if agents:
                    log.info("agents: %s; alert voice: %s", agents.claude.mode,
                             agents.voice.label if agents.voice.available else "off (no XAI_API_KEY)")
                station = Station(detector, site, aligner, args.out, still.session, agents, cloud, convex, pi_sink)
            station.process(still)
    except KeyboardInterrupt:
        log.info("stopped")
    finally:
        if station:
            station.close()
            log.info("wrote %s", station.sink.dir)
        for sink in cloud:
            sink.close()


if __name__ == "__main__":
    main(sys.argv[1:])

"""Send observations, frames, decisions, alerts and site maps to the Convex live map without blocking the station.

Every public method only queues work and returns at once. A background thread sends one batched mutation per
flush interval (frame + observations + decisions + alerts together), so a frame every 2 s costs two Convex calls
(upload URL + batch). If Convex is unreachable, observations wait in a bounded queue, only the newest frame is kept,
and sends retry with backoff.

Config: ~/.config/balloon/convex.json -> {"url": "https://<dev>.convex.cloud", "ingest_secret": "...",
                                          "prod": {"url": "https://<prod>.convex.cloud", "ingest_secret": "..."}}
The top level is the dev deployment; ConvexSink(env="prod") uses the "prod" section.
Requires: pip install convex==0.8.1 (opencv-python is optional, used to shrink frames before upload).

    sink = ConvexSink()
    sink.set_site(json.load(open("sites/marina-green-lot.json")))
    sink.upload_frame("stills/000456.jpg", session, t, (1920, 1080), name="stills/000456.jpg")
    sink.write_observations([observation])
    sink.close()
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from convex import ConvexClient

log = logging.getLogger("convex_sink")

CONFIG_PATH = Path.home() / ".config/balloon/convex.json"
FLUSH_INTERVAL_S = 2.0
CALL_TIMEOUT_S = 10.0
MAX_QUEUED = 500
MAX_BATCH = 200
BACKOFF_MAX_S = 30.0
FRAME_MAX_WIDTH = 1280
FRAME_JPEG_QUALITY = 75


@dataclass(frozen=True)
class PendingFrame:
    jpeg: bytes
    session: str
    t: float
    size: tuple[int, int]
    name: str


def clean(value: Any) -> Any:
    """Make a value Convex-safe: drop None fields, tuples to lists, numpy scalars to Python numbers."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, bool) or isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "item"):
        return clean(value.item())
    return value


def is_rejected(error: Exception) -> bool:
    """Convex refused the data itself; retrying the same batch would fail forever."""
    return "ArgumentValidationError" in str(error)


def load_config(path: Path = CONFIG_PATH, env: str = "dev") -> dict[str, str]:
    root = json.loads(path.read_text())
    cfg = root if env == "dev" else root.get(env, {})
    if not cfg.get("url") or not cfg.get("ingest_secret"):
        raise ValueError(f"{path} needs both 'url' and 'ingest_secret' for the {env} deployment")
    return cfg


def convex_site(site: dict, image_size: tuple[int, int] | None) -> dict:
    """Only the fields the Convex `sites` table accepts; image_size lets the map scale polygons to any frame."""
    zones = [{k: z.get(k) for k in ("id", "kind", "name", "polygon", "capacity")} for z in site.get("zones", [])]
    spaces = [{k: s[k] for k in ("id", "zone", "polygon")} for s in site.get("spaces", [])]
    return clean({"site": site["site"], "name": site.get("name"), "reference_frame": site.get("reference_frame"),
                  "image_size": list(image_size) if image_size else None, "zones": zones, "spaces": spaces})


def convex_decision(record: dict) -> dict | None:
    """A pricing decision in the shape of the `decisions` table; market decisions live in Spacetime."""
    if record.get("agent") != "pricing":
        return None
    return clean({
        "t": record["t"], "zone": record["zone"], "action": record["action"],
        "price_before": record["old_price"], "price_after": record["new_price"],
        "inputs": record["inputs"],
        "outputs": {"target_price": record.get("target_price"), "code": record.get("code")},
        "explanation": record.get("explanation") or record["reason"],
        "model": record.get("explained_by", "engine"),
    })


def alert_severity(record: dict) -> str:
    if record.get("low_confidence"):
        return "info"
    return "critical" if record.get("trigger", {}).get("people_near_rip") else "warning"


def alert_counts(record: dict) -> dict:
    in_water = int(record.get("trigger", {}).get("people_in_water_zone") or record.get("people_in_water") or 0)
    everyone = int(record.get("counts", {}).get("person", 0))
    return {"person_water": in_water, "person_beach": max(0, everyone - in_water)}


def convex_alert(record: dict) -> dict:
    """Carries what Balloon Patrol (Jira) needs when a patrol member confirms the alert on the live map."""
    return clean({
        "t": record["t"], "session": record.get("session"), "text": record["alert"],
        "uncertainty": record["uncertainty"], "severity": alert_severity(record), "frame": record.get("frame"),
        "model": record.get("written_by"), "zone": record.get("zone"), "confidence": record.get("confidence"),
        "counts": alert_counts(record),
    })


def shrink_jpeg(raw: bytes, max_width: int) -> tuple[bytes, tuple[int, int] | None]:
    """Downscale wide frames so phones don't pull 2 MB every 2 s. Falls back to the original bytes without cv2."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return raw, None
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None or img.shape[1] <= max_width:
        return raw, None
    h, w = img.shape[:2]
    small = cv2.resize(img, (max_width, round(h * max_width / w)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, FRAME_JPEG_QUALITY])
    return (buf.tobytes(), (small.shape[1], small.shape[0])) if ok else (raw, None)


class ConvexSink:
    def __init__(
        self,
        config_path: Path = CONFIG_PATH,
        flush_interval_s: float = FLUSH_INTERVAL_S,
        call_timeout_s: float = CALL_TIMEOUT_S,
        frame_max_width: int = FRAME_MAX_WIDTH,
        env: str = "dev",
    ) -> None:
        cfg = load_config(config_path, env)
        self._secret = cfg["ingest_secret"]
        self._client = ConvexClient(cfg["url"])
        self._flush_interval_s = flush_interval_s
        self._timeout_s = call_timeout_s
        self._frame_max_width = frame_max_width
        self._calls = ThreadPoolExecutor(max_workers=2, thread_name_prefix="convex-call")

        self._lock = threading.Lock()
        self._observations: deque[dict] = deque(maxlen=MAX_QUEUED)
        self._decisions: deque[dict] = deque(maxlen=MAX_QUEUED)
        self._alerts: deque[dict] = deque(maxlen=MAX_QUEUED)
        self._site: dict | None = None
        self._frame: PendingFrame | None = None
        self._uploaded: dict | None = None
        self._failures = 0
        self.sent = {"frames": 0, "observations": 0, "decisions": 0, "alerts": 0, "sites": 0}

        self._wake = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="convex-sink", daemon=True)
        self._thread.start()

    def write_observations(self, observations: list[dict]) -> None:
        with self._lock:
            self._observations.extend(clean(o) for o in observations)
            self._idle.clear()

    def write_decision(self, decision: dict) -> None:
        with self._lock:
            self._decisions.append(clean(decision))
            self._idle.clear()
        self._wake.set()

    def write_alert(self, alert: dict) -> None:
        with self._lock:
            self._alerts.append(clean(alert))
            self._idle.clear()
        self._wake.set()

    def write(self, kind: str, record: dict) -> None:
        """The station's Sink interface: observations, pricing decisions and alerts, mapped to the Convex tables."""
        if kind == "observations":
            self.write_observations([record])
        elif kind == "decisions" and (decision := convex_decision(record)):
            self.write_decision(decision)
        elif kind == "alerts":
            self.write_alert(convex_alert(record))

    def upload_frame(
        self, jpeg: str | bytes, session: str, t: float, size: tuple[int, int], name: str | None = None
    ) -> None:
        """Queue a frame (a path or the JPEG bytes). Only the newest unsent frame is kept.
        Pass name equal to the observation's 'frame'."""
        if isinstance(jpeg, bytes):
            data, default_name = jpeg, "frame.jpg"
        else:
            data, default_name = Path(jpeg).read_bytes(), Path(jpeg).name
        frame = PendingFrame(data, session, float(t), (int(size[0]), int(size[1])), name or default_name)
        with self._lock:
            self._frame = frame
            self._idle.clear()

    def set_site(self, site: dict) -> None:
        with self._lock:
            self._site = clean(site)
            self._idle.clear()
        self._wake.set()

    def flush(self, timeout_s: float = 30.0) -> bool:
        """Block until everything queued so far is sent (or timeout). For shutdown and tests, not the hot loop."""
        self._wake.set()
        return self._idle.wait(timeout_s)

    def close(self, timeout_s: float = 10.0) -> None:
        self.flush(timeout_s)
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout_s)
        self._calls.shutdown(wait=False, cancel_futures=True)

    def _redact(self, error: Exception) -> str:
        # Convex validation errors echo the call's args, which include the secret.
        return str(error).replace(self._secret, "***")

    def _call(self, name: str, args: dict) -> Any:
        future = self._calls.submit(self._client.mutation, name, {"secret": self._secret, **args})
        try:
            return future.result(timeout=self._timeout_s)
        except FutureTimeout as e:
            raise TimeoutError(f"{name} took longer than {self._timeout_s:.0f} s") from e

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self._flush_interval_s)
            self._wake.clear()
            try:
                self._send_pending()
                self._failures = 0
            except Exception as e:  # network, Convex validation, disk: log, back off, keep the queue
                self._failures += 1
                delay = min(BACKOFF_MAX_S, 2.0 ** self._failures)
                log.warning("convex send failed (%s); retrying in %.0f s", self._redact(e), delay)
                self._stop.wait(delay)

    def _send_pending(self) -> None:
        with self._lock:
            site, self._site = self._site, None
        if site is not None:
            try:
                self._call("ingest:setSite", {"site": site})
                self.sent["sites"] += 1
            except Exception as e:
                if not is_rejected(e):
                    with self._lock:
                        self._site = self._site or site
                    raise
                log.error("convex rejected the site map, dropping it: %s", self._redact(e))

        self._upload_newest_frame()
        self._send_batch()

        with self._lock:
            empty = not (self._observations or self._decisions or self._alerts or self._frame or self._uploaded or self._site)
            if empty:
                self._idle.set()

    def _upload_newest_frame(self) -> None:
        with self._lock:
            if self._uploaded is not None:
                return
            frame, self._frame = self._frame, None
        if frame is None:
            return
        try:
            data, shrunk = shrink_jpeg(frame.jpeg, self._frame_max_width)
            upload_url = self._call("ingest:generateUploadUrl", {})
            r = requests.post(upload_url, data=data, headers={"Content-Type": "image/jpeg"}, timeout=self._timeout_s)
            r.raise_for_status()
        except Exception:
            with self._lock:
                self._frame = self._frame or frame
            raise
        width, height = shrunk or frame.size
        with self._lock:
            self._uploaded = {
                "session": frame.session,
                "t": frame.t,
                "name": frame.name,
                "storageId": r.json()["storageId"],
                "width": float(width),
                "height": float(height),
                "bytes": float(len(data)),
            }

    def _send_batch(self) -> None:
        with self._lock:
            frame = self._uploaded
            obs = [self._observations.popleft() for _ in range(min(MAX_BATCH, len(self._observations)))]
            dec = [self._decisions.popleft() for _ in range(min(MAX_BATCH, len(self._decisions)))]
            alerts = [self._alerts.popleft() for _ in range(min(MAX_BATCH, len(self._alerts)))]
        if not (frame or obs or dec or alerts):
            return
        args: dict[str, Any] = {}
        if frame:
            args["frame"] = frame
        if obs:
            args["observations"] = obs
        if dec:
            args["decisions"] = dec
        if alerts:
            args["alerts"] = alerts
        try:
            self._call("ingest:batch", args)
        except Exception as e:
            if is_rejected(e):
                log.error("convex rejected a batch, dropping it: %s", self._redact(e))
                with self._lock:
                    if self._uploaded is frame:
                        self._uploaded = None
                return
            with self._lock:
                self._observations.extendleft(reversed(obs))
                self._decisions.extendleft(reversed(dec))
                self._alerts.extendleft(reversed(alerts))
            raise
        with self._lock:
            if self._uploaded is frame:
                self._uploaded = None
        self.sent["frames"] += 1 if frame else 0
        self.sent["observations"] += len(obs)
        self.sent["decisions"] += len(dec)
        self.sent["alerts"] += len(alerts)

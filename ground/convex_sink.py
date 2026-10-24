"""Send observations, frames, decisions, alerts and site maps to the Convex live map without blocking the station.

Every public method only queues work and returns at once. A background thread sends one batched mutation per
flush interval (frame + observations + decisions + alerts together), so a frame every 2 s costs two Convex calls
(upload URL + batch). If Convex is unreachable, observations wait in a bounded queue, only the newest frame is kept,
and sends retry with backoff.

Config: ~/.config/balloon/convex.json -> {"url": "https://<deployment>.convex.cloud", "ingest_secret": "..."}
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
    path: str
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


def load_config(path: Path = CONFIG_PATH) -> dict[str, str]:
    cfg = json.loads(path.read_text())
    if not cfg.get("url") or not cfg.get("ingest_secret"):
        raise ValueError(f"{path} needs both 'url' and 'ingest_secret'")
    return cfg


def shrink_jpeg(path: str, max_width: int) -> tuple[bytes, tuple[int, int] | None]:
    """Downscale wide frames so phones don't pull 2 MB every 2 s. Falls back to the original bytes without cv2."""
    raw = Path(path).read_bytes()
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
    ) -> None:
        cfg = load_config(config_path)
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

    def upload_frame(
        self, jpeg_path: str, session: str, t: float, size: tuple[int, int], name: str | None = None
    ) -> None:
        """Queue a frame. Only the newest unsent frame is kept. Pass name equal to the observation's 'frame'."""
        frame = PendingFrame(str(jpeg_path), session, float(t), (int(size[0]), int(size[1])), name or Path(jpeg_path).name)
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
                log.warning("convex send failed (%s); retrying in %.0f s", e, delay)
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
                log.error("convex rejected the site map, dropping it: %s", e)

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
            data, shrunk = shrink_jpeg(frame.path, self._frame_max_width)
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
                log.error("convex rejected a batch, dropping it: %s", e)
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

"""Post each frame's detections back to the Pi so its dashboard can draw boxes over the live video.

Payload (POST <pi>/api/detections): t_unix, frame, width, height, counts, detections [{cls, conf, xyxy}], zones.
Fire-and-forget on a background thread: a slow or unreachable Pi never stalls the detector (latest frame wins)."""
import json
import logging
import queue
import threading
import urllib.request

log = logging.getLogger("pi_sink")


class PiDashboardSink:
    def __init__(self, pi_url: str, timeout: float = 2.0):
        self.url = pi_url.rstrip("/") + "/api/detections"
        self.timeout = timeout
        self.q: queue.Queue = queue.Queue(maxsize=2)
        self.failures = 0
        self.sent = 0
        threading.Thread(target=self._worker, daemon=True, name="pi-sink").start()

    def post(self, obs: dict, detections: list[dict], shape, extra: dict | None = None) -> None:
        payload = {
            "t_unix": obs.get("t"), "frame": obs.get("frame"),
            "width": int(shape[1]), "height": int(shape[0]),
            "counts": obs.get("counts", {}), "zones": obs.get("zones") or None,
            "confidence": obs.get("confidence"), "aligned": obs.get("aligned"), "model": obs.get("model"),
            "detections": [{"cls": d["cls"], "conf": d.get("conf"), "xyxy": d["xyxy"]} for d in detections][:300],
        }
        if extra:
            payload.update(extra)
        try:
            self.q.put_nowait(payload)
        except queue.Full:            # keep only the newest frame
            try:
                self.q.get_nowait()
            except queue.Empty:
                pass
            self.q.put_nowait(payload)

    def _worker(self) -> None:
        while True:
            payload = self.q.get()
            body = json.dumps(payload, separators=(",", ":")).encode()
            req = urllib.request.Request(self.url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout):
                    pass
                self.sent += 1
                if self.failures:
                    log.info("pi dashboard reachable again")
                self.failures = 0
            except Exception as e:
                self.failures += 1
                if self.failures in (1, 10, 100, 1000):
                    log.warning("pi dashboard post failed (%d): %s", self.failures, e)

    # Sink protocol compatibility (not used for records; detections go through post())
    def write(self, kind: str, record: dict) -> None:
        return None

    def close(self) -> None:
        return None

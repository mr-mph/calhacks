"""Balloon narrator (runs on the laptop): looks through the Pi's camera every few seconds, describes what it sees with
Claude, speaks it with ElevenLabs, and posts both to the Pi so every dashboard on BalloonNet shows and plays them.
Also answers questions people ask on the dashboard (voice or text), with the live image and telemetry as context.

    ground/.venv/bin/python narrator.py --pi http://10.42.0.1:8080            # every 20 s
    ground/.venv/bin/python narrator.py --pi http://10.42.0.1:8080 --interval 30 --no-voice

Keys: ANTHROPIC_API_KEY and ELEVENLABS_API_KEY from the environment or ~/.config/balloon/secrets.env.
"""
import argparse
import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

log = logging.getLogger("narrator")

SYSTEM = """You are the voice of a tethered helium balloon camera at Cal Hacks (the Palace of Fine Arts, San Francisco).
You see a photo from the balloon's camera plus live telemetry. Speak like a sharp, friendly commentator on a live feed:
one or two short sentences, plain spoken English, no markdown, no lists, no hedging, no "the image shows".
Say what is actually visible and notable (people, vehicles, structures, water, light, motion), and weave in a
telemetry fact when it is interesting (altitude, tilt, air quality, climb). Vary your phrasing; never repeat the
previous caption's wording. If the view is dark, blurred, or pointing at something mundane, say so briefly and
with humour. When answering a question, answer it directly first, then at most one extra detail."""


def load_secrets():
    p = Path.home() / ".config" / "balloon" / "secrets.env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def http_json(url, data=None, timeout=10):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"} if data is not None else {},
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def http_bytes(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


class ElevenLabs:
    def __init__(self, api_key, voice_id, model_id="eleven_flash_v2_5"):
        self.key, self.voice, self.model = api_key, voice_id, model_id

    def tts_mp3(self, text):
        url = "https://api.elevenlabs.io/v1/text-to-speech/%s?output_format=mp3_22050_32" % self.voice
        body = json.dumps({"text": text, "model_id": self.model,
                           "voice_settings": {"stability": 0.45, "similarity_boost": 0.75}}).encode()
        req = urllib.request.Request(url, data=body, headers={"xi-api-key": self.key, "Content-Type": "application/json",
                                                              "Accept": "audio/mpeg"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()


class Narrator:
    def __init__(self, pi, model, voice, interval, voice_enabled):
        import anthropic
        self.pi = pi.rstrip("/")
        self.client = anthropic.Anthropic()
        self.model = model
        self.interval = interval
        self.tts = ElevenLabs(os.environ["ELEVENLABS_API_KEY"], voice) if (voice_enabled and os.environ.get("ELEVENLABS_API_KEY")) else None
        self.recent = deque(maxlen=6)
        self.spend_in = self.spend_out = 0

    # ----- context -----
    def snapshot_b64(self):
        return base64.b64encode(http_bytes(self.pi + "/camera/snapshot.jpg", timeout=8)).decode()

    def telemetry_text(self):
        try:
            t = http_json(self.pi + "/api/latest", timeout=4)
        except Exception:
            t = {}
        try:
            d = http_json(self.pi + "/api/detections", timeout=4)
        except Exception:
            d = {}
        parts = []
        for k, lab, u in (("altitude_m", "altitude above launch", "m"), ("elevation_msl_m", "elevation", "m above sea level"),
                          ("vspeed_mps", "climb rate", "m/s"), ("tilt_deg", "tilt", "degrees"), ("temp_c", "air temperature", "C"),
                          ("pressure_hpa", "pressure", "hPa"), ("aq_raw", "air quality raw (lower is cleaner, >300 is polluted)", "")):
            if t.get(k) is not None:
                parts.append("%s %s %s" % (lab, t[k], u))
        if d.get("available"):
            parts.append("object detector sees: " + (", ".join("%s x%d" % kv for kv in (d.get("by_class") or {}).items()) or "nothing"))
        return "; ".join(parts) or "no telemetry"

    # ----- model -----
    def claude(self, prompt, with_image=True, max_tokens=160):
        content = []
        if with_image:
            try:
                content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": self.snapshot_b64()}})
            except Exception as e:
                log.warning("no snapshot: %s", e)
        content.append({"type": "text", "text": prompt})
        resp = self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=SYSTEM,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": content}],
        )
        self.spend_in += resp.usage.input_tokens
        self.spend_out += resp.usage.output_tokens
        if resp.stop_reason == "refusal":
            return "I'd rather not describe that one."
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def post(self, path, payload):
        try:
            return http_json(self.pi + path, payload, timeout=15)
        except Exception as e:
            log.warning("post %s failed: %s", path, e)
            return None

    def voice_b64(self, text):
        if not self.tts:
            return None
        try:
            return base64.b64encode(self.tts.tts_mp3(text)).decode()
        except urllib.error.HTTPError as e:
            log.warning("elevenlabs %s: %s", e.code, e.read()[:200])
        except Exception as e:
            log.warning("elevenlabs failed: %s", e)
        return None

    # ----- loops -----
    def caption_once(self):
        prev = " | ".join(self.recent)
        prompt = ("Live telemetry: %s.\nPrevious captions (do not repeat their wording): %s\n"
                  "Describe what the camera sees right now in one or two spoken sentences." % (self.telemetry_text(), prev or "none"))
        text = self.claude(prompt)
        if not text:
            return
        self.recent.append(text)
        log.info("caption: %s", text)
        self.post("/api/captions", {"text": text, "audio_b64": self.voice_b64(text), "model": self.model})

    def answer_loop(self):
        seen = set()
        while True:
            try:
                for q in http_json(self.pi + "/api/ask/pending", timeout=4):
                    if q["id"] in seen:
                        continue
                    seen.add(q["id"])
                    log.info("question: %s", q["text"])
                    prompt = ("Live telemetry: %s.\nRecent captions: %s\nSomeone on the ground asks: \"%s\"\n"
                              "Answer them directly in one to three spoken sentences." % (self.telemetry_text(), " | ".join(self.recent) or "none", q["text"]))
                    text = self.claude(prompt, max_tokens=220)
                    log.info("answer: %s", text)
                    self.post("/api/ask/answer", {"id": q["id"], "text": text, "audio_b64": self.voice_b64(text)})
            except Exception as e:
                log.warning("answer loop: %s", e)
            time.sleep(1.0)

    def run(self):
        threading.Thread(target=self.answer_loop, daemon=True, name="answers").start()
        log.info("narrating every %.0f s with %s (voice %s) -> %s", self.interval, self.model, "on" if self.tts else "off", self.pi)
        while True:
            t0 = time.time()
            try:
                self.caption_once()
            except Exception as e:
                log.warning("caption failed: %s", e)
            if int(t0) % 300 < self.interval:
                log.info("tokens so far: in=%d out=%d", self.spend_in, self.spend_out)
            time.sleep(max(2.0, self.interval - (time.time() - t0)))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    load_secrets()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pi", default=os.environ.get("BALLOON_PI", "http://10.42.0.1:8080"))
    ap.add_argument("--model", default=os.environ.get("BALLOON_NARRATOR_MODEL", "claude-sonnet-5-5"))
    ap.add_argument("--interval", type=float, default=float(os.environ.get("BALLOON_CAPTION_INTERVAL", "20")))
    ap.add_argument("--voice-id", default=os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"))
    ap.add_argument("--no-voice", action="store_true")
    a = ap.parse_args()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY missing (env or ~/.config/balloon/secrets.env)")
    Narrator(a.pi, a.model, a.voice_id, a.interval, not a.no_voice).run()


if __name__ == "__main__":
    main()

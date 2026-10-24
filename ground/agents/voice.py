"""Grok voice for beach alerts: one xAI text-to-speech call per alert, read in a calm voice for the patrol.

POST https://api.x.ai/v1/tts (docs.x.ai/developers/rest-api-reference/inference/voice) returns the audio bytes.
xAI charges $15 per million characters, so a 300-character alert costs about $0.0045. The cost goes into the same
spend ledger as Claude (ground/out/spend.json, purpose "voice"); over the cap, the alert simply has no audio.
"""
import base64
import logging
import os

import requests

from agents.llm import SpendLedger, load_api_key

log = logging.getLogger("agents.voice")

TTS_URL = "https://api.x.ai/v1/tts"
USD_PER_CHAR = 15.00 / 1_000_000
LEDGER_MODEL = "xai-tts"
VOICE_ID = os.environ.get("BALLOON_VOICE_ID", "rex")
SPEED = 0.95
MAX_CHARS = 800
TIMEOUT_S = 30.0
MP3 = {"codec": "mp3", "sample_rate": 24000, "bit_rate": 64000}


def spoken_text(alert: dict) -> str:
    text = f"Beach alert. {alert['alert'].strip()} {alert['uncertainty'].strip()}"
    return text[:MAX_CHARS]


def is_mp3(data: bytes) -> bool:
    if data[:3] == b"ID3":
        return True
    return len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0


def _audio_from(response: requests.Response) -> bytes:
    """Raw MP3 by default; the docs also describe a JSON body with base64 audio, so accept both."""
    if response.headers.get("content-type", "").startswith("application/json"):
        return base64.b64decode(response.json()["audio"])
    return response.content


class GrokVoice:
    def __init__(self, ledger: SpendLedger, api_key: str | None = None, voice: str = VOICE_ID,
                 http: requests.Session | None = None):
        self.ledger = ledger
        self.voice = voice
        self.key = api_key or load_api_key("XAI_API_KEY")
        self.http = http or requests.Session()

    @property
    def available(self) -> bool:
        return self.key is not None

    @property
    def label(self) -> str:
        return f"Grok TTS ({self.voice})"

    def speak(self, alert: dict) -> bytes | None:
        """MP3 bytes of the alert and its uncertainty line, or None without a key, over the cap, or on an error."""
        if not self.key:
            return None
        text = spoken_text(alert)
        usd = len(text) * USD_PER_CHAR
        if not self.ledger.allows(usd):
            self.ledger.record("voice", LEDGER_MODEL, 0.0, refused=True)
            log.warning("spend cap $%.2f reached for %s; alert has no audio", self.ledger.cap_usd, self.ledger.session)
            return None
        body = {"text": text, "voice_id": self.voice, "language": "en", "output_format": MP3,
                "speed": SPEED, "text_normalization": True}
        try:
            response = self.http.post(TTS_URL, json=body, timeout=TIMEOUT_S,
                                      headers={"Authorization": f"Bearer {self.key}"})
            response.raise_for_status()
            audio = _audio_from(response)
        except (requests.RequestException, ValueError, KeyError) as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            log.warning("voice: xAI TTS failed (%s%s)", type(e).__name__, f" {status}" if status else "")
            return None
        self.ledger.record("voice", LEDGER_MODEL, usd)
        if not is_mp3(audio):
            log.warning("voice: xAI TTS returned %d bytes that are not MP3", len(audio))
            return None
        return audio

"""One real Grok text-to-speech call, only when XAI_API_KEY is available. Writes ground/out/voice-smoke.mp3."""
from pathlib import Path

import pytest

from agents.llm import SpendLedger, load_api_key
from agents.voice import USD_PER_CHAR, GrokVoice, spoken_text
from mp3 import mp3_duration_s

pytestmark = pytest.mark.skipif(not load_api_key("XAI_API_KEY"), reason="no XAI_API_KEY; alerts have no audio")

OUT = Path(__file__).resolve().parents[1] / "out" / "voice-smoke.mp3"
ALERT = {"alert": "Possible rip current at the dark gap left of the lifeguard tower; 2 people in the water near it.",
         "uncertainty": "Glare on the water could hide swimmers, and the detector has not been checked on this beach."}


def test_grok_speaks_one_alert(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.json", "live-voice", 0.05)
    audio = GrokVoice(ledger).speak(ALERT)
    assert audio, "no audio (see the agents.voice warning above)"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(audio)
    assert 2.0 < mp3_duration_s(audio) < 60.0
    assert ledger.spent() == pytest.approx(len(spoken_text(ALERT)) * USD_PER_CHAR)

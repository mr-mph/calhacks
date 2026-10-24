import base64
import json

import pytest
import requests

import convex_sink
import station
from agents.llm import SpendLedger
from agents.voice import TTS_URL, USD_PER_CHAR, GrokVoice, is_mp3, spoken_text
from test_cloud_sinks import FakeConvexClient, write_convex_config

FAKE_MP3 = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\xff\xf3\x84\xc4" + bytes(200)
ALERT = {"t": 9.0, "session": "s", "frame": "stills/9.jpg", "alert": "Rip forming left of the stairs.",
         "uncertainty": "Glare could hide swimmers.", "trigger": {"people_near_rip": 1}, "low_confidence": False}


class FakeTTSResponse:
    def __init__(self, status: int = 200, content: bytes = FAKE_MP3, content_type: str = "audio/mpeg"):
        self.status_code = status
        self.content = content
        self.headers = {"content-type": content_type}

    def json(self):
        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}", response=self)


class FakeHTTP:
    def __init__(self, response: FakeTTSResponse | Exception):
        self.response = response
        self.calls: list[dict] = []

    def post(self, url, json=None, timeout=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def voice(tmp_path, response=None, cap: float = 1.0, key: str | None = "test-key") -> tuple[GrokVoice, FakeHTTP]:
    http = FakeHTTP(response or FakeTTSResponse())
    ledger = SpendLedger(tmp_path / "spend.json", "s", cap)
    return GrokVoice(ledger, api_key=key, voice="rex", http=http), http


def spend(tmp_path) -> dict:
    return json.loads((tmp_path / "spend.json").read_text())["sessions"]["s"]


def test_spoken_text_reads_alert_then_uncertainty():
    assert spoken_text(ALERT) == "Beach alert. Rip forming left of the stairs. Glare could hide swimmers."


def test_speak_posts_one_mp3_request_and_counts_published_price(tmp_path):
    grok, http = voice(tmp_path)
    assert grok.speak(ALERT) == FAKE_MP3
    [call] = http.calls
    assert call["url"] == TTS_URL == "https://api.x.ai/v1/tts"
    assert call["headers"] == {"Authorization": "Bearer test-key"}
    body = call["json"]
    assert body["text"] == spoken_text(ALERT) and body["voice_id"] == "rex" and body["language"] == "en"
    assert body["output_format"]["codec"] == "mp3"
    entry = spend(tmp_path)
    assert entry["by_purpose"]["voice"] == pytest.approx(len(body["text"]) * USD_PER_CHAR, abs=1e-6)
    assert entry["calls"] == 1 and entry["last_model"] == "xai-tts"


def test_speak_accepts_json_base64_audio(tmp_path):
    body = json.dumps({"audio": base64.b64encode(FAKE_MP3).decode(), "content_type": "audio/mpeg"}).encode()
    grok, _ = voice(tmp_path, FakeTTSResponse(content=body, content_type="application/json"))
    assert grok.speak(ALERT) == FAKE_MP3


def test_speak_refuses_over_cap_without_calling_xai(tmp_path):
    grok, http = voice(tmp_path, cap=0.0)
    assert grok.speak(ALERT) is None
    assert http.calls == []
    assert spend(tmp_path)["refused"] == 1 and spend(tmp_path)["usd"] == 0.0


def test_speak_without_key_does_nothing(tmp_path):
    grok, http = voice(tmp_path, key=None)
    grok.key = None
    assert not grok.available and grok.speak(ALERT) is None and http.calls == []


@pytest.mark.parametrize("response", [FakeTTSResponse(status=429), requests.ConnectionError("down"),
                                      FakeTTSResponse(content=b"<html>error</html>", content_type="text/html")])
def test_speak_failures_return_none_and_never_log_the_key(tmp_path, caplog, response):
    grok, _ = voice(tmp_path, response)
    assert grok.speak(ALERT) is None
    assert "test-key" not in caplog.text


def test_is_mp3():
    assert is_mp3(FAKE_MP3) and is_mp3(b"\xff\xfb\x90\x00") and not is_mp3(b"RIFF....WAVE") and not is_mp3(b"")


def test_station_saves_the_alert_audio_and_points_the_record_at_it(tmp_path, monkeypatch):
    monkeypatch.setenv("BALLOON_ENV_FILE", str(tmp_path / "missing"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    agents = station.Agents(tmp_path, "s", None, 1800)
    assert agents._voiced(ALERT) == ALERT
    agents.voice, _ = voice(tmp_path)
    record = agents._voiced(ALERT)
    assert record["audio"]["voice"] == "Grok TTS (rex)" and record["audio"]["bytes"] == len(FAKE_MP3)
    assert open(record["audio"]["file"], "rb").read() == FAKE_MP3


def test_convex_sink_stores_alert_audio_then_sends_its_id(tmp_path, monkeypatch):
    uploads: list[tuple[str, bytes]] = []

    class StorageResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"storageId": f"storage-{len(uploads)}"}

    def post(url, data, headers, timeout):
        uploads.append((headers["Content-Type"], data))
        return StorageResponse()

    monkeypatch.setattr(convex_sink, "ConvexClient", FakeConvexClient)
    monkeypatch.setattr(convex_sink.requests, "post", post)
    mp3 = tmp_path / "alert.mp3"
    mp3.write_bytes(FAKE_MP3)
    sink = convex_sink.ConvexSink(write_convex_config(tmp_path), flush_interval_s=0.05)
    sink.write("alerts", {**ALERT, "audio": {"file": str(mp3), "voice": "Grok TTS (rex)", "bytes": len(FAKE_MP3)}})
    sink.write("alerts", {**ALERT, "t": 10.0, "audio": {"file": str(tmp_path / "gone.mp3"), "voice": "x"}})
    sink.write("alerts", {**ALERT, "t": 11.0})
    assert sink.flush(10)
    sink.close()
    assert uploads == [("audio/mpeg", FAKE_MP3)]
    sent = [a for name, args in sink._client.mutations if name == "ingest:batch" for a in args["alerts"]]
    assert [a["t"] for a in sent] == [9.0, 10.0, 11.0]
    assert sent[0]["audioId"] == "storage-1" and sent[0]["voice"] == "Grok TTS (rex)"
    assert not {"audioId", "voice"} & (sent[1].keys() | sent[2].keys())

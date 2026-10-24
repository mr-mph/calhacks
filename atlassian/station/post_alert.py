"""Send a confirmed beach alert from the ground station to Balloon Patrol (Jira).

Reads the web trigger URL and shared secret from ~/.config/balloon/forge.json (written by
atlassian/scripts/setup.sh). Stdlib only, so it runs in the station venv without new packages.

    from post_alert import post_alert, to_payload
    post_alert(to_payload(alert, zone="north-stairs", frame_url=url))   # alert = AlertWriter.check(...) output

    python3 post_alert.py payload.json      # or send a hand-written payload
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONFIG = Path.home() / ".config" / "balloon" / "forge.json"
TIMEOUT_S = 25


def load_config(path: Path = CONFIG) -> dict:
    return json.loads(path.read_text())


def to_payload(alert: dict, zone: str, frame_url: str | None = None) -> dict:
    """Map a confirmed station alert (ground/agents/alerts.py) to the Balloon Patrol contract."""
    trigger = alert.get("trigger", {})
    in_water = int(trigger.get("people_in_water_zone") or alert.get("people_in_water") or 0)
    everyone = int(alert.get("counts", {}).get("person", 0))
    return {
        "alert_id": f"{alert['session']}-{alert['frame']}",
        "text": alert["alert"],
        "uncertainty": alert.get("uncertainty", ""),
        "zone": zone,
        "counts": {"person_water": in_water, "person_beach": max(0, everyone - in_water)},
        "confidence": float(alert["confidence"]),
        "frame_url": frame_url,
        "t": float(alert["t"]),
    }


def post_alert(payload: dict, config: dict | None = None) -> dict:
    cfg = config or load_config()
    request = urllib.request.Request(
        cfg["webtrigger_url"],
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", cfg.get("header", "X-Balloon-Secret"): cfg["secret"]},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as err:
        return {"status": err.code, **json.loads(err.read() or b"{}")}


if __name__ == "__main__":
    print(json.dumps(post_alert(json.loads(Path(sys.argv[1]).read_text())), indent=2))

#!/bin/bash
# ONE command for the ground side. From the repo root on a Mac that is on Wi-Fi "BalloonNet":
#     ground/start.sh
# It checks the Pi, creates the Python environment on first run, then runs together until Ctrl-C:
#   - the detector (YOLO on every still, boxes posted to the Pi dashboard)       log: ground/out/station-live.log
#   - the narrator (Claude describes the view + ElevenLabs voice + Q&A) if keys exist  log: ground/out/narrator.log
# Knobs (environment variables):  PI=http://10.42.0.1:8080  CLASSES=all|carperson (default all)
#   INTERVAL=20 (seconds between captions)  NO_NARRATOR=1  NO_VOICE=1
set -u
cd "$(dirname "$0")"
PI="${PI:-http://10.42.0.1:8080}"
mkdir -p out
bold() { printf '\033[1m%s\033[0m\n' "$*"; }

bold "== balloon ground station =="
if ! curl -s -m 4 "$PI/api/status" >/dev/null; then
  echo "Cannot reach the Pi at $PI."
  echo "  - Is this Mac on Wi-Fi 'BalloonNet' (password balloon123)?  - Is the Pi powered (give it ~1 min after power-on)?"
  exit 1
fi
echo "Pi reachable: $(curl -s -m 4 "$PI/api/status" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("session", d["session"], "| sensors:", ", ".join(s["name"] for s in d["sensors"]["sensors"]))' 2>/dev/null)"

if [ ! -x .venv/bin/python ]; then
  bold "First run: creating the Python environment (needs internet, a few minutes)…"
  python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip && .venv/bin/pip install -q -r requirements-station.txt || { echo "install failed"; exit 1; }
fi
[ -f ~/.config/balloon/secrets.env ] && set -a && . ~/.config/balloon/secrets.env && set +a

pids=""
cleanup() { echo; bold "stopping…"; for p in $pids; do pkill -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; done; pkill -f "station.py --pi $PI" 2>/dev/null; pkill -f "narrator.py --pi $PI" 2>/dev/null; wait 2>/dev/null; exit 0; }
trap cleanup INT TERM

# --- detector ---
export BALLOON_ALL_CLASSES=$([ "${CLASSES:-all}" = "all" ] && echo 1 || echo 0)
bold "detector: YOLO on the Pi's stills, boxes -> dashboard (classes: ${CLASSES:-all})"
( while true; do PYTHONUNBUFFERED=1 .venv/bin/python station.py --pi "$PI" --no-convex --no-spacetime --poll 2 >> out/station-live.log 2>&1; sleep 5; done ) &
pids="$pids $!"

# --- narrator ---
if [ "${NO_NARRATOR:-0}" = "1" ]; then
  echo "narrator: off (NO_NARRATOR=1)"
elif [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "narrator: off (no ANTHROPIC_API_KEY in ~/.config/balloon/secrets.env)"
else
  NV=""; [ "${NO_VOICE:-0}" = "1" ] && NV="--no-voice"
  bold "narrator: Claude captions every ${INTERVAL:-20} s$([ "${NO_VOICE:-0}" = "1" ] && echo ' (no voice)' || echo ' + ElevenLabs voice')"
  # shellcheck disable=SC2086  (NV is intentionally word-split; macOS bash 3.2 cannot expand an empty array under set -u)
  ( while true; do PYTHONUNBUFFERED=1 .venv/bin/python narrator.py --pi "$PI" --interval "${INTERVAL:-20}" $NV >> out/narrator.log 2>&1; sleep 5; done ) &
  pids="$pids $!"
fi

echo
echo "Dashboard: $PI   (phones: join BalloonNet, open the same address)"
echo "Logs: ground/out/station-live.log, ground/out/narrator.log      Ctrl-C stops everything."
echo
# live tail of the interesting lines
tail -n 0 -F out/station-live.log out/narrator.log 2>/dev/null | grep --line-buffered -E "caption:|answer:|question:|cars=|rror|arning" | cut -c1-160

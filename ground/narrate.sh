#!/bin/bash
# Run the narrator (Claude captions + ElevenLabs voice) against the live Pi and keep it running.
#     ground/narrate.sh                    # every 20 s, Pi at http://10.42.0.1:8080
#     ground/narrate.sh --interval 30 --no-voice
# Keys in ~/.config/balloon/secrets.env (ANTHROPIC_API_KEY, ELEVENLABS_API_KEY).
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "no ground/.venv: python3 -m venv .venv && .venv/bin/pip install -r requirements-station.txt" >&2; exit 1; }
mkdir -p out
while true; do
  PYTHONUNBUFFERED=1 .venv/bin/python narrator.py --pi "${PI:-http://10.42.0.1:8080}" "$@" 2>&1 | tee -a out/narrator.log
  echo "narrator exited; restarting in 5 s (Ctrl-C to stop)"; sleep 5
done

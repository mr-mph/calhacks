#!/bin/bash
# Run the ground station against the live Pi and keep it running (restarts on crash / network blip).
#     ground/live.sh                      # Pi at http://10.42.0.1:8080 (BalloonNet), no cloud sinks
#     ground/live.sh --agents --prod      # extra flags pass through (needs ~/.config/balloon/*.json)
#     PI=http://balloon.local:8080 ground/live.sh
cd "$(dirname "$0")"
PI="${PI:-http://10.42.0.1:8080}"
[ -x .venv/bin/python ] || { echo "no ground/.venv: python3 -m venv .venv && .venv/bin/pip install -r requirements-station.txt" >&2; exit 1; }
mkdir -p out
EXTRA=("$@"); case " $* " in *--convex*|*--prod*) ;; *) EXTRA+=(--no-convex);; esac; case " $* " in *--spacetime*) ;; *) EXTRA+=(--no-spacetime);; esac
echo "station -> $PI  (log: ground/out/station-live.log, Ctrl-C to stop)"
while true; do
  PYTHONUNBUFFERED=1 .venv/bin/python station.py --pi "$PI" --poll 2 "${EXTRA[@]}" 2>&1 | tee -a out/station-live.log
  echo "station exited; restarting in 5 s (Ctrl-C to stop)"; sleep 5
done

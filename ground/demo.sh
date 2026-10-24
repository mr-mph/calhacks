#!/usr/bin/env bash
# Replay a recorded session through the whole pipeline (detector, agents, Convex live map, Spacetime markets) as if
# it were live, looping until Ctrl-C. The judging fallback when the balloon can't fly.
#
#   ground/demo.sh <session-dir> [site.json] [extra station.py flags]
#
# The site defaults to ground/sites/<session name>.json. Sends to the Convex production deployment (the public map)
# unless you pass --no-convex; add --no-spacetime to leave the markets alone.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SESSION="${1:?usage: demo.sh <session-dir> [site.json] [station flags]}"
shift
SESSION="$(cd "$SESSION" && pwd)"
NAME="$(basename "$SESSION")"

SITE="$HERE/sites/$NAME.json"
if [[ $# -gt 0 && $1 == *.json ]]; then
  SITE="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
  shift
fi
[[ -f $SITE ]] || { echo "no site file: $SITE (pass one as the second argument)"; exit 1; }
[[ -f $SESSION/stills/index.csv ]] || { echo "$SESSION has no stills/index.csv"; exit 1; }

VISDRONE_WEIGHTS="$HERE/runs/visdrone/weights/best.pt"
if [[ -z ${BALLOON_WEIGHTS:-} && -f $VISDRONE_WEIGHTS ]]; then
  export BALLOON_WEIGHTS="$VISDRONE_WEIGHTS" BALLOON_MODEL_NAME="${BALLOON_MODEL_NAME:-yolo11n-visdrone}"
fi

echo "Replaying $NAME with site $(basename "$SITE"). Live map: https://overhead-live.vercel.app  Markets: https://overhead-market.vercel.app"
echo "Afterwards, remove its rows from the map: (cd web && npx convex run --prod admin:purgeSession '{\"session\": \"$NAME\"}')"
cd "$HERE"
exec .venv/bin/python station.py --replay "$SESSION" --site "$SITE" --agents --loop --prod "$@"

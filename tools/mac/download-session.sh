#!/bin/bash
# Download a recorded session from the Pi over HTTP (no SSH, no password). Mac must be on Wi-Fi "BalloonNet".
#     tools/mac/download-session.sh 20261025-082727            # videos + telemetry/markers/captions/detections
#     tools/mac/download-session.sh 20261025-082727 --stills   # also the stills (thousands of JPEGs, slower)
#     tools/mac/download-session.sh                            # lists sessions on the Pi
# Files land in data/sessions/<session>/ ; re-running resumes/skips what is already complete.
set -u
PI="${PI:-http://10.42.0.1:8080}"
S="${1:-}"; STILLS=0; [ "${2:-}" = "--stills" ] && STILLS=1
cd "$(dirname "$0")/../.."
if ! curl -s -m 6 "$PI/api/status" >/dev/null; then
  echo "Cannot reach the Pi at $PI. Join Wi-Fi 'BalloonNet' (password balloon123) and retry." >&2; exit 1
fi
if [ -z "$S" ]; then
  echo "Sessions on the Pi:"; curl -s -m 10 "$PI/api/sessions" | python3 -c 'import json,sys
for s in json.load(sys.stdin): print("  %s  %6.0f MB  video %d  stills %d%s" % (s["name"], s["size_mb"], s["video_segments"], s["stills"], "  (current)" if s["current"] else ""))'
  echo "Usage: $0 <session> [--stills]"; exit 0
fi
OUT="data/sessions/$S"; mkdir -p "$OUT/video"
get() { # url, destination: skip if complete, resume if partial
  local url="$1" dst="$2" size
  size=$(curl -sI -m 15 "$url" | awk 'tolower($1)=="content-length:"{gsub(/\r/,"",$2); print $2}')
  if [ -n "$size" ] && [ -f "$dst" ] && [ "$(stat -f%z "$dst")" = "$size" ]; then printf "  ok      %s\n" "$(basename "$dst")"; return 0; fi
  printf "  getting %s (%s MB)\n" "$(basename "$dst")" "$(( ${size:-0} / 1048576 ))"
  curl -s -m 1800 -C - -o "$dst" "$url" || curl -s -m 1800 -o "$dst" "$url"
}
echo "== session $S from $PI -> $OUT =="
for f in telemetry.csv markers.csv sensors.json captions.jsonl detections.jsonl mosaic.jpg; do
  curl -s -m 10 -o /dev/null -w "%{http_code}" "$PI/data/sessions/$S/$f" | grep -q 200 && get "$PI/data/sessions/$S/$f" "$OUT/$f"
done
echo "-- video segments --"
LIST=$(curl -s -m 15 "$PI/data/sessions/$S/video/" | grep -oE "href='[^']+\.(mkv|mp4)'" | sed "s/href='//; s/'$//" | sort -u)
n=0; for href in $LIST; do get "$PI$href" "$OUT/video/$(basename "$href")"; n=$((n+1)); done
echo "-- $n video segment(s) --"
if [ "$STILLS" = 1 ]; then
  mkdir -p "$OUT/stills"; echo "-- stills --"
  get "$PI/data/sessions/$S/stills/index.csv" "$OUT/stills/index.csv"
  for href in $(curl -s -m 30 "$PI/data/sessions/$S/stills/" | grep -oE "href='[^']+\.jpg'" | sed "s/href='//; s/'$//" | sort -u); do
    dst="$OUT/stills/$(basename "$href")"; [ -s "$dst" ] || curl -s -m 60 -o "$dst" "$PI$href"
  done
  echo "   $(ls "$OUT/stills" | grep -c jpg) stills"
fi
AUDIO=$(curl -s -m 10 "$PI/data/sessions/$S/audio/" 2>/dev/null | grep -oE "href='[^']+\.mp3'" | sed "s/href='//; s/'$//" | sort -u)
if [ -n "$AUDIO" ]; then mkdir -p "$OUT/audio"; for href in $AUDIO; do dst="$OUT/audio/$(basename "$href")"; [ -s "$dst" ] || curl -s -m 60 -o "$dst" "$PI$href"; done; echo "-- $(ls "$OUT/audio" | wc -l | tr -d ' ') narrator clips --"; fi
echo "== done: $(du -sh "$OUT" | cut -f1) in $OUT =="
echo "Join the segments into one file:  ffmpeg -f concat -safe 0 -i <(for f in $OUT/video/*.mkv; do echo \"file '\$PWD/\$f'\"; done) -c copy $OUT/flight.mkv"

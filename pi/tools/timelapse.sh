#!/bin/bash
# Build a timelapse MP4 from a session's stills (works on the Pi or on the Mac after ./fetch.sh).
#     tools/timelapse.sh /data/balloon/sessions/<session> [fps=24] [out.mp4]
# Stills are saved every BALLOON_STILL_INTERVAL seconds (default 2), so 24 fps = 48x real time.
set -euo pipefail
S="${1:?session dir}"; FPS="${2:-24}"; OUT="${3:-$S/timelapse.mp4}"
N=$(ls "$S/stills"/*.jpg 2>/dev/null | wc -l | tr -d ' ')
[ "$N" -gt 0 ] || { echo "no stills in $S/stills" >&2; exit 1; }
echo "$N stills -> $OUT at $FPS fps ($(python3 -c "print(round($N/$FPS,1))") s of video)"
ffmpeg -hide_banner -loglevel error -y -framerate "$FPS" -pattern_type glob -i "$S/stills/*.jpg" \
  -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2,format=yuv420p" -c:v libx264 -preset veryfast -crf 23 -movflags +faststart "$OUT"
ls -la "$OUT"

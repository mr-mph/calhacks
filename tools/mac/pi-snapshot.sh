#!/bin/bash
# Grab a read-only health snapshot of the Pi while on Wi-Fi "BalloonNet", for checking later from another network.
#   tools/mac/pi-snapshot.sh            -> ~/pi-snapshot/<time>/
set -u
PI="${PI:-http://10.42.0.1:8080}"
out=~/pi-snapshot/$(date +%Y%m%d-%H%M%S)
mkdir -p "$out"
get() { curl -s -m 8 "$PI$1" -o "$out/$2" -w "$1 %{http_code} %{size_download}B\n"; }

get /api/status status.json
get /api/latest latest.json
get "/api/history?seconds=300" history.json
get /api/detections detections.json
get /api/captions captions.json
get /api/sessions sessions.json
get /camera/snapshot.jpg snapshot.jpg
get /mosaic.jpg mosaic.jpg
curl -s -m 4 -o /dev/null -w "camera :8081/state %{http_code}\n" "${PI%:*}:8081/state"
echo "saved to $out"

#!/bin/bash
# Copy the Pi code to the Pi and (re)start the services. Run from the Mac:
#     ./deploy.sh [user@]host        default: pi@balloon.local
#     ./deploy.sh pi@balloon.local --setup       also run setup.sh (first time / after changes to it)
#     ./deploy.sh pi@balloon.local --setup --usb-gadget
set -euo pipefail
cd "$(dirname "$0")"
TARGET="${1:-pi@balloon.local}"
[[ "$TARGET" == *@* ]] || TARGET="pi@$TARGET"
shift || true
SETUP=0; EXTRA=""
for a in "$@"; do
  [ "$a" = "--setup" ] && SETUP=1
  [ "$a" = "--usb-gadget" ] && EXTRA="--usb-gadget"
done
echo "== deploying to $TARGET =="
ssh -o ConnectTimeout=8 "$TARGET" 'sudo mkdir -p /opt/balloon && sudo chown $USER /opt/balloon'
rsync -az --delete --exclude '__pycache__' --exclude '.DS_Store' pi/ "$TARGET:/opt/balloon/"
if [ "$SETUP" = "1" ]; then
  ssh -t "$TARGET" "sudo /opt/balloon/setup.sh $EXTRA"
else
  ssh "$TARGET" 'sudo systemctl restart balloon-telemetry balloon-camera balloon-recorder balloon-mapper 2>/dev/null || echo "services not installed yet: run with --setup"; sleep 1; systemctl --no-pager --no-legend list-units "balloon-*" 2>/dev/null'
fi
HOST="${TARGET#*@}"
echo "Dashboard: http://$HOST:8080"

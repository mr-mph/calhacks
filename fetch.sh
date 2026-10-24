#!/bin/bash
# Pull recorded sessions from the Pi to ./data/ on the Mac (resumable; re-run anytime).
#     ./fetch.sh                      all sessions from tarun@balloon.local
#     ./fetch.sh tarun@balloon.local 20261024-101500   one session
set -euo pipefail
cd "$(dirname "$0")"
TARGET="${1:-tarun@balloon.local}"; [[ "$TARGET" == *@* ]] || TARGET="tarun@$TARGET"
SESSION="${2:-}"
mkdir -p data/sessions
if [ -n "$SESSION" ]; then
  rsync -avz --progress --partial "$TARGET:/data/balloon/sessions/$SESSION/" "data/sessions/$SESSION/"
else
  rsync -avz --progress --partial "$TARGET:/data/balloon/sessions/" data/sessions/
fi
echo "sessions now in $(pwd)/data/sessions:"; du -sh data/sessions/* 2>/dev/null

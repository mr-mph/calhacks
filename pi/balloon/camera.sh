#!/bin/bash
# Camera service: serves a low-CPU MJPEG stream from the USB webcam on :8081 using ustreamer.
#   http://<pi>:8081/stream     multipart MJPEG (what the dashboard <img> uses)
#   http://<pi>:8081/snapshot   single JPEG
#   http://<pi>:8081/state      JSON status
# Logitech webcams emit MJPEG natively so ustreamer just passes frames through (no re-encode).
# Falls back to the Python/OpenCV streamer if ustreamer is not installed.
set -u
[ -f /etc/default/balloon ] && . /etc/default/balloon
RES="${BALLOON_CAMERA_RES:-640x480}"
FPS="${BALLOON_CAMERA_FPS:-15}"
PORT="${BALLOON_CAMERA_PORT:-8081}"

# Pick the first real video-capture node (Logitech cams also expose a metadata node).
DEV=""
for d in /dev/v4l/by-id/*-video-index0 /dev/video0 /dev/video1 /dev/video2; do
  [ -e "$d" ] && DEV="$d" && break
done
if [ -z "$DEV" ]; then
  echo "no camera device found, retrying in 5 s" >&2
  sleep 5
  exit 1   # systemd restarts us
fi
echo "camera device: $DEV ($RES @ ${FPS}fps) on port $PORT"

if command -v ustreamer >/dev/null 2>&1; then
  exec ustreamer --device "$DEV" --format MJPEG --resolution "$RES" --desired-fps "$FPS" \
       --host 0.0.0.0 --port "$PORT" --allow-origin='*' --drop-same-frames 30 \
       --device-timeout 5 --device-error-delay 2 --persistent --slowdown
else
  echo "ustreamer not installed; using OpenCV fallback" >&2
  exec /usr/bin/python3 -m balloon.camera_fallback --device "$DEV" --res "$RES" --fps "$FPS" --port "$PORT"
fi

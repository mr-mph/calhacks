#!/bin/bash
# If wlan0 has no connection, kick NetworkManager. Runs from a systemd timer every minute.
STATE_FILE=/run/balloon-wifi-down-count
state=$(nmcli -t -f GENERAL.STATE dev show wlan0 2>/dev/null | cut -d: -f2)
# match "100 (connected)" only: a bare "connected" also matches "30 (disconnected)"
if echo "$state" | grep -q "(connected)"; then
  echo 0 > "$STATE_FILE"
  exit 0
fi
count=$(( $(cat "$STATE_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$count" > "$STATE_FILE"
echo "wlan0 state: '$state' (down $count checks)"
if [ "$count" -ge 2 ]; then
  nmcli radio wifi off; sleep 3; nmcli radio wifi on
  echo 0 > "$STATE_FILE"
fi

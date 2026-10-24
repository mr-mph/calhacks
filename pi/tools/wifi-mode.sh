#!/bin/bash
# Switch the Pi between joining a phone hotspot (client) and being its own Wi-Fi network (ap).
# AP mode: phones/laptops join "BalloonNet" and open http://10.42.0.1:8080 - no phone hotspot, no venue Wi-Fi.
#     sudo tools/wifi-mode.sh ap [ssid] [password]       default BalloonNet / balloon123
#     sudo tools/wifi-mode.sh client                     back to the configured hotspot/Wi-Fi profiles
#     tools/wifi-mode.sh status
set -euo pipefail
MODE="${1:-status}"
case "$MODE" in
  ap)
    SSID="${2:-BalloonNet}"; PSK="${3:-balloon123}"
    nmcli con delete balloon-ap >/dev/null 2>&1 || true
    nmcli con add type wifi ifname wlan0 con-name balloon-ap autoconnect yes connection.autoconnect-priority 50 \
      ssid "$SSID" 802-11-wireless.mode ap 802-11-wireless.band bg ipv4.method shared ipv6.method ignore \
      wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PSK" >/dev/null
    nmcli con up balloon-ap >/dev/null
    echo "AP up: join Wi-Fi '$SSID' (password $PSK), dashboard at http://10.42.0.1:8080"
    ;;
  client)
    nmcli con down balloon-ap >/dev/null 2>&1 || true
    nmcli con modify balloon-ap connection.autoconnect no 2>/dev/null || true
    nmcli dev wifi rescan >/dev/null 2>&1 || true
    echo "AP off; NetworkManager will rejoin a configured Wi-Fi network. Status in ~20 s: nmcli dev status"
    ;;
  status)
    nmcli -t -f NAME,DEVICE,STATE con show --active | grep -E "wlan0|wifi" || echo "wlan0 not connected"
    ip -4 addr show wlan0 | awk '/inet /{print "wlan0", $2}'
    ;;
  *) echo "usage: $0 ap [ssid] [password] | client | status" >&2; exit 1;;
esac

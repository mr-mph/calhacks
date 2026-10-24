#!/bin/bash
# Add a Wi-Fi network (e.g. the phone hotspot) to the Pi's first-boot network config and make it apply on next boot.
# Run on the Mac with the SD card in the reader:
#     ./tools/mac/sd-add-wifi.sh "Hotspot Name" "hotspot password"
# Keeps any networks already configured. Idempotent for the same SSID.
set -euo pipefail
SSID="${1:?usage: $0 SSID PASSWORD}"; PASS="${2:?usage: $0 SSID PASSWORD}"
BOOT=""; for d in /Volumes/bootfs /Volumes/boot; do [ -f "$d/network-config" ] && BOOT="$d" && break; done
[ -z "$BOOT" ] && { echo "SD boot partition not mounted" >&2; exit 1; }
SSID="$SSID" PASS="$PASS" python3 - "$BOOT/network-config" <<'PY'
import os, sys, yaml
p = sys.argv[1]; ssid = os.environ["SSID"]; pw = os.environ["PASS"]
cfg = yaml.safe_load(open(p)) or {"network": {"version": 2}}
net = cfg.setdefault("network", {}); net.setdefault("version", 2)
wl = net.setdefault("wifis", {}).setdefault("wlan0", {"dhcp4": True, "optional": True})
wl.setdefault("dhcp4", True); wl["optional"] = True
aps = wl.setdefault("access-points", {})
aps[ssid] = {"password": pw}
# hotspot first: cloud-init/NM connects to whichever is in range; both stay configured
eth = net.setdefault("ethernets", {})
eth.setdefault("usb0", {"dhcp4": True, "dhcp6": False, "optional": True})
yaml.safe_dump(cfg, open(p, "w"), default_flow_style=False, sort_keys=False)
print("network-config: wifi networks now:", list(aps.keys()))
PY
NEWID="rpi-imager-wifi-$(date +%s)"
sed -i '' "s/^instance-id: .*/instance-id: $NEWID/" "$BOOT/meta-data"
sed -i '' -E "s/(ds=nocloud;i=)[^ ]*/\1$NEWID/" "$BOOT/cmdline.txt"
echo "instance-id -> $NEWID (first-boot config re-runs once)"
sync; diskutil unmount "$BOOT" >/dev/null && echo "ejected. Card back in the Pi, power it, wait ~2 min. Put the Mac on the same hotspot, then: ssh tarun@balloon.local"

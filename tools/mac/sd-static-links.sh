#!/bin/bash
# Give the Pi fixed link-local addresses on the cable links so they never depend on DHCP:
#   usb0 (USB-C to the Mac)  169.254.2.2/16     eth0 (Ethernet to the Mac's adapter)  169.254.1.2/16
# Wi-Fi config is left as is. Run on the Mac with the SD card in the reader; ejects when done.
set -euo pipefail
BOOT=""; for d in /Volumes/bootfs /Volumes/boot; do [ -f "$d/network-config" ] && BOOT="$d" && break; done
[ -z "$BOOT" ] && { echo "SD boot partition not mounted" >&2; exit 1; }
python3 - "$BOOT/network-config" <<'PY'
import sys, yaml
p = sys.argv[1]; cfg = yaml.safe_load(open(p)); net = cfg["network"]; eth = net.setdefault("ethernets", {})
eth["usb0"] = {"dhcp4": False, "dhcp6": False, "addresses": ["169.254.2.2/16"], "optional": True}
eth["eth0"] = {"dhcp4": False, "dhcp6": False, "addresses": ["169.254.1.2/16"], "optional": True}
yaml.safe_dump(cfg, open(p, "w"), default_flow_style=False, sort_keys=False)
print(open(p).read())
PY
NEWID="rpi-imager-static-$(date +%s)"
sed -i '' "s/^instance-id: .*/instance-id: $NEWID/" "$BOOT/meta-data"
sed -i '' -E "s/(ds=nocloud;i=)[^ ]*/\1$NEWID/" "$BOOT/cmdline.txt"
echo "instance-id -> $NEWID"
sync; diskutil unmount "$BOOT" >/dev/null && echo "ejected. Pi reachable at 169.254.2.2 (USB-C) or 169.254.1.2 (Ethernet) ~90 s after power-on."

#!/bin/bash
# For a Pi with a monitor but no keyboard. Run on the Mac with the Pi's SD card in the reader:
#     ./tools/mac/sd-no-keyboard.sh "<wifi ssid>" "<wifi password>"
# On the next boot the Pi: joins that Wi-Fi (internet for apt), puts a fixed address on the Ethernet cable
# (169.254.2.2/24, Mac side 169.254.2.1), enables SSH, and PRINTS its addresses on the HDMI console.
# Then from the Mac:  ssh tarun@169.254.2.2
set -euo pipefail
SSID="${1:?usage: $0 SSID PASSWORD}"; PASS="${2:?usage: $0 SSID PASSWORD}"
BOOT=""; for d in /Volumes/bootfs /Volumes/boot; do [ -f "$d/user-data" ] && BOOT="$d" && break; done
[ -z "$BOOT" ] && { echo "SD boot partition not mounted" >&2; exit 1; }
cp "$BOOT/user-data" "$BOOT/user-data.bak"
SSID="$SSID" PASS="$PASS" python3 - "$BOOT/user-data" <<'PY'
import os, sys, yaml
p = sys.argv[1]; ssid = os.environ["SSID"]; pw = os.environ["PASS"]
cfg = yaml.safe_load(open(p)) or {}
cmds = [
  "systemctl enable --now ssh || true",
  "nmcli radio wifi on || true",
  "nmcli con delete venue-wifi >/dev/null 2>&1 || true",
  "nmcli con add type wifi ifname wlan0 con-name venue-wifi ssid '%s' wifi-sec.key-mgmt wpa-psk wifi-sec.psk '%s' connection.autoconnect yes || true" % (ssid.replace("'", "'\\''"), pw.replace("'", "'\\''")),
  "nmcli con delete cable >/dev/null 2>&1 || true",
  "nmcli con add type ethernet ifname eth0 con-name cable ipv4.method manual ipv4.addresses 169.254.2.2/24 ipv6.method link-local connection.autoconnect yes || true",
  "nmcli con up cable || true",
  "nmcli con up venue-wifi || true",
  "sleep 8",
  "( echo; echo '===== BALLOON PI NETWORK ====='; ip -br addr; echo; nmcli -t -f DEVICE,STATE,CONNECTION dev status; echo; ping -c 1 -W 2 deb.debian.org >/dev/null 2>&1 && echo 'INTERNET: yes' || echo 'INTERNET: no'; echo 'ssh tarun@169.254.2.2  (cable)'; echo '==============================' ) > /dev/tty1 2>&1 || true",
]
rc = cfg.get("runcmd") or []
rc = [c for c in rc if not (isinstance(c, str) and "BALLOON PI NETWORK" in c)]
cfg["runcmd"] = rc + cmds
cfg.setdefault("ssh_pwauth", True)
yaml.safe_dump(cfg, open(p, "w"), default_flow_style=False, sort_keys=False, width=4096)
print("user-data: runcmd now has %d steps (wifi '%s', cable 169.254.2.2, console printout)" % (len(cfg["runcmd"]), ssid))
PY
# make cloud-init treat the next boot as a new instance so runcmd runs again
NEWID="rpi-nokb-$(date +%s)"
[ -f "$BOOT/meta-data" ] && sed -i '' -E "s/^(instance[-_]id): .*/\1: $NEWID/" "$BOOT/meta-data"
grep -q "ds=nocloud;i=" "$BOOT/cmdline.txt" && sed -i '' -E "s/(ds=nocloud;i=)[^ ]*/\1$NEWID/" "$BOOT/cmdline.txt"
python3 -c "import yaml; yaml.safe_load(open('$BOOT/user-data')); print('yaml ok')"
rm -f "$BOOT/user-data.bak"; sync; diskutil unmount "$BOOT" >/dev/null && echo "EJECTED. Card into the Pi with monitor attached; the addresses appear on screen ~90 s after boot."

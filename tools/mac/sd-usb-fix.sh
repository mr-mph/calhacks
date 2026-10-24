#!/bin/bash
# Second SD-card pass (Mac, card in reader). For the cloud-init style Raspberry Pi OS image:
#  - make NetworkManager manage usb0 (it ignores USB gadgets by default) and create the usb-gadget connection
#  - (optional, --with-key) install this Mac's SSH public key for the Pi user
#  - bump the cloud-init instance-id so the first-boot config runs again and applies the above
# Idempotent.
set -euo pipefail
BOOT=""; for d in /Volumes/bootfs /Volumes/boot; do [ -f "$d/user-data" ] && BOOT="$d" && break; done
[ -z "$BOOT" ] && { echo "boot partition with user-data not found; insert the SD card" >&2; exit 1; }
PUB=""
if [ "${1:-}" = "--with-key" ]; then
  for k in ~/.ssh/id_ed25519.pub ~/.ssh/id_rsa.pub; do [ -f "$k" ] && PUB="$(cat "$k")" && break; done
  [ -z "$PUB" ] && { echo "no SSH public key in ~/.ssh" >&2; exit 1; }
fi
UD="$BOOT/user-data"
cp "$UD" "$BOOT/user-data.orig.$(date +%s)"
PUB="$PUB" python3 - "$UD" <<'PY'
import os, re, sys
p = sys.argv[1]; s = open(p).read(); pub = os.environ["PUB"].strip()
if "sd-usb-fix" in s:
    print("user-data: already patched"); sys.exit(0)
# 1) ssh key under the user: block (after the name: line)
if pub and "ssh_authorized_keys" not in s:
    s = re.sub(r'(?m)^(  name: .*)$', r'\1\n  ssh_authorized_keys:\n    - "%s"' % pub, s, count=1)
# 2) files: udev override so NetworkManager manages the gadget interface
s += '''
# --- added by sd-usb-fix ---
write_files:
  - path: /etc/udev/rules.d/86-nm-manage-usb-gadget.rules
    content: |
      ENV{DEVTYPE}=="gadget", ENV{NM_UNMANAGED}="0"
  - path: /etc/NetworkManager/conf.d/wifi-powersave.conf
    content: |
      [connection]
      wifi.powersave = 2
'''
# 3) runcmd entries (append to the existing list; cloud-init rejects duplicate keys)
cmds = '''  - [ sh, -c, "udevadm control --reload && udevadm trigger --subsystem-match=net --action=add || true" ]
  - [ sh, -c, "nmcli device set usb0 managed yes || true" ]
  - [ sh, -c, "nmcli con show usb-gadget >/dev/null 2>&1 || nmcli con add type ethernet ifname usb0 con-name usb-gadget ipv4.method auto ipv4.link-local fallback ipv4.dhcp-timeout 20 ipv6.method link-local connection.autoconnect yes connection.autoconnect-priority 10 || nmcli con add type ethernet ifname usb0 con-name usb-gadget ipv4.method auto ipv6.method link-local connection.autoconnect yes" ]
  - [ sh, -c, "nmcli con up usb-gadget || true" ]
'''
if re.search(r'(?m)^runcmd:', s):
    # insert after the last existing runcmd item
    lines = s.split("\n"); out = []; in_run = False; inserted = False
    for i, line in enumerate(lines):
        if line.startswith("runcmd:"): in_run = True; out.append(line); continue
        if in_run and not inserted and not line.startswith("  -") and not line.startswith("    "):
            out.append(cmds.rstrip("\n")); inserted = True; in_run = False
        out.append(line)
    if not inserted: out.append(cmds.rstrip("\n"))
    s = "\n".join(out)
else:
    s += "runcmd:\n" + cmds
open(p, "w").write(s)
print("user-data: patched (usb0 managed + connection%s)" % (", ssh key" if pub else ""))
PY
# 4) new instance-id in meta-data and cmdline so cloud-init re-runs per-instance config
NEWID="rpi-imager-usb-$(date +%s)"
sed -i '' "s/^instance-id: .*/instance-id: $NEWID/" "$BOOT/meta-data"
sed -i '' -E "s/(ds=nocloud;i=)[^ ]*/\1$NEWID/" "$BOOT/cmdline.txt"
echo "instance-id -> $NEWID"
echo "--- cmdline ---"; cat "$BOOT/cmdline.txt"; echo
python3 -c "import yaml,sys; yaml.safe_load(open('$UD')); print('user-data: valid YAML')" 2>/dev/null || echo "(pyyaml not installed; skipped YAML check)"
sync; diskutil unmount "$BOOT" >/dev/null && echo "ejected. Card back in the Pi, USB-C to the Mac, wait ~2 min (first boot re-runs, one reboot)."

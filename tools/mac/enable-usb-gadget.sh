#!/bin/bash
# Run on the Mac with the Pi's microSD card in a reader. Turns on USB-C Ethernet gadget mode so that
# plugging the Pi's USB-C port into the Mac gives a network link (ssh tarun@balloon.local) with no Wi-Fi.
# Edits only the FAT boot partition (bootfs). Safe to re-run.
set -euo pipefail
BOOT=""
for d in /Volumes/bootfs /Volumes/boot; do [ -f "$d/config.txt" ] && BOOT="$d" && break; done
if [ -z "$BOOT" ]; then
  echo "No Raspberry Pi boot partition mounted (looked for /Volumes/bootfs/config.txt). Insert the SD card." >&2
  exit 1
fi
echo "boot partition: $BOOT"
if ! grep -q 'dr_mode=peripheral' "$BOOT/config.txt"; then
  printf '\n[all]\ndtoverlay=dwc2,dr_mode=peripheral\n' >> "$BOOT/config.txt"
  echo "config.txt: added dtoverlay=dwc2,dr_mode=peripheral"
else
  echo "config.txt: dwc2 overlay already present"
fi
if ! grep -q 'modules-load=dwc2' "$BOOT/cmdline.txt"; then
  # cmdline.txt is a single line; insert right after rootwait
  sed -i '' 's/rootwait/rootwait modules-load=dwc2,g_ether/' "$BOOT/cmdline.txt"
  echo "cmdline.txt: added modules-load=dwc2,g_ether"
else
  echo "cmdline.txt: already has modules-load=dwc2"
fi
[ -f "$BOOT/ssh" ] || touch "$BOOT/ssh"
echo "--- cmdline.txt now: ---"; cat "$BOOT/cmdline.txt"
sync
diskutil unmount "$BOOT" >/dev/null && echo "ejected. Put the card back in the Pi, connect USB-C to the Mac, wait ~90 s."
echo "On the Mac a new network device 'RNDIS/Ethernet Gadget' appears (System Settings > Network)."
echo "Then:  ssh-copy-id tarun@balloon.local"

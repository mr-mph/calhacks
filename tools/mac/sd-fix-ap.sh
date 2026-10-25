#!/bin/bash
# Recover the Pi's Wi-Fi access point from the SD card (Mac, card in reader). On the next boot a one-shot stage:
#   removes the local-only dnsmasq override, dumps NetworkManager/dnsmasq logs to balloon-ap-debug.txt on the card,
#   re-enables autoconnect for balloon-ap, then reboots into normal operation.
set -euo pipefail
BOOT="${BOOT_DIR:-}"; [ -n "$BOOT" ] || for d in /Volumes/bootfs /Volumes/boot; do [ -f "$d/cmdline.txt" ] && BOOT="$d" && break; done
[ -z "$BOOT" ] && { echo "SD boot partition not mounted" >&2; exit 1; }
mkdir -p "$BOOT/balloon"
cat > "$BOOT/balloon/fixap.sh" <<'EOS'
#!/bin/bash
D=/boot/firmware/balloon-ap-debug.txt
{
  echo "=== fixap $(date) ==="
  echo "--- dnsmasq-shared.d ---"; ls -la /etc/NetworkManager/dnsmasq-shared.d 2>/dev/null; cat /etc/NetworkManager/dnsmasq-shared.d/*.conf 2>/dev/null
  echo "--- connections ---"; nmcli -t -f NAME,TYPE,AUTOCONNECT,AUTOCONNECT-PRIORITY con show 2>/dev/null
  echo "--- NetworkManager journal (previous boot, wlan0/dnsmasq/shared) ---"
  journalctl -b -1 -u NetworkManager --no-pager 2>/dev/null | grep -iE "wlan0|dnsmasq|shared|balloon-ap|fail|error" | tail -60
  echo "--- dnsmasq journal (previous boot) ---"; journalctl -b -1 --no-pager 2>/dev/null | grep -i dnsmasq | tail -20
} > "$D" 2>&1
rm -f /etc/NetworkManager/dnsmasq-shared.d/balloon-local-only.conf
nmcli con modify balloon-ap connection.autoconnect yes 2>/dev/null || true
sed -i 's| systemd.run=[^ ]*||; s| systemd.run_success_action=[^ ]*||; s| systemd.unit=kernel-command-line.target||' /boot/firmware/cmdline.txt
echo "override removed; rebooting" >> "$D"; sync
exit 0
EOS
chmod +x "$BOOT/balloon/fixap.sh"
sed -i '' 's| systemd.run=[^ ]*||; s| systemd.run_success_action=[^ ]*||; s| systemd.unit=kernel-command-line.target||' "$BOOT/cmdline.txt"
sed -i '' 's|$| systemd.run=/boot/firmware/balloon/fixap.sh systemd.run_success_action=reboot systemd.unit=kernel-command-line.target|' "$BOOT/cmdline.txt"
tr -d '\n' < "$BOOT/cmdline.txt" > "$BOOT/cmdline.tmp" && mv "$BOOT/cmdline.tmp" "$BOOT/cmdline.txt"
echo "cmdline: $(cat "$BOOT/cmdline.txt")"
sync; [ -n "${BOOT_DIR:-}" ] && exit 0; diskutil unmount "$BOOT" >/dev/null && echo "EJECTED. Card into the Pi, power on: it fixes itself and reboots (~1 min), then BalloonNet is back."

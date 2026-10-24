#!/bin/bash
# Flash Raspberry Pi OS Lite (64-bit) onto a microSD card with hostname, user, SSH and Wi-Fi preconfigured,
# so the Pi comes up as tarun@balloon.local with no monitor. Run from the Mac:
#     ./flash.sh /dev/diskN          find N with: diskutil list external physical (built-in reader shows as internal)
# Prompts for anything not set in the environment: WIFI_SSID, WIFI_PASSWORD, PI_PASSWORD.
# Optional: PI_USER (tarun), PI_HOSTNAME (balloon), WIFI_COUNTRY (US), PI_TIMEZONE (America/Los_Angeles).
set -euo pipefail
IMAGER="/Applications/Raspberry Pi Imager.app/Contents/MacOS/rpi-imager"
IMAGE_URL="https://downloads.raspberrypi.com/raspios_lite_arm64_latest"
DEVICE="${1:?usage: ./flash.sh /dev/diskN}"
PI_USER="${PI_USER:-tarun}"
PI_HOSTNAME="${PI_HOSTNAME:-balloon}"
WIFI_COUNTRY="${WIFI_COUNTRY:-US}"
PI_TIMEZONE="${PI_TIMEZONE:-America/Los_Angeles}"

[ -x "$IMAGER" ] || { echo "Raspberry Pi Imager missing: brew install --cask raspberry-pi-imager"; exit 1; }
# refuse anything that isn't removable media, so a typo can't wipe an internal drive
diskutil info "$DEVICE" | grep -Eq 'Removable Media: +(Removable|Yes)' || { echo "$DEVICE is not a removable card, refusing"; exit 1; }
diskutil info "$DEVICE" | grep -E 'Media Name|Disk Size'

[ -n "${WIFI_SSID:-}" ] || read -rp "Wi-Fi name: " WIFI_SSID
[ -n "${WIFI_PASSWORD:-}" ] || { read -rsp "Wi-Fi password: " WIFI_PASSWORD; echo; }
[ -n "${PI_PASSWORD:-}" ] || { read -rsp "Password for $PI_USER on the Pi: " PI_PASSWORD; echo; }

# macOS's LibreSSL can't make SHA-512 hashes; Homebrew openssl can
if HASH=$(openssl passwd -6 "$PI_PASSWORD" 2>/dev/null); then
  PASSWD_LINE="passwd: $HASH"
else
  PASSWD_LINE="plain_text_passwd: \"$PI_PASSWORD\""
fi

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/user-data" <<EOF
#cloud-config
hostname: $PI_HOSTNAME
manage_etc_hosts: true
packages:
- avahi-daemon
apt:
  conf: |
    Acquire {
      Check-Date "false";
    };
timezone: $PI_TIMEZONE
keyboard:
  model: pc105
  layout: "us"
users:
- name: $PI_USER
  groups: users,adm,dialout,audio,netdev,video,plugdev,cdrom,games,input,gpio,spi,i2c,render,sudo
  shell: /bin/bash
  lock_passwd: false
  $PASSWD_LINE
ssh_pwauth: true
enable_ssh: true
runcmd:
- systemctl enable --now ssh
EOF
cat > "$TMP/network-config" <<EOF
network:
  version: 2
  wifis:
    renderer: NetworkManager
    wlan0:
      dhcp4: true
      optional: true
      regulatory-domain: "$WIFI_COUNTRY"
      access-points:
        "$WIFI_SSID":
          password: "$WIFI_PASSWORD"
EOF

echo "== writing Raspberry Pi OS Lite (64-bit) to $DEVICE (erases it) =="
"$IMAGER" --cli --cloudinit-userdata "$TMP/user-data" --cloudinit-networkconfig "$TMP/network-config" "$IMAGE_URL" "$DEVICE"
echo "Done. Boot the Pi, wait ~3 min, then: ssh $PI_USER@$PI_HOSTNAME.local  (Mac must be on \"$WIFI_SSID\")"

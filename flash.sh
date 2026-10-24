#!/bin/bash
# Flash Raspberry Pi OS Lite (64-bit) onto a microSD card with hostname, user, SSH and Wi-Fi preconfigured,
# so the Pi comes up as tarun@balloon.local with no monitor. Run from the Mac:
#     ./flash.sh /dev/diskN          find N with: diskutil list external physical (built-in reader shows as internal)
# Prompts for anything not set in the environment: WIFI_SSID, WIFI_PASSWORD, PI_PASSWORD.
# Optional: PI_USER (tarun), PI_HOSTNAME (balloon), WIFI_COUNTRY (US), PI_TIMEZONE (America/Los_Angeles),
# PI_SSH_KEY (~/.ssh/id_ed25519.pub if it exists: authorized on the Pi so ssh needs no password),
# IMAGE (a local .img.xz instead of downloading the latest), USB_GADGET (1: the Pi's USB-C port is also a network link, so ssh works over the power cable with no Wi-Fi).
set -euo pipefail
IMAGER="/Applications/Raspberry Pi Imager.app/Contents/MacOS/rpi-imager"
IMAGE="${IMAGE:-https://downloads.raspberrypi.com/raspios_lite_arm64_latest}"
DEVICE="${1:?usage: ./flash.sh /dev/diskN}"
PI_USER="${PI_USER:-tarun}"
PI_HOSTNAME="${PI_HOSTNAME:-balloon}"
WIFI_COUNTRY="${WIFI_COUNTRY:-US}"
PI_TIMEZONE="${PI_TIMEZONE:-America/Los_Angeles}"
PI_SSH_KEY="${PI_SSH_KEY:-$HOME/.ssh/id_ed25519.pub}"
USB_GADGET="${USB_GADGET:-1}"

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
KEY_LINES=""
[ -f "$PI_SSH_KEY" ] && KEY_LINES="  ssh_authorized_keys:
  - $(cat "$PI_SSH_KEY")"

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
$KEY_LINES
ssh_pwauth: true
enable_ssh: true
# usb0 only exists with the dwc2 overlay below; link-local on both ends means no DHCP is needed, mDNS finds the Pi.
# Same connection name setup.sh --usb-gadget checks for, so it won't add a second one.
write_files:
- path: /etc/NetworkManager/system-connections/usb-gadget.nmconnection
  permissions: '0600'
  content: |
    [connection]
    id=usb-gadget
    type=ethernet
    interface-name=usb0
    autoconnect=true
    [ipv4]
    method=link-local
    [ipv6]
    method=link-local
runcmd:
- systemctl enable --now ssh
- nmcli connection reload || true
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
"$IMAGER" --cli --disable-eject --cloudinit-userdata "$TMP/user-data" --cloudinit-networkconfig "$TMP/network-config" "$IMAGE" "$DEVICE"

if [ "$USB_GADGET" = "1" ]; then
  diskutil mountDisk "$DEVICE" >/dev/null
  BOOT=$(diskutil info "${DEVICE}s1" | awk -F': *' '/Mount Point/{print $2}')
  [ -f "$BOOT/cmdline.txt" ] || { echo "boot partition not found at '$BOOT', USB gadget not enabled"; exit 1; }
  grep -q 'modules-load=dwc2' "$BOOT/cmdline.txt" || sed -i '' '1 s/$/ modules-load=dwc2,g_ether/' "$BOOT/cmdline.txt"
  grep -q '^dtoverlay=dwc2' "$BOOT/config.txt" || printf '\n[all]\ndtoverlay=dwc2,dr_mode=peripheral\n' >> "$BOOT/config.txt"
  echo "== USB gadget enabled: $(tail -1 "$BOOT/config.txt"); cmdline: $(grep -o 'modules-load=[^ ]*' "$BOOT/cmdline.txt")"
fi
diskutil eject "$DEVICE" >/dev/null
echo "Done. Boot the Pi, wait ~3 min, then: ssh $PI_USER@$PI_HOSTNAME.local"
echo "  over Wi-Fi: Mac on \"$WIFI_SSID\"; over USB (USB_GADGET=1): Pi's USB-C port cabled to the Mac"

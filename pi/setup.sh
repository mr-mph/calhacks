#!/bin/bash
# One-shot provisioning for the Pi. Run ON THE PI as root after deploy.sh copied the code to /opt/balloon:
#     sudo /opt/balloon/setup.sh [--usb-gadget]
# Idempotent: safe to re-run.
set -euo pipefail
USER_NAME="${BALLOON_USER:-${SUDO_USER:-pi}}"
USB_GADGET=0
for a in "$@"; do [ "$a" = "--usb-gadget" ] && USB_GADGET=1; done
echo "== balloon setup for user $USER_NAME =="

echo "== packages =="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-flask python3-smbus2 python3-numpy python3-opencv python3-requests \
  python3-gpiozero i2c-tools v4l-utils ffmpeg avahi-daemon network-manager >/dev/null
apt-get install -y -qq ustreamer >/dev/null || echo "!! ustreamer not available; camera will use the OpenCV fallback"

echo "== I2C =="
raspi-config nonint do_i2c 0 || true
grep -q '^dtparam=i2c_arm=on' /boot/firmware/config.txt 2>/dev/null || echo 'dtparam=i2c_arm=on' >> /boot/firmware/config.txt
# faster I2C makes the 5 Hz loop comfortable
grep -q 'i2c_arm_baudrate' /boot/firmware/config.txt || sed -i 's/^dtparam=i2c_arm=on.*/dtparam=i2c_arm=on,i2c_arm_baudrate=400000/' /boot/firmware/config.txt
modprobe i2c-dev 2>/dev/null || true

echo "== user groups =="
for g in i2c gpio video dialout; do getent group "$g" >/dev/null && usermod -aG "$g" "$USER_NAME"; done

echo "== data dir =="
mkdir -p /data/balloon/sessions
chown -R "$USER_NAME:$USER_NAME" /data/balloon

echo "== config =="
[ -f /etc/default/balloon ] || install -m 644 /opt/balloon/default.env /etc/default/balloon

echo "== Wi-Fi: disable power save (smoother stream) =="
mkdir -p /etc/NetworkManager/conf.d
cat > /etc/NetworkManager/conf.d/wifi-powersave.conf <<CONF
[connection]
wifi.powersave = 2
CONF

if [ "$USB_GADGET" = "1" ]; then
  echo "== USB-C ethernet gadget (ssh balloon.local over the USB-C cable) =="
  grep -q '^dtoverlay=dwc2' /boot/firmware/config.txt || echo 'dtoverlay=dwc2,dr_mode=peripheral' >> /boot/firmware/config.txt
  grep -q 'modules-load=dwc2' /boot/firmware/cmdline.txt || sed -i 's/rootwait/rootwait modules-load=dwc2,g_ether/' /boot/firmware/cmdline.txt
  # usb0: take DHCP from the Mac if it runs Internet Sharing (gives the Pi internet for apt), otherwise fall back
  # to a link-local 169.254.x.x address. mDNS (balloon.local) works either way.
  nmcli con show usb-gadget >/dev/null 2>&1 || nmcli con add type ethernet ifname usb0 con-name usb-gadget \
    ipv4.method auto ipv4.link-local fallback ipv4.dhcp-timeout 20 ipv6.method link-local \
    connection.autoconnect yes connection.autoconnect-priority 10 >/dev/null || true
  echo "   (takes effect after reboot)"
fi

echo "== services =="
for f in /opt/balloon/systemd/*; do
  sed "s/__USER__/$USER_NAME/g" "$f" > "/etc/systemd/system/$(basename "$f")"
done
systemctl daemon-reload
systemctl enable balloon-telemetry balloon-camera balloon-recorder balloon-mapper balloon-wifi-watchdog.timer >/dev/null
systemctl restart balloon-telemetry balloon-camera balloon-recorder balloon-mapper
systemctl start balloon-wifi-watchdog.timer
sleep 2
systemctl --no-pager --no-legend list-units 'balloon-*'

echo
echo "== I2C devices seen now (expect 04 or 08 = Base Hat ADC, 76/77 barometer, 53/19/4c/68 accel, 58 SGP30) =="
i2cdetect -y 1 || true
echo
IP=$(hostname -I | awk '{print $1}')
echo "Dashboard: http://$(hostname).local:8080   or   http://$IP:8080"
echo "Camera:    http://$IP:8081/stream"
echo "Logs:      journalctl -fu balloon-telemetry"
[ "$USB_GADGET" = "1" ] && echo "Reboot now for USB gadget mode: sudo reboot"
exit 0

#!/bin/bash
# Go / no-go checklist. Run on the Pi right before launch:  /opt/balloon/tools/preflight.sh
PASS=0; FAIL=0
ok()   { echo "  [ OK ] $1"; PASS=$((PASS+1)); }
bad()  { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }
warn() { echo "  [WARN] $1"; }
echo "== balloon preflight $(date) =="
for s in balloon-telemetry balloon-camera balloon-recorder balloon-mapper; do
  systemctl is-active --quiet "$s" && ok "$s running" || bad "$s NOT running  (journalctl -u $s -n 30)"
done
systemctl is-active --quiet balloon-wifi-watchdog.timer && ok "wifi watchdog timer" || warn "wifi watchdog timer not active"

ST=$(curl -s -m 3 http://127.0.0.1:8080/api/status)
if [ -n "$ST" ]; then
  ok "dashboard answering on :8080"
  python3 - "$ST" <<'PY'
import json, sys
st = json.loads(sys.argv[1])
names = [s["name"] for s in st["sensors"]["sensors"]]
print("  sensors:", ", ".join(names))
print("  I2C:", ", ".join(st["sensors"]["i2c_addresses"]) or "none")
for e in st["sensors"]["errors"]: print("  [WARN] sensor error:", e)
bad = [k for k, v in st["failures"].items() if v]
print("  [FAIL] sensors failing reads: %s" % bad if bad else "  [ OK ] no sensor read failures")
print("  [ OK ] altitude zeroed at %.2f hPa" % st["p0_hpa"] if st["zeroed"] else "  [WARN] altitude not zeroed yet (no barometer?)")
print("  session:", st["session"], "samples:", st["samples"])
cam = st.get("camera")
print("  [ OK ] camera online" if cam and cam.get("result", {}).get("source", {}).get("online") else "  [FAIL] camera offline")
PY
else
  bad "dashboard not answering on :8080"
fi

L=$(curl -s -m 3 http://127.0.0.1:8080/api/latest)
echo "  latest: $(echo "$L" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(" ".join("%s=%s"%(k,d.get(k)) for k in ("altitude_m","pressure_hpa","temp_c","tilt_deg","light_pct","uv_index","aq_raw","eco2_ppm","cpu_temp_c","wifi_rssi_dbm","disk_free_gb")))' 2>/dev/null)"

FREE=$(df --output=avail -BG /data/balloon 2>/dev/null | tail -1 | tr -dc '0-9')
[ -n "$FREE" ] && { [ "$FREE" -ge 3 ] && ok "SD free: ${FREE} GB" || bad "SD free only ${FREE} GB (video stops < 1 GB)"; }
SESSION=$(cat /data/balloon/current_session 2>/dev/null)
if [ -n "$SESSION" ]; then
  N=$(wc -l < "$SESSION/telemetry.csv"); [ "$N" -gt 10 ] && ok "telemetry.csv growing ($N rows)" || bad "telemetry.csv has only $N rows"
  V=$(ls "$SESSION/video" 2>/dev/null | wc -l); [ "$V" -gt 0 ] && ok "video segments: $V" || warn "no video segments yet (wait 60 s after start)"
  S=$(find "$SESSION/stills" -name '*.jpg' 2>/dev/null | wc -l | tr -d ' '); [ "$S" -gt 0 ] && ok "stills: $S" || warn "no stills yet"
fi
T=$(vcgencmd measure_temp 2>/dev/null | tr -dc '0-9.'); [ -n "$T" ] && { awk "BEGIN{exit !($T < 75)}" && ok "CPU ${T}C" || warn "CPU hot: ${T}C"; }
TH=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2); [ "$TH" = "0x0" ] && ok "power OK (not throttled)" || warn "throttled flags $TH -> check power bank / cable"
if nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep -q "^balloon-ap:wlan0"; then
  ok "wifi: access point BalloonNet ($(iw dev wlan0 station dump 2>/dev/null | grep -c Station) client(s) connected)"
else
  RSSI=$(awk 'NR>2 && /wlan/{print int($4)}' /proc/net/wireless); [ -n "$RSSI" ] && { [ "$RSSI" -gt -75 ] && ok "wifi ${RSSI} dBm" || warn "weak wifi ${RSSI} dBm"; } || warn "wlan0 not associated"
fi
IP=$(hostname -I | awk '{print $1}')
echo "  dashboard: http://$IP:8080   (http://$(hostname).local:8080)"
nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep -q "^balloon-ap:wlan0" && echo "  on BalloonNet: http://10.42.0.1:8080"
echo "== $PASS ok, $FAIL failed =="
[ "$FAIL" -eq 0 ] && echo "GO" || echo "NO-GO"

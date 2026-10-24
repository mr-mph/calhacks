# CalHacks balloon payload

Contributors (people or AI agents): read **CLAUDE.md** first for architecture, conventions, and how to test without hardware.

Tethered helium-balloon payload on a Raspberry Pi 4 + Grove Base Hat + Logitech USB webcam.
The Pi logs every sensor and the camera to its SD card no matter what, and serves a live dashboard
(video + real-time charts) to any phone or laptop on the same Wi-Fi (or over the USB-C cable).

```
pi/                      everything that runs on the Pi (deployed to /opt/balloon)
  balloon/server.py      dashboard + API + SSE, also runs the sampler thread        :8080
  balloon/sensors.py     I2C auto-detection, 5 Hz sampling, altitude/tilt, CSV logging
  balloon/drivers/       BMP280/BME280/BMP180, ADXL345/LIS3DH/MMA7660/MPU6050, Grove ADC, SGP30, Pi stats
  balloon/camera.sh      ustreamer MJPEG stream (fallback: camera_fallback.py)          :8081
  balloon/recorder.py    ffmpeg copies the stream to 60 s .mkv segments + a still every 2 s
  balloon/mapper.py      stitches the downward-camera stills into mosaic.jpg (dashboard "Map" tab)
  balloon/static/        dashboard (plain HTML/JS, uPlot vendored, works offline)
  systemd/               one unit per service, all Restart=always, start at boot
  setup.sh               provisioning (apt packages, I2C, groups, units, optional USB gadget)
  tools/                 i2c_check.py, test_sensor.py
deploy.sh                rsync pi/ to the Pi and restart services
```

Data layout on the SD card: `/data/balloon/sessions/<YYYYmmdd-HHMMSS>/`
`telemetry.csv` (fixed schema, one row per sample), `markers.csv`, `sensors.json`,
`video/*.mkv`, `stills/*.jpg` + `stills/index.csv`, `mosaic.jpg`. Everything is downloadable from the dashboard.

## 1. Flash the Pi (once)

Scripted: `brew install --cask raspberry-pi-imager`, put the microSD in a reader, then
`./flash.sh /dev/diskN` (find N with `diskutil list`). It asks for the Wi-Fi name/password and the Pi password and
writes Raspberry Pi OS Lite (64-bit) as `tarun@balloon.local` with SSH on. Or by hand in the Imager app:

1. `brew install --cask raspberry-pi-imager`, put the microSD in a reader.
2. Raspberry Pi Imager → Pi 4 → **Raspberry Pi OS (64-bit)** → your card → Next → **Edit settings**:
   hostname `balloon`, user `tarun` + password, Wi-Fi = the **phone hotspot** SSID/password, locale;
   Services → enable SSH (password, or paste `~/.ssh/id_ed25519.pub`).
3. Boot the Pi with the webcam attached. Put the Mac on the same hotspot. `ssh tarun@balloon.local`.

## 2. Wire the Grove sensors (Base Hat)

| Sensor | Port |
|---|---|
| Barometer BMP280 / BME280 | any **I2C** port |
| Accelerometer | any **I2C** port |
| Air quality v1.3 (analog) | **A4** |
| SGP30 VOC/eCO2 (if that's the air sensor) | any **I2C** port |
| Light sensor | **A0** |
| UV sensor | **A2** |
| SG90 servo (optional) | **D18** (PWM), set `BALLOON_SERVO=1` |

I2C sensors are auto-detected by address. Analog channels are set in `/etc/default/balloon` (`BALLOON_ANALOG`).

## 3. Deploy

```bash
./deploy.sh tarun@balloon.local --setup              # first time: copies code, installs packages, enables services
./deploy.sh tarun@balloon.local --setup --usb-gadget  # ...and also make the USB-C port an Ethernet link (reboot after)
./deploy.sh tarun@balloon.local                       # later: copy code + restart services
```

Then open **http://balloon.local:8080** (or `http://<pi-ip>:8080`) on a phone or laptop.

## 4. Check the sensors one at a time (on the Pi)

```bash
cd /opt/balloon
i2cdetect -y 1                       # expect 04 (ADC), 77 or 76 (barometer), 53/19/4c/68 (accel), 58 (SGP30)
python3 tools/i2c_check.py           # names each address
python3 tools/test_sensor.py -k barometer   # ~1000-1020 hPa, room temperature
python3 tools/test_sensor.py -k accel       # az ~ +1.0 g when flat; tilt it and watch ax/ay
python3 tools/test_sensor.py -k analog      # light_pct drops when covered; aq_raw rises if you breathe on it
journalctl -fu balloon-telemetry     # live log of the service
```

## 5. Before launch and after landing

```bash
ssh tarun@balloon.local /opt/balloon/tools/preflight.sh   # GO / NO-GO: services, camera, sensors, disk, power, wifi
./fetch.sh                                                 # pull all sessions to ./data/sessions on the Mac
python3 analysis/plot_session.py data/sessions/<session>   # one-page flight summary PNG (needs matplotlib)
python3 pi/tests/test_drivers_fake_i2c.py                  # driver math vs Bosch datasheet, no hardware needed
```

Name a marker "launch" (the Mark button) and the dashboard shows time aloft; the peak altitude chip tracks the max.

- **Replay**: open `http://balloon.local:8080/?replay=<session>` (or the "replay" link in Sensors & sessions) to play back
  any recorded flight at 1-50x with the stills as the video track. Works for the demo if the balloon can't fly.
- **Vertical profiles**: temperature, air quality, light, UV, humidity, eCO2 and sway plotted against altitude
  (appear once the payload has moved more than 3 m).
- **QR** button in the header shows a QR code pointing at the dashboard for judges' phones.

## 6. Operating notes

- Altitude is relative: zeroed to the median pressure of the first 5 s after the service starts. Press **Zero alt** on
  the dashboard (or `curl -X POST http://balloon.local:8080/api/zero`) on the ground right before launch.
- **Mark** writes a timestamped note to `markers.csv` and draws it on the altitude chart (launch, max altitude, etc.).
- Video recording pauses automatically when the SD card has < 1 GB free; CSV logging never stops.
- Services survive Wi-Fi loss (nothing depends on the network); a timer kicks Wi-Fi if it stays down > 2 min.
- USB-C gadget mode: after `--usb-gadget` + reboot, plugging the Pi's USB-C port into the Mac gives you
  `ssh tarun@balloon.local` and the dashboard over the cable, no Wi-Fi needed (the Pi hands the Mac an address).
- Post-flight map of higher quality: `python3 -m balloon.mapper --batch /data/balloon/sessions/<s>/stills -o map.jpg --every 2`
- Develop the dashboard on a laptop with fake sensors:
  `cd pi && BALLOON_SIM=1 BALLOON_DATA=/tmp/balloon python3 -m balloon.server` → http://localhost:8080

## Tuning (`/etc/default/balloon`, then `sudo systemctl restart 'balloon-*'`)

`BALLOON_SAMPLE_HZ` (5), `BALLOON_CAMERA_RES` (640x480), `BALLOON_CAMERA_FPS` (15),
`BALLOON_ANALOG` (aq:4; add light:0, uv:2 if present), `BALLOON_STILL_INTERVAL` (2), `BALLOON_MIN_FREE_GB` (1), `BALLOON_SERVO` (0).

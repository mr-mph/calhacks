# Contributor guide (humans and AI agents)

Read this before changing anything. It covers what the system is, how it is wired together, how to test
without hardware, and the conventions that keep it working on the Pi during the hackathon.

## What this is

A tethered helium-balloon payload for CalHacks (Oct 2026). A Raspberry Pi 4 with a Seeed Grove Base Hat and a
Logitech USB webcam logs sensors + video to its SD card and serves a live dashboard over Wi-Fi (phone hotspot) or
over the USB-C cable. Weight budget is ~400 g total, power is a USB-C power bank. Team of 4, time-boxed.

Hardware we actually have (confirmed by the team):
- Grove barometer/temperature (BMP280 family, I2C 0x76/0x77)
- Grove 3-axis accelerometer (I2C; exact chip unknown until `i2cdetect` runs: 0x53 ADXL345, 0x19 LIS3DHTR, 0x4c MMA7660)
- Grove Air Quality Sensor v1.3 (analog, port A4, read through the Base Hat ADC at I2C 0x04)
- Logitech USB webcam, 16 GB microSD
- Possibly an MPU-6050 (I2C 0x68, accel + gyro) if someone attaches it
We do NOT have light, UV, humidity, or SGP30 sensors. Drivers for them exist but must stay off by default.

Pi: hostname `balloon`, user `tarun`, Raspberry Pi OS 64-bit (Bookworm or newer, NetworkManager, /boot/firmware).
Development link is USB-C gadget networking (tools/mac/enable-usb-gadget.sh, then ssh over the cable);
flight link is a phone hotspot (venue Wi-Fi blocks peer traffic). Never commit the Pi password or any credential. SSH uses keys (`ssh-copy-id tarun@balloon.local`).

## Architecture (all on the Pi, under /opt/balloon, one systemd unit each)

```
balloon-telemetry  python3 -m balloon.server     :8080  sampler thread + CSV + Flask dashboard + SSE
balloon-camera     balloon/camera.sh             :8081  ustreamer MJPEG (/stream /snapshot /state); OpenCV fallback
balloon-recorder   python3 -m balloon.recorder          ffmpeg -c copy stream -> video/*.mkv (60 s segments); stills every 2 s
balloon-mapper     python3 -m balloon.mapper            stitches stills -> mosaic.jpg (ORB + RANSAC similarity, incremental)
balloon-wifi-watchdog.timer                            kicks NetworkManager if wlan0 is down 2 checks in a row
```

Data: `/data/balloon/sessions/<YYYYmmdd-HHMMSS>/` with `telemetry.csv` (fixed schema `sensors.COLUMNS`),
`markers.csv`, `sensors.json`, `video/`, `stills/` + `stills/index.csv`, `mosaic.jpg`.
`/data/balloon/current_session` holds the active session path; recorder and mapper follow it.
Config: environment variables, documented in `pi/balloon/config.py`, set in `/etc/default/balloon` (template `pi/default.env`).

Key files:
- `pi/balloon/sensors.py` detection (`_known_addresses`), sampling loop, altitude/tilt derivation, CSV, SSE fan-out
- `pi/balloon/drivers/*.py` one class per chip: `KIND`, `FIELDS`, `name`, `read() -> dict`
- `pi/balloon/server.py` HTTP API (see docstring at top for the route list)
- `pi/balloon/static/app.js` dashboard; chart/tile/profile definitions are the `CHARTS`, `TILES`, `PROFILES` arrays at the top
- `pi/setup.sh` provisioning on the Pi (idempotent), `deploy.sh` rsync + restart from the Mac, `fetch.sh` pull sessions
- `pi/tools/` preflight.sh (go/no-go), i2c_check.py, test_sensor.py; `pi/tests/` hardware-free tests; `analysis/` post-flight plots

## How to test without the Pi

```bash
cd pi && BALLOON_SIM=1 BALLOON_DATA=/tmp/balloon python3 -m balloon.server     # fake sensors matching our kit -> http://localhost:8080
BALLOON_SIM_ALL=1 ...                                                          # also fakes humidity/light/UV/SGP30 code paths
python3 pi/tests/test_drivers_fake_i2c.py                                      # real drivers against a fake smbus2 (Bosch datasheet values)
python3 -m balloon.camera_fallback --device some_video.mp4 --port 8081         # fake camera; recorder + mapper then work end to end
```
Needs: flask, numpy (dashboard), opencv-python-headless (camera fallback / mapper), matplotlib (analysis). No smbus2 on the Mac.
The dashboard has been verified in headless Chrome; any JS exception shows as a red banner at the top of the page.

## Deploy / operate

```bash
./deploy.sh tarun@balloon.local --setup        # first time (apt, I2C, units); add --usb-gadget for USB-C networking
./deploy.sh tarun@balloon.local                # later: rsync + restart
ssh tarun@balloon.local /opt/balloon/tools/preflight.sh
ssh tarun@balloon.local journalctl -fu balloon-telemetry
```

## Conventions (please keep)

- Python 3 stdlib + apt packages only (flask, smbus2, numpy, opencv, requests, gpiozero). No pip on the Pi, no venv,
  no build steps, no npm. Dashboard is plain HTML/CSS/JS with uPlot vendored in `static/vendor/`. Must work offline.
- `sensors.COLUMNS` is the CSV contract. Add columns at the end; never rename or remove. Missing values are empty.
- Drivers never raise out of `read()` for transient errors in a way that kills the loop: the sampler catches per-sensor
  exceptions and backs off. Detection failures go to `info["errors"]`, visible on the dashboard.
- Charts: one y-axis per chart, series colors by slot (`--s1 --s2 --s3`), legend only for multi-series. Only render
  what has data (`hasData`). Phone-first layout; keep redraws cheap (5 Hz SSE, 15 charts max).
- Nothing may depend on the network being up; services use `After=local-fs.target`, never `network-online`.
- Logging must never stop because of disk: video/stills pause under `BALLOON_MIN_FREE_GB`; CSV keeps going.
- Keep CPU modest: camera is pass-through MJPEG (no re-encode), mapper is niced with a CPU quota.
- Commit and push small steps to `main` (private repo `mr-mph/calhacks`). Test in sim mode before pushing.

## State and open items (update this section as you go)

- 2026-10-23: all software written and tested in simulation and against a synthetic camera; NOT yet run on the
  real Pi. First real-hardware run should: check `i2cdetect -y 1`, run `tools/test_sensor.py`, confirm ustreamer
  installed from apt, confirm ffmpeg records from the ustreamer stream, confirm the Grove ADC address (0x04 vs 0x08).
- 2026-10-24: added elevation_msl_m (QNH-based) + alt_since_launch_m columns, /api/qnh, timelapse.sh, wifi-mode.sh (Pi as AP).
  Hardware access still not achieved: venue Wi-Fi isolates clients, Mac USB gadget / direct Ethernet links never
  answered unicast (suspect the Mac's "Untitled Bridge" virtual interface on the LAN adapter). Hotspot path untested
  because the hotspot was off while the Pi booted. Next person: get a monitor on the Pi or keep the hotspot on.
- Ideas not started: metre scale bar on the mosaic (footprint = 2*h*tan(FOV/2)), tilt-rectified stills,
  Claude-vision captions from snapshots (laptop side), ESP32 tether-length encoder, servo pan (code exists, off).

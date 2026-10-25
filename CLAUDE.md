# Contributor guide (humans and AI agents)

Read this before changing anything. It covers what the system is, how it is wired together, how to test
without hardware, and the conventions that keep it working on the Pi during the hackathon.

## What this is

A tethered helium-balloon payload for CalHacks (Oct 2026). A Raspberry Pi 4 with a Seeed Grove Base Hat and a
Logitech USB webcam logs sensors + video to its SD card and serves a live dashboard over Wi-Fi (phone hotspot) or
over the USB-C cable. Weight budget is ~400 g total, power is a USB-C power bank. Team of 4, time-boxed.

Mission (decided Saturday Oct 24): tethered observation a few hundred feet up, held over one place for hours. One
camera view serves beachgoers (rip-current and swimmer alerts written by Claude), drivers (live parking map with surge
pricing) and markets (prediction markets and an analyst agent on car and foot-traffic counts). Docs:
- `docs/status.md`: current status, what's live, blockers and owners (start here)
- `CONTEXT.md`: mission, prize plan, order of work, full software walkthrough
- `docs/pitch.md`: why a balloon beats drones and satellites (with numbers and sources), demo storyline
- `docs/tracks.md`: every Cal Hacks track, rules, deadlines, free credits, venue hardware
- `docs/launch-plan.md`: helium, lift and tether

Hardware we actually have (confirmed by the team):
- Grove High Precision Barometer: Infineon **DPS310/DPS368** at I2C 0x77 (confirmed 2026-10-24; NOT a BMP280)
- Grove 3-axis accelerometer: **MMA7660** (±1.5 g) at I2C 0x4c (confirmed 2026-10-24)
- Grove Air Quality Sensor v1.3 (analog, port A4, read through the Base Hat ADC at I2C 0x04)
- Logitech USB webcam, 16 GB microSD
- Grove 16x2 LCD (I2C 0x3e text, 0x62 or 0x30 RGB backlight): hot-pluggable, `balloon/lcd.py` shows altitude/temp/AQ
- Possibly an MPU-6050 (I2C 0x68, accel + gyro) if someone attaches it
We do NOT have light, UV, humidity, or SGP30 sensors. Drivers for them exist but must stay off by default.

Pi: hostname `balloon`, user `tarun` (password login, shared by the team; never commit it), Raspberry Pi OS Lite 64-bit
(Trixie, NetworkManager, /boot/firmware). **The Pi is its own Wi-Fi network "BalloonNet"** (password `balloon123`,
Pi = 10.42.0.1). Join it and everything is there: dashboard http://10.42.0.1:8080, `ssh tarun@10.42.0.1`. Venue Wi-Fi
and venue wired both isolate clients, so BalloonNet is the only link that works at Cal Hacks. For internet on the Pi
(apt) plug its Ethernet into a venue wall jack (DHCP profile `venue-eth`); BalloonNet clients then get internet through
the Pi too. Provisioning a fresh card is one command: `tools/mac/sd-provision.sh` (see "Deploy / operate").

**Cloud is optional.** The whole demo runs with no internet: Pi dashboard + a laptop running the station. Convex (live
map), Spacetime (markets) and Jira only switch on when their credential files exist on the station laptop.

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

## Run the whole thing locally (no cloud needed)

```bash
# 1. laptop joins Wi-Fi "BalloonNet" (balloon123). Dashboard: http://10.42.0.1:8080 (video, sensors, charts, replay)
# 2. detector on the laptop, boxes drawn on the Pi dashboard for every phone on BalloonNet:
cd ground && python3 -m venv .venv && .venv/bin/pip install -r requirements-station.txt   # once
ground/start.sh                                  # detector + narrator together, auto-restart, Ctrl-C stops (the one command)
ground/live.sh / ground/narrate.sh               # the two halves separately; CLASSES=carperson for cars/people only
# 3. before launch, on the dashboard with the payload hanging still: Level, Zero alt, then Mark "launch" as it lifts
```
Trained weights (`ground/runs/visdrone/weights/best.pt`, `ground/runs/ripaid/weights/best.pt`) are gitignored and live
on the training Mac; without them the station uses the stock `yolo11n.pt` (COCO).

## Deploy / operate

```bash
# fresh card (Pi OS Lite 64-bit from the Imager, no customisation needed), card in the Mac's reader:
./tools/mac/sd-provision.sh "<wifi ssid for internet>" "<wifi password>" "<pi password>" [BalloonNet password]
#   first boot (unattended, ~8 min): user, SSH, I2C, cable address 169.254.2.2, copies pi/ to /opt/balloon, apt, services,
#   then switches Wi-Fi to the BalloonNet access point. Log: balloon-firstboot.log on the card.
# code changes later (open one password ssh session with ControlMaster, then rsync through it):
ssh -o ControlMaster=yes -o ControlPersist=8h -o ControlPath=~/.ssh/cm-balloon tarun@10.42.0.1      # separate terminal
rsync -az --delete --exclude __pycache__ -e "ssh -o ControlPath=~/.ssh/cm-balloon" pi/ tarun@10.42.0.1:/opt/balloon/
ssh -o ControlPath=~/.ssh/cm-balloon tarun@10.42.0.1 'sudo systemctl restart balloon-telemetry'
ssh -o ControlPath=~/.ssh/cm-balloon tarun@10.42.0.1 /opt/balloon/tools/preflight.sh                 # GO / NO-GO
ssh -o ControlPath=~/.ssh/cm-balloon tarun@10.42.0.1 'sudo tools/wifi-mode.sh client'                # back to normal Wi-Fi
```
Other SD-card helpers in `tools/mac/` (enable-usb-gadget, sd-add-wifi, sd-no-keyboard, sd-static-links) are from the
debugging trail and mostly superseded by sd-provision.sh. `deploy.sh`/`flash.sh` assume `balloon.local` resolves, which
it does on BalloonNet.

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

- **2026-10-24 23:00: the Pi flies as built.** Pi 4 provisioned with `tools/mac/sd-provision.sh`, running as the
  BalloonNet access point; all four services up; preflight GO. Hardware confirmed: DPS368 barometer (driver
  `drivers/dps310.py`), MMA7660 accelerometer (sideways: press Level), Air Quality v1.3 on A4 via the Base Hat ADC,
  Logitech webcam at 15 fps (ustreamer HW encode). QNH calibrated so the Palace of Fine Arts reads 5 m MSL
  (`POST /api/elevation`). Grove LCD RGB lights but shows no text at the hat's 3.3 V (5 V part); driver left in.
- Dashboard features: live video with detector boxes + tilt bubble, tiles, 15 charts incl. YOLO counts, vertical
  profiles, orientation, markers, replay of any session, QR code, Level / Zero alt / elevation / QNH endpoints.
- Ground station runs on Seth's Mac (`ground/.venv`) against the live Pi; detections go to the Pi (`/api/detections`)
  and into the telemetry rows (`det_cars`, `det_people`). Cloud sinks off (no credentials on this Mac).
- 2026-10-24 23:35: narrator live. `ground/narrator.py` (laptop) -> Claude Sonnet 5.5 captions + ElevenLabs MP3 ->
  Pi `/api/captions`; spoken Q&A via `/api/ask` relay; dashboard Narrator card (Voice toggle, mic via Web Speech API).
  Secrets only in `~/.config/balloon/secrets.env` on the laptop (never in git).
- Open: the real flight and a recorded session (`./fetch.sh` afterwards; `analysis/plot_session.py`); copy trained
  weights to the station laptop; the live map's source changes on `main` (station command, Markets tab hidden) need a
  manual `npx vercel deploy --prod` from `web/` by the Vercel project owner (Vercel is not linked to GitHub); Devpost.
- Earlier history (networking saga, cloud work, models) is in git log and `docs/status.md`.
- Ideas not started: metre scale bar on the mosaic (footprint = 2*h*tan(FOV/2)), tilt-rectified stills,
  Claude-vision captions from snapshots (laptop side), ESP32 tether-length encoder, servo pan (code exists, off).

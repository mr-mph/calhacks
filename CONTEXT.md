# CalHacks 13.0 Balloon Payload: Full Project Context

> Everything a teammate, judge, or future contributor needs to understand where this project is, what decisions have been made, what's still open, and how the software works. This is the single source of truth.

---

## 1. The Mission

We're building a **1U CubeSat-style payload** at **Cal Hacks 13.0** (October 23-25, 2026, San Francisco). Team of 4, no ham licence.

**Primary mission:** Fly the payload on a helium balloon (target 30,000-50,000 ft), logging atmospheric data and video the whole way up, with a parachute recovery. The software records everything to the SD card regardless of connectivity, and serves a live dashboard over Wi-Fi when in range.

**Fallback mission:** If a free flight isn't feasible (weather, helium, landing prediction), run a tethered flight to modest altitude plus drop tests and freezer tests. Still a solid demo -- the sensor data, dashboard, and video work identically.

**The hackathon started Friday night (Oct 23). Real work begins Saturday morning.**

---

## 2. Hardware Plan

All hardware comes from the **MLH hardware lab** unless noted. Grab the Pi early -- only ~9 exist.

| Component | Source | Role |
|---|---|---|
| Raspberry Pi 4B | MLH lab (limited supply) | Video recording, Wi-Fi dashboard, data logging |
| Logitech USB webcam | MLH lab | Downward-facing video + stills |
| Arduino | MLH lab | Sensor reading, buzzer, cutdown trigger |
| Grove Base Hat + sensors | MLH lab | I2C/analog sensor hub on the Pi |
| Grove barometer (BMP280 family) | MLH lab | **Most important sensor** -- altitude profile |
| Grove accelerometer | MLH lab | Tilt/sway (may be low-range ~1.5g; see note below) |
| Grove Air Quality Sensor v1.3 | MLH lab | Analog air quality on port A4 |
| Phone (Phyphox) | Personal | Backup motion, GPS, video |
| Lithium AA batteries | Buy/bring | Arduino power (no LiPo -- fire risk) |
| USB-C power bank | Personal | Pi power, insulated |
| PETG 1U frame | Build at hackathon | Structure |
| Styrofoam box | Buy | Insulation (vent hole + camera window) |

**Weight target: under 1 kg.** If the Pi + webcam + power bank push past ~0.8 kg, drop the Pi and use the phone as the camera. Every 100 g cut saves ~5 cu ft of helium.

**Accelerometer note:** The Grove accel from MLH may be an MMA7660 (~1.5g range), which will clip during any impact or fast motion. Bring an MPU6050 or ADXL375 if cheap. The software auto-detects any of ADXL345, LIS3DH, MMA7660, or MPU6050 -- just plug it into an I2C port.

---

## 3. Altitude, Regulations & Tracking

### Altitude & Cutdown
- Weather balloons burst near 98,000 ft. Reaching 30-50k ft requires an active cutdown.
- **Cutdown design:** Arduino reads the barometer. At ~240 hPa (~35,000 ft), it heats nichrome wire to melt the tether line. Timer backup in case the barometer fails.
- **Test first on a tether before any free flight.**
- This is a design concept, not a tested recipe.

### FAA (Part 101)
- The "1.8 kg exemption" is NOT a blanket pass. Part 101 has multiple triggers:
  - Over 4 lb at a certain weight/density
  - Over 6 lb
  - Over 12 lb total train
  - Line needing >50 lb to separate
- **Stay under 1 kg, use a weak link, avoid 550 paracord.**
- 30-50k ft is **airliner cruising altitude** -- do not create a hazard.
- Treat this as general information, not legal advice.

### Tracking
- Phone GPS may hold below 59,000 ft but isn't proven above ~10k ft
- Phone live-location apps only report near the ground
- **Plan:** Two phones with SIMs, both logging to SD card
- LoRa/Meshtastic radios would be ideal but Amazon deliveries land after Sunday -- ask MLH or mentors if they have any to borrow
- Phone provides the only real-time tracking for recovery

### Launch Site
Pick by the **landing predictor**, not by distance from the venue.

| Site | Notes |
|---|---|
| Berkeley Marina | Closest to venue |
| Heather Farm Park, Walnut Creek | East of hills |
| John Henry Johnson Park, Pittsburg | Furthest east, best for Central Valley landing |

**Goal:** landing in open Central Valley farmland, east of the hills, away from the Bay.
**SF-HAB** is the local group to ask for advice. Check park permission and airport distances.

---

## 4. Parachute, Balloons & Tether

### Parachute (NOT SOLVED)
- Hobby Lobby's 12" and 18" rocket chutes are too small (~8-10 m/s descent)
- Need a **36-48" ripstop chute** at ~4-5 m/s
- At 0.8 kg: 48" chute = ~3.6 m/s, 36" chute = ~4.8 m/s
- **Buy ripstop at Discount Fabrics** (1805 Eastshore Hwy, Berkeley, opens 10 AM, 510-548-2981)
- Sew a 48" octagon with lines running corner to corner
- **Drop-test a dummy payload before flying**

### Helium
- ~75-80 cu ft lifts a 1 kg payload (payload + chute + line)
- A 300 g payload needs only ~20 cu ft
- Every 100 g you cut saves ~5 cu ft

### Balloons
- 1 kg payload needs ~150 eleven-inch party balloons OR 7-8 balloons at 36"
- Bigger balloons save tying effort, not helium
- Party balloons aren't rated for high altitude -- no burst-height data
- **Test on a tether before any free flight**

### Where to Buy
- **Berkeley Balloons and Events** (1643 San Pablo Ave, 510-932-5537, text works) -- opens 9 AM Saturday. Ask about tank rental, regulator, 36" balloons, and filling.
- **Airgas Berkeley** -- closed on weekends.
- **REI Berkeley** (1338 San Pablo Ave, 510-527-4140, opens 10 AM) -- tether line. Call first. 20-30 lb braided line for free flight; 30-50 lb for tethered test.

### Tether
- Free flight: 20-30 lb braided line with a weak link
- Tethered test: 30-50 lb line is fine
- Do NOT use 550 paracord (too strong, FAA trigger)

---

## 5. Open Decisions & Saturday Plan

### Tonight (Friday)
1. Text Berkeley Balloons: can they fill balloons, rent a tank + regulator, price, do they stock 36"?
2. Ask MLH + mentor channel for LoRa nodes and the exact Grove accelerometer/barometer stock
3. Weigh the full payload -- this decides chute size, helium amount, and whether the Pi stays
4. **Lock in: free flight vs. tethered flight + drop tests** (decide by Saturday morning)

### Saturday Schedule
1. **9 AM** -- Berkeley Balloons and Events
2. **10 AM** -- REI Berkeley (tether line)
3. **10 AM** -- Discount Fabrics (ripstop for parachute)
4. Build parachute, drop-test dummy payload
5. Sensor dry run on real Pi hardware
6. **Fly free only if:** predictor shows clean landing AND helium is secured
7. **Otherwise:** tethered flight + drop tests (still a solid demo)

---

## 6. Software Architecture

Everything runs on the Pi itself. No cloud backend, no external database, no build step, no npm. Five independent systemd services:

```
                          +--> balloon-camera      (ustreamer MJPEG :8081)
                          |
    balloon-telemetry ----+--> balloon-recorder    (ffmpeg -> .mkv segments + stills)
    (Flask :8080)         |
    (sampler thread)      +--> balloon-mapper      (ORB + RANSAC -> mosaic.jpg)
    (CSV logging)         |
    (SSE push)            +--> balloon-wifi-watchdog.timer
                               (kicks NetworkManager if wlan0 drops)
```

### Service Breakdown

**balloon-telemetry** (the core) -- `pi/balloon/server.py` + `pi/balloon/sensors.py`
- Flask server on :8080, background Telemetry thread
- Scans I2C bus and auto-detects every known sensor by address
- Samples all sensors at 5 Hz, derives altitude (ISA barometric formula, EMA-smoothed, zeroed to ground), vertical speed, pitch/roll/tilt
- Writes every sample to `telemetry.csv` (flushed per row, never stops)
- 30-minute in-memory ring buffer, SSE fan-out to all browsers
- Serves dashboard, REST API, data downloads, QR codes, camera proxy, session replay

**balloon-camera** -- `pi/balloon/camera.sh`
- `ustreamer` for zero-copy MJPEG streaming from USB webcam on :8081
- Falls back to OpenCV Python server if ustreamer unavailable

**balloon-recorder** -- `pi/balloon/recorder.py`
- `ffmpeg -c copy` segments the MJPEG stream into 60s `.mkv` files (no re-encode, low CPU)
- Grabs a still every 2 seconds with telemetry metadata
- Pauses when SD card free space drops below 1 GB; CSV logging never stops

**balloon-mapper** -- `pi/balloon/mapper.py`
- ORB feature detection + RANSAC affine estimation aligns each still to the previous
- Builds an incremental mosaic; batch mode uses OpenCV's SCANS stitcher

**balloon-wifi-watchdog** -- `pi/wifi-watchdog.sh`
- Timer-triggered; restarts NetworkManager if wlan0 has no IP for two checks

### Data Flow

```
Sensors  ──5Hz──>  Telemetry Thread  ──>  telemetry.csv (permanent)
                        │
                        ├──> SSE push ──> Browser (charts, tiles, profiles)
                        └──> /api/* (REST)

Webcam  ──MJPEG──>  ustreamer :8081  ──>  Browser (live view)
                         │
                         ├──> ffmpeg ──> video/*.mkv (60s segments)
                         └──> snapshot/2s ──> stills/*.jpg ──> mapper ──> mosaic.jpg
```

---

## 7. Dashboard

Single-page app in plain HTML/CSS/JS (`pi/balloon/static/`). No framework, no build, works offline.

- **Real-time tiles** -- altitude (hero), climb rate, pressure, temp, tilt, light, UV, air quality, eCO2, humidity. Only appear when their sensor has data.
- **15 time-series charts** (uPlot, vendored) -- auto-appear per sensor. Markers drawn on altitude chart.
- **Vertical profile plots** -- value vs altitude (binned mean + raw scatter). Appear after 3 m of altitude change.
- **Live MJPEG camera** + **aerial mosaic map** ("Map" tab)
- **Markers** -- timestamped notes; name one "launch" to show time aloft and peak altitude
- **Session replay** at 1-50x with still playback (`?replay=<session>`)
- **QR code** for judges' phones (pure-Python SVG, no dependency)
- **Dark/light theme**, status chips (session, samples, disk, CPU, RSSI with warnings)
- Phone-first layout, designed for 5 Hz SSE on mobile

---

## 8. Sensor Drivers

All in `pi/balloon/drivers/`, strict contract: `KIND`, `FIELDS`, `name`, `read() -> dict`.

| Driver | Chip | I2C | Fields |
|---|---|---|---|
| BMP280 | BMP280/BME280 | 0x76/0x77 | pressure_hpa, temp_c, humidity_pct (BME) |
| BMP180 | BMP180 | 0x77 | pressure_hpa, temp_c |
| ADXL345 | ADXL345 | 0x53 | ax_g, ay_g, az_g |
| LIS3DH | LIS3DHTR | 0x18/0x19 | ax_g, ay_g, az_g |
| MMA7660 | MMA7660 | 0x4C | ax_g, ay_g, az_g |
| MPU6050 | MPU6050/6500/9250 | 0x68/0x69 | ax_g, ay_g, az_g, gx_dps, gy_dps, gz_dps |
| SGP30 | SGP30 | 0x58 | eco2_ppm, tvoc_ppb |
| GroveADC + AnalogSensors | STM32 ADC | 0x04/0x08 | light_raw/pct, uv_mv/index, aq_raw/level |
| SystemStats | Linux sysfs | -- | cpu_temp_c, wifi_rssi_dbm, disk_free_gb, load_1m |

Auto-detection scans 0x03-0x77, tries factories in priority order per address. First correct chip ID wins. Fault tolerance: per-sensor exception backoff, retry every ~5 s after 5 consecutive failures.

---

## 9. CSV Schema

Fixed `sensors.COLUMNS` -- same columns every session, missing sensors produce empty cells:

```
t_unix, t_iso, t_mono,
pressure_hpa, temp_c, humidity_pct, altitude_m, altitude_raw_m, vspeed_mps,
ax_g, ay_g, az_g, accel_mag_g, pitch_deg, roll_deg, tilt_deg,
gx_dps, gy_dps, gz_dps,
light_raw, light_pct, uv_mv, uv_index, aq_raw, aq_level,
eco2_ppm, tvoc_ppb,
cpu_temp_c, wifi_rssi_dbm, disk_free_gb, load_1m
```

**Derived fields:** altitude_m (ISA formula, EMA alpha=0.25, zeroed to first 25 samples), vspeed_mps, accel_mag_g, pitch_deg, roll_deg, tilt_deg.

---

## 10. Session Data Layout

```
/data/balloon/sessions/20261024-091500/
  telemetry.csv         5 Hz, flushed per row
  markers.csv           t_unix, t_iso, altitude_m, note
  sensors.json          detection results
  video/*.mkv           60-second MJPEG segments
  stills/*.jpg          one every 2 seconds
  stills/index.csv      file, t_unix, altitude_m, pitch_deg, roll_deg, tilt_deg
  mosaic.jpg            incremental aerial mosaic
```

---

## 11. Configuration

All via env vars, defined in `pi/balloon/config.py`, set in `/etc/default/balloon`:

| Variable | Default | Description |
|---|---|---|
| BALLOON_SIM | 0 | Fake sensors for laptop dev |
| BALLOON_DATA | /data/balloon | Data root |
| BALLOON_SAMPLE_HZ | 5.0 | Sampling frequency |
| BALLOON_ANALOG | aq:4 | Analog sensor channels |
| BALLOON_CAMERA_RES | 640x480 | Camera resolution |
| BALLOON_CAMERA_FPS | 15 | Camera framerate |
| BALLOON_MIN_FREE_GB | 1.0 | Stop video below this |
| BALLOON_SERVO | 0 | Enable servo pan |

---

## 12. Deployment & Operations

```bash
# First time (on Mac, Pi on same network)
./deploy.sh tarun@balloon.local --setup              # copies code, installs packages, enables services
./deploy.sh tarun@balloon.local --setup --usb-gadget  # also enables USB-C Ethernet

# Later deploys
./deploy.sh tarun@balloon.local                       # rsync + restart

# Pre-flight
ssh tarun@balloon.local /opt/balloon/tools/preflight.sh

# Data retrieval
./fetch.sh                                            # all sessions to Mac
python3 analysis/plot_session.py data/sessions/<s>    # flight summary PNG
```

### Networking
- **USB-C cable (dev):** `tools/mac/enable-usb-gadget.sh` on the SD card, then `ssh tarun@balloon.local` over the cable
- **Phone hotspot (flight):** venue Wi-Fi blocks peer traffic, use a phone hotspot
- **Nothing depends on network.** All services start before networking. CSV logging and video work fully offline.

---

## 13. Simulation Mode

```bash
cd pi && BALLOON_SIM=1 BALLOON_DATA=/tmp/balloon python3 -m balloon.server
# http://localhost:8080 -- simulated balloon rising to 60 m with sway, AQ drift, system stats
# Add BALLOON_SIM_ALL=1 for humidity/light/UV/SGP30

python3 tests/test_drivers_fake_i2c.py    # driver math tests, no hardware
```

---

## 14. Key Design Decisions

1. **No build step, no npm, no pip on the Pi.** Python stdlib + apt packages only. Dashboard is vanilla JS. Single rsync deploys.
2. **Fixed CSV schema.** Same columns regardless of sensors. Analysis scripts never break.
3. **Independent, crash-resistant services.** Each is a separate systemd unit with Restart=always. Camera can crash without affecting telemetry.
4. **CSV logging never stops.** Video and stills pause when disk is low, but CSV keeps going.
5. **Auto-detection over configuration.** Sensors found by I2C scan, not config files.
6. **Pass-through MJPEG.** No re-encoding keeps CPU low on a power-constrained Pi in a balloon.
7. **Phone-first dashboard.** Primary viewer is a judge's phone.
8. **Relative altitude.** Zeroed to ground pressure at startup. Press "Zero alt" before launch.
9. **Similarity transforms for mosaic.** ORB + RANSAC similarity (not full homography) -- more stable for nadir camera.
10. **No LiPo batteries.** Fire risk at altitude. Lithium AAs for Arduino, USB-C power bank for Pi.

---

## 15. Software Progress

### Done (tested in simulation)
- Full sensor driver stack with I2C auto-detection (7 chip families + analog + system stats)
- 5 Hz sampling with altitude/tilt derivation, CSV logging, SSE push
- Flask dashboard with 15 chart types, tiles, vertical profiles, replay, QR
- MJPEG camera integration + OpenCV fallback
- Video recording (segmented .mkv) + still capture + telemetry indexing
- Real-time mosaic stitcher (incremental + batch modes)
- Systemd services, setup script, deploy/fetch/preflight scripts
- Simulation mode, fake-I2C driver tests
- Post-flight analysis/plotting
- Wi-Fi watchdog, USB-C gadget networking

### Not Yet Done
- **First real-hardware run** -- needs: `i2cdetect`, `test_sensor.py`, confirm ustreamer/ffmpeg, verify Grove ADC address (0x04 vs 0x08)
- **Arduino cutdown integration** -- code concept exists but nothing written
- **Parachute** -- not yet sourced or built
- **Physical payload assembly** -- PETG frame, styrofoam box, camera window
- **Flight test** -- tethered test before any free flight
- **Tracking solution** -- phone GPS + SIM cards, LoRa if available

### Ideas (Not Started)
- Metre scale bar on mosaic
- Tilt-rectified stills
- Claude-vision captions from snapshots
- ESP32 tether-length encoder
- Servo camera pan (code exists, disabled)

---

## 16. Git History

```
94640f9  Pi telemetry: config, Grove sensor drivers, sampler with CSV logging, simulator
48bff6b  Dashboard: Flask server with SSE, uPlot charts, camera/map views, markers
25c3244  Camera stream, recorder, mosaic mapper, systemd units, setup/deploy scripts
3811cbf  README, on-page JS error banner
3054533  Preflight checklist, fetch + post-flight plot, fake-I2C tests, flight summary
063dca1  Replay mode for past sessions, vertical profiles, QR code overlay
b28ce8e  Scripted headless SD card flash
02fd133  Match actual kit: analog default = AQ on A4 only; simulator matches our hardware
405bbf2  Fake-I2C test: set analog channels explicitly
bff8e02  CLAUDE.md contributor guide
86b4eaa  USB-C gadget networking (Mac-side SD script, NM profile, DHCP + link-local)
3435c32  Fix: wifi watchdog treated disconnected as connected
fb59dab  Docs: helium and lift launch plan
2f8e3da  Authorize ssh key in flash.sh
51cd254  enable-usb-gadget: detect peripheral overlay specifically
```

---

## 17. File Tree

```
calhacks/
  CLAUDE.md                 contributor guide
  CONTEXT.md                this file
  README.md                 quickstart + operating guide
  deploy.sh                 rsync to Pi + restart services
  fetch.sh                  pull sessions to Mac
  analysis/
    plot_session.py         post-flight summary figure
  tools/mac/
    enable-usb-gadget.sh    prepare SD card for USB-C Ethernet
  pi/                       deployed to /opt/balloon on Pi
    setup.sh                provisioning (apt, I2C, systemd)
    default.env             template for /etc/default/balloon
    wifi-watchdog.sh        reconnect Wi-Fi
    balloon/
      config.py             env-var configuration with defaults
      server.py             Flask dashboard + API + SSE
      sensors.py            I2C scan, sampling loop, CSV, altitude/tilt
      sim.py                fake sensors for laptop dev
      recorder.py           ffmpeg video + still capture
      mapper.py             ORB+RANSAC mosaic stitcher
      camera_fallback.py    OpenCV camera (ustreamer fallback)
      qr.py                 pure-Python QR -> SVG
      servo.py              SG90 servo via gpiozero
      drivers/
        bmp280.py           BMP280/BME280 (Bosch datasheet formulas)
        bmp180.py           BMP180 (legacy barometer)
        accel.py            ADXL345, LIS3DH, MMA7660, MPU6050
        grove_adc.py        Base Hat ADC + analog wrappers
        sgp30.py            SGP30 VOC/eCO2
        system.py           Pi housekeeping stats
      static/
        index.html          dashboard (single page)
        app.js              charts, SSE, profiles, replay (520 lines)
        style.css           mobile-first, dark/light themes
        vendor/             uPlot (vendored, no CDN)
    systemd/                5 service/timer units
    tests/
      test_drivers_fake_i2c.py
    tools/
      preflight.sh          GO/NO-GO checklist
      i2c_check.py          name each I2C address
      test_sensor.py        test individual sensors
```

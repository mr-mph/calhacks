"""Sensor detection and the telemetry sampling loop.

- Scans the I2C bus and instantiates a driver for every known address.
- Samples all sensors at SAMPLE_HZ, derives altitude (zeroed at startup) and tilt.
- Appends every sample to <session>/telemetry.csv (flushed each row).
- Keeps a ring buffer for the dashboard and fans out samples to SSE subscribers.
"""
import csv
import collections
import json
import logging
import math
import os
import queue
import re
import statistics
import threading
import time
from datetime import datetime

from . import config

log = logging.getLogger("sensors")

# Fixed CSV schema so analysis is trivial regardless of which sensors were present.
COLUMNS = [
    "t_unix", "t_iso", "t_mono",
    "pressure_hpa", "temp_c", "humidity_pct", "altitude_m", "altitude_raw_m", "vspeed_mps",
    "ax_g", "ay_g", "az_g", "accel_mag_g", "pitch_deg", "roll_deg", "tilt_deg",
    "gx_dps", "gy_dps", "gz_dps",
    "light_raw", "light_pct", "uv_mv", "uv_index", "aq_raw", "aq_level",
    "eco2_ppm", "tvoc_ppb",
    "cpu_temp_c", "wifi_rssi_dbm", "disk_free_gb", "load_1m",
    "elevation_msl_m", "alt_since_launch_m",
]

# I2C address -> list of driver factories to try (first that succeeds wins).
def _known_addresses():
    from .drivers import bmp280, bmp180, dps310, accel, sgp30
    return {
        0x76: [bmp280.BMP280, dps310.DPS310],
        0x77: [bmp280.BMP280, bmp180.BMP180, dps310.DPS310],
        0x53: [accel.ADXL345],
        0x18: [accel.LIS3DH],
        0x19: [accel.LIS3DH],
        0x4C: [accel.MMA7660],
        0x68: [accel.MPU6050],
        0x69: [accel.MPU6050],
        0x58: [sgp30.SGP30],
    }


def scan_i2c(bus):
    """Return the list of responding 7-bit addresses (like i2cdetect)."""
    found = []
    for addr in range(0x03, 0x78):
        try:
            bus.read_byte(addr)
            found.append(addr)
        except OSError:
            # Some devices NAK a plain read but answer a quick write; try that too.
            try:
                bus.write_quick(addr)
                found.append(addr)
            except OSError:
                pass
    return found


def detect_sensors():
    """Instantiate every sensor we can find. Returns (sensors, info dict)."""
    info = {"sim": config.SIM, "i2c_addresses": [], "sensors": [], "errors": []}
    if config.SIM:
        from .sim import sim_sensors
        sensors = sim_sensors()
        info["sensors"] = [{"name": s.name, "kind": s.KIND, "fields": s.FIELDS} for s in sensors]
        return sensors, info

    sensors = []
    try:
        from smbus2 import SMBus
        bus = SMBus(config.I2C_BUS)
    except Exception as e:  # no I2C at all: still run with system stats so logging/dashboard work
        info["errors"].append("I2C bus %s unavailable: %s" % (config.I2C_BUS, e))
        bus = None

    if bus is not None:
        addrs = scan_i2c(bus)
        info["i2c_addresses"] = ["0x%02x" % a for a in addrs]
        log.info("I2C devices: %s", info["i2c_addresses"])
        for addr in addrs:
            for factory in _known_addresses().get(addr, []):
                try:
                    s = factory(bus, addr)
                    sensors.append(s)
                    log.info("detected %s at 0x%02x", s.name, addr)
                    break
                except Exception as e:
                    info["errors"].append("0x%02x %s: %s" % (addr, factory.__name__, e))
        # Grove Base Hat ADC (0x04 default, 0x08 on some firmware) + analog sensors
        from .drivers.grove_adc import GroveADC, AnalogSensors
        for adc_addr in (0x04, 0x08):
            if adc_addr in addrs and config.ANALOG:
                try:
                    adc = GroveADC(bus, adc_addr)
                    sensors.append(AnalogSensors(adc, config.ANALOG))
                    log.info("Grove ADC v%s at 0x%02x, analog channels %s", adc.version, adc_addr, config.ANALOG)
                    break
                except Exception as e:
                    info["errors"].append("ADC 0x%02x: %s" % (adc_addr, e))

    from .drivers.system import SystemStats
    sensors.append(SystemStats(config.DATA_ROOT))
    info["sensors"] = [{"name": s.name, "kind": s.KIND, "fields": s.FIELDS} for s in sensors]
    for e in info["errors"]:
        log.warning(e)
    return sensors, info


def pressure_altitude(p_hpa, p0_hpa):
    """ISA barometric formula, metres above the reference pressure."""
    return 44330.0 * (1.0 - (p_hpa / p0_hpa) ** (1.0 / 5.255))


class Telemetry(threading.Thread):
    """Background sampler. Thread-safe accessors: latest(), history(), subscribe()."""

    def __init__(self):
        super().__init__(daemon=True, name="telemetry")
        self.sensors, self.info = detect_sensors()
        self.lock = threading.Lock()
        self._latest = {}
        maxlen = int(config.HISTORY_SECONDS * config.SAMPLE_HZ)
        self._history = collections.deque(maxlen=maxlen)
        self._subscribers = []
        self._zero_samples = []
        self.p0 = None
        self.alt_ema = None
        self._prev_alt = None
        self._prev_t = None
        self.rezero_requested = False
        self.qnh = config.QNH_HPA          # sea-level pressure for elevation_msl_m
        self.launch_alt = None             # altitude_m when a "launch" marker was recorded
        self.level_ref = self._load_level()  # gravity vector when the payload hangs "upright" (POST /api/level)
        self.failures = collections.Counter()
        self.start_time = time.time()
        self.samples = 0
        self.markers = []
        self._open_session()

    # ---------- session / files ----------
    def _open_session(self):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.session = stamp
        self.session_dir = os.path.join(config.SESSIONS_DIR, stamp)
        os.makedirs(self.session_dir, exist_ok=True)
        for sub in ("video", "stills"):
            os.makedirs(os.path.join(self.session_dir, sub), exist_ok=True)
        self.csv_path = os.path.join(self.session_dir, "telemetry.csv")
        self._csv_file = open(self.csv_path, "a", newline="", buffering=1)
        self._csv = csv.DictWriter(self._csv_file, fieldnames=COLUMNS, extrasaction="ignore")
        if self._csv_file.tell() == 0:
            self._csv.writeheader()
        self.markers_path = os.path.join(self.session_dir, "markers.csv")
        with open(self.markers_path, "a") as f:
            if f.tell() == 0:
                f.write("t_unix,t_iso,altitude_m,note\n")
        with open(config.CURRENT_SESSION_FILE, "w") as f:
            f.write(self.session_dir)
        with open(os.path.join(self.session_dir, "sensors.json"), "w") as f:
            json.dump(self.info, f, indent=2)
        log.info("session %s -> %s", self.session, self.session_dir)

    def _level_path(self):
        return os.path.join(config.DATA_ROOT, "level.json")

    def _load_level(self):
        try:
            with open(self._level_path()) as f:
                v = json.load(f)
            return [float(v["ax"]), float(v["ay"]), float(v["az"])]
        except Exception:
            return None

    def set_ground_elevation(self, elevation_m):
        """Calibrate the sea-level pressure so the current spot reads elevation_m above sea level."""
        p = self.latest().get("pressure_hpa")
        if not p:
            return None
        self.qnh = round(p / (1.0 - elevation_m / 44330.0) ** 5.255, 2)
        log.info("ground elevation set to %.1f m -> QNH %.2f hPa", elevation_m, self.qnh)
        return self.qnh

    def set_level(self):
        """Take the current accelerometer vector as the 'upright' reference for tilt_deg."""
        s = self.latest()
        if s.get("ax_g") is None:
            return None
        ref = [s["ax_g"], s["ay_g"], s["az_g"]]
        with self.lock:
            self.level_ref = ref
        try:
            with open(self._level_path(), "w") as f:
                json.dump({"ax": ref[0], "ay": ref[1], "az": ref[2], "t_unix": time.time()}, f)
        except OSError as e:
            log.warning("could not save level reference: %s", e)
        log.info("level reference set to %s", ref)
        return ref

    def add_marker(self, note):
        s = self.latest()
        row = {"t_unix": time.time(), "t_iso": datetime.now().isoformat(timespec="milliseconds"),
               "altitude_m": s.get("altitude_m"), "note": note}
        with open(self.markers_path, "a") as f:
            f.write("%s,%s,%s,%s\n" % (row["t_unix"], row["t_iso"], row["altitude_m"] if row["altitude_m"] is not None else "",
                                        note.replace(",", ";").replace("\n", " ")))
        with self.lock:
            self.markers.append(row)
            if re.search(r"launch|release|lift", note, re.I):
                self.launch_alt = s.get("altitude_m") or 0.0
                log.info("launch marked at %.2f m", self.launch_alt)
        self._broadcast({"type": "marker", "marker": row})
        return row

    # ---------- public accessors ----------
    def latest(self):
        with self.lock:
            return dict(self._latest)

    def history(self, seconds=None):
        with self.lock:
            rows = list(self._history)
        if seconds:
            cutoff = time.time() - seconds
            rows = [r for r in rows if r["t_unix"] >= cutoff]
        return rows

    def subscribe(self):
        q = queue.Queue(maxsize=200)
        with self.lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def request_rezero(self):
        self.rezero_requested = True

    def status(self):
        with self.lock:
            return {
                "session": self.session, "session_dir": self.session_dir, "csv": self.csv_path,
                "samples": self.samples, "uptime_s": round(time.time() - self.start_time, 1),
                "p0_hpa": self.p0, "zeroed": self.p0 is not None, "sensors": self.info,
                "qnh_hpa": self.qnh, "launch_alt_m": self.launch_alt, "leveled": self.level_ref is not None, "level_ref": self.level_ref,
                "failures": dict(self.failures), "sample_hz": config.SAMPLE_HZ, "markers": self.markers[-50:],
            }

    # ---------- sampling ----------
    def _broadcast(self, msg):
        with self.lock:
            subs = list(self._subscribers)
        for q in subs:
            try:
                q.put_nowait(msg)
            except queue.Full:
                try:
                    q.get_nowait()
                    q.put_nowait(msg)
                except Exception:
                    pass

    def _derive(self, row, t_mono):
        p = row.get("pressure_hpa")
        if p is not None and p > 300:
            if self.rezero_requested:
                self.p0, self.alt_ema, self._zero_samples = None, None, []
                self.rezero_requested = False
            if self.p0 is None:
                self._zero_samples.append(p)
                if len(self._zero_samples) >= config.ZERO_SAMPLES:
                    self.p0 = statistics.median(self._zero_samples)
                    log.info("ground pressure zeroed at %.2f hPa", self.p0)
                row["altitude_raw_m"] = 0.0
                row["altitude_m"] = 0.0
            else:
                raw = pressure_altitude(p, self.p0)
                a = config.ALT_SMOOTHING
                self.alt_ema = raw if self.alt_ema is None else (a * raw + (1 - a) * self.alt_ema)
                row["altitude_raw_m"] = round(raw, 2)
                row["altitude_m"] = round(self.alt_ema, 2)
                if self._prev_alt is not None and t_mono > self._prev_t:
                    v = (self.alt_ema - self._prev_alt) / (t_mono - self._prev_t)
                    row["vspeed_mps"] = round(v, 3)
                self._prev_alt, self._prev_t = self.alt_ema, t_mono
            row["elevation_msl_m"] = round(pressure_altitude(p, self.qnh), 1)
            if self.launch_alt is not None and row.get("altitude_m") is not None:
                row["alt_since_launch_m"] = round(row["altitude_m"] - self.launch_alt, 2)
        ax, ay, az = row.get("ax_g"), row.get("ay_g"), row.get("az_g")
        if ax is not None and ay is not None and az is not None:
            mag = math.sqrt(ax * ax + ay * ay + az * az)
            row["accel_mag_g"] = round(mag, 3)
            row["pitch_deg"] = round(math.degrees(math.atan2(ax, math.sqrt(ay * ay + az * az))), 2)
            row["roll_deg"] = round(math.degrees(math.atan2(ay, az)), 2)
            if self.level_ref is not None and mag > 1e-6:
                rx, ry, rz = self.level_ref
                rmag = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
                cosang = (ax * rx + ay * ry + az * rz) / (mag * rmag)
                row["tilt_deg"] = round(math.degrees(math.acos(max(-1.0, min(1.0, cosang)))), 2)
            else:
                row["tilt_deg"] = round(math.degrees(math.acos(max(-1.0, min(1.0, az / mag)))) if mag > 1e-6 else 0.0, 2)
            for k in ("ax_g", "ay_g", "az_g"):
                row[k] = round(row[k], 4)

    def run(self):
        period = 1.0 / config.SAMPLE_HZ
        next_t = time.monotonic()
        while True:
            t_mono = time.monotonic()
            now = time.time()
            row = {"t_unix": round(now, 3), "t_iso": datetime.fromtimestamp(now).isoformat(timespec="milliseconds"),
                   "t_mono": round(t_mono, 3)}
            for s in self.sensors:
                # back off a sensor that keeps failing (retry every ~5 s instead of every sample)
                if self.failures[s.name] >= 5 and int(t_mono * config.SAMPLE_HZ) % int(5 * config.SAMPLE_HZ):
                    continue
                try:
                    row.update(s.read())
                    if self.failures[s.name]:
                        log.info("%s recovered", s.name)
                    self.failures[s.name] = 0
                except Exception as e:
                    self.failures[s.name] += 1
                    if self.failures[s.name] in (1, 5, 50, 500):
                        log.warning("%s read failed (%d): %s", s.name, self.failures[s.name], e)
            try:
                self._derive(row, t_mono)
            except Exception as e:  # a bad reference (QNH, level) must never stop logging
                self.failures["derive"] += 1
                if self.failures["derive"] in (1, 5, 50, 500):
                    log.error("derive failed (%d): %s", self.failures["derive"], e)
            try:
                self._csv.writerow(row)
            except Exception as e:
                log.error("csv write failed: %s", e)
            with self.lock:
                self._latest = row
                self._history.append(row)
                self.samples += 1
            self._broadcast({"type": "sample", "sample": row})
            next_t += period
            delay = next_t - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_t = time.monotonic()

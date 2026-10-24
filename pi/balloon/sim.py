"""Fake sensors for developing the dashboard on a laptop (BALLOON_SIM=1).
Simulates a balloon slowly rising to ~60 m, swaying in the wind, with plausible noise.
By default it mimics our actual kit: BMP280 barometer, 3-axis accelerometer, Air Quality v1.3 on A4.
Set BALLOON_SIM_ALL=1 to also fake humidity, light, UV, SGP30 (for testing those code paths)."""
import math
import os
import random
import time

SIM_ALL = os.environ.get("BALLOON_SIM_ALL", "0") in ("1", "true", "yes")


class SimBarometer:
    KIND = "barometer"
    FIELDS = ["pressure_hpa", "temp_c", "humidity_pct"]
    name = "SIM-BME280" if SIM_ALL else "SIM-BMP280"

    def __init__(self):
        self.t0 = time.monotonic()
        self.p0 = 1013.25 + random.uniform(-5, 5)

    def altitude(self):
        t = time.monotonic() - self.t0
        if t < 10:
            return 0.0
        return min(60.0, (t - 10) * 0.4) + 1.5 * math.sin(t / 7.0)

    def read(self):
        h = self.altitude()
        p = self.p0 * (1 - h / 44330.0) ** 5.255 + random.gauss(0, 0.02)
        return {"pressure_hpa": round(p, 3), "temp_c": round(22.0 - 0.0065 * h + random.gauss(0, 0.03), 2),
                "humidity_pct": round(45 + random.gauss(0, 0.3), 1) if SIM_ALL else None}


class SimAccel:
    KIND = "accel"
    FIELDS = ["ax_g", "ay_g", "az_g"]
    name = "SIM-ADXL345"

    def __init__(self):
        self.t0 = time.monotonic()

    def read(self):
        t = time.monotonic() - self.t0
        pitch = math.radians(8 * math.sin(t / 3.1))
        roll = math.radians(6 * math.sin(t / 2.3 + 1))
        ax = math.sin(pitch) + random.gauss(0, 0.01)
        ay = -math.cos(pitch) * math.sin(roll) + random.gauss(0, 0.01)
        az = math.cos(pitch) * math.cos(roll) + random.gauss(0, 0.01)
        return {"ax_g": ax, "ay_g": ay, "az_g": az}


class SimAnalog:
    KIND = "analog"
    FIELDS = ["light_raw", "light_pct", "uv_mv", "uv_index", "aq_raw", "aq_level"]
    name = "SIM-analog"

    def __init__(self):
        self.t0 = time.monotonic()

    def read(self):
        t = time.monotonic() - self.t0
        light = 62 + 15 * math.sin(t / 20) + random.gauss(0, 0.8)
        uv_mv = max(0, 320 + 80 * math.sin(t / 30) + random.gauss(0, 5))
        aq = int(max(0, 180 + 40 * math.sin(t / 45) + random.gauss(0, 4)))
        out = {"aq_raw": aq, "aq_level": "high" if aq > 700 else ("low" if aq > 300 else "fresh")}
        if SIM_ALL:
            out.update({"light_raw": int(light * 40.95), "light_pct": round(light, 1), "uv_mv": int(uv_mv),
                        "uv_index": round((307 * uv_mv / 1000) / 200, 2)})
        return out


class SimGas:
    KIND = "gas"
    FIELDS = ["eco2_ppm", "tvoc_ppb"]
    name = "SIM-SGP30"

    def read(self):
        return {"eco2_ppm": int(420 + random.gauss(0, 6)), "tvoc_ppb": int(14 + random.gauss(0, 2))}


class SimSystem:
    KIND = "system"
    FIELDS = ["cpu_temp_c", "wifi_rssi_dbm", "disk_free_gb", "load_1m"]
    name = "SIM-system"

    def read(self):
        return {"cpu_temp_c": round(51 + random.gauss(0, 0.3), 1), "wifi_rssi_dbm": int(-58 + random.gauss(0, 2)),
                "disk_free_gb": 11.4, "load_1m": 0.7}


def sim_sensors():
    sensors = [SimBarometer(), SimAccel(), SimAnalog()]
    if SIM_ALL:
        sensors.append(SimGas())
    sensors.append(SimSystem())
    return sensors

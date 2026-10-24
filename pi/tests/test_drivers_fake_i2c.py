#!/usr/bin/env python3
"""Exercise the REAL driver + detection code path on a laptop with a fake smbus2.
Simulates: BMP280 @0x77 with the Bosch datasheet example (expects 25.08 C / 1006.53 hPa),
ADXL345 @0x53 reading +1 g on Z, Grove ADC @0x04, SGP30 @0x58.
Run:  python3 tests/test_drivers_fake_i2c.py
"""
import os, sys, types, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["BALLOON_DATA"] = os.environ.get("BALLOON_DATA", "/tmp/balloon-fake-test")
os.environ["BALLOON_SIM"] = "0"


def le16(v):
    v &= 0xFFFF
    return [v & 0xFF, v >> 8]


# Bosch datasheet example calibration + raw values
CAL = dict(T1=27504, T2=26435, T3=-1000, P1=36477, P2=-10685, P3=3024, P4=2855, P5=140, P6=-7, P7=15500, P8=-14600, P9=6000)
ADC_T, ADC_P = 519888, 415148
calbytes = sum((le16(CAL[k]) for k in ("T1", "T2", "T3", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9")), []) + [0, 0]
p20, t20 = ADC_P << 4, ADC_T << 4
rawbytes = [p20 >> 16 & 0xFF, p20 >> 8 & 0xFF, p20 & 0xFF, t20 >> 16 & 0xFF, t20 >> 8 & 0xFF, t20 & 0xFF]


class FakeMsg(list):
    def __init__(self, addr, data, read=False, n=0):
        super().__init__(data)
        self.addr, self.read_flag, self.n = addr, read, n


class FakeBus:
    DEVICES = {0x77, 0x53, 0x04, 0x58}

    def __init__(self, bus):
        self.regs = {}

    def _chk(self, addr):
        if addr not in self.DEVICES:
            raise OSError(121, "Remote I/O error")

    def read_byte(self, addr):
        self._chk(addr)
        return 0

    def write_quick(self, addr):
        self._chk(addr)

    def write_byte_data(self, addr, reg, val):
        self._chk(addr)
        self.regs[(addr, reg)] = val

    def read_byte_data(self, addr, reg):
        self._chk(addr)
        if addr == 0x77 and reg == 0xD0:
            return 0x58
        if addr == 0x53 and reg == 0x00:
            return 0xE5
        return self.regs.get((addr, reg), 0)

    def read_i2c_block_data(self, addr, reg, n):
        self._chk(addr)
        if addr == 0x77 and reg == 0x88:
            return calbytes[:n]
        if addr == 0x77 and reg == 0xF7:
            return rawbytes[:n]
        if addr == 0x53 and reg == 0x32:
            return le16(0) + le16(0) + le16(256)   # 256 * 3.9 mg = 0.998 g on Z
        return [0] * n

    def read_word_data(self, addr, reg):
        self._chk(addr)
        if addr == 0x04:
            ch = reg & 0x0F
            if reg & 0xF0 == 0x10: return [2000, 0, 300, 0, 450, 0, 0, 0][ch]   # raw
            if reg & 0xF0 == 0x20: return [1611, 0, 242, 0, 362, 0, 0, 0][ch]   # mV
            if reg & 0xF0 == 0x30: return [488, 0, 73, 0, 110, 0, 0, 0][ch]     # 0.1 %
            return 3
        return 0

    def i2c_rdwr(self, *msgs):
        for m in msgs:
            if m.read_flag:
                m[:] = [0x01, 0xA4, 0, 0x00, 0x14, 0]   # eCO2 420, TVOC 20


fake = types.ModuleType("smbus2")
fake.SMBus = FakeBus
fake.i2c_msg = types.SimpleNamespace(write=lambda a, d: FakeMsg(a, d), read=lambda a, n: FakeMsg(a, [0] * n, True, n))
sys.modules["smbus2"] = fake

from balloon import sensors as S

sens, info = S.detect_sensors()
names = [s.name for s in sens]
print("I2C:", info["i2c_addresses"], "detected:", names, "errors:", info["errors"])
assert info["errors"] == [], info["errors"]
assert {"BMP280", "ADXL345", "AnalogSensors", "SGP30", "system"} <= set(names), names

readings = {}
for s in sens:
    readings.update(s.read())
print({k: v for k, v in readings.items() if k not in ("cpu_temp_c", "wifi_rssi_dbm", "disk_free_gb", "load_1m")})
assert abs(readings["temp_c"] - 25.08) < 0.02, readings["temp_c"]
assert abs(readings["pressure_hpa"] - 1006.53) < 0.05, readings["pressure_hpa"]
assert abs(readings["az_g"] - 1.0) < 0.01 and abs(readings["ax_g"]) < 1e-6
assert readings["light_pct"] == 48.8 and readings["uv_mv"] == 242 and readings["aq_raw"] == 450 and readings["aq_level"] == "low"
assert readings["eco2_ppm"] == 420 and readings["tvoc_ppb"] == 20

# derived values through the sampler
t = S.Telemetry()
row = {"pressure_hpa": 1006.53, "ax_g": 0.0, "ay_g": 0.0, "az_g": 1.0}
for i in range(S.config.ZERO_SAMPLES):
    t._derive(dict(row), i * 0.2)
r = {"pressure_hpa": 1006.53 * (1 - 100 / 44330.0) ** 5.255, "ax_g": 0.5, "ay_g": 0.0, "az_g": 0.866}
t._derive(r, 99.0)
print("100 m test ->", r["altitude_raw_m"], "m ; tilt", r["tilt_deg"], "pitch", r["pitch_deg"])
assert abs(r["altitude_raw_m"] - 100.0) < 0.5
assert abs(r["tilt_deg"] - 30.0) < 0.1 and abs(r["pitch_deg"] - 30.0) < 0.1
print("ALL OK")

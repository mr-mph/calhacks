"""Sensirion SGP30 VOC / eCO2 sensor (Grove - VOC and eCO2 Gas Sensor), address 0x58.
Needs ~15 s warm-up; returns 400 ppm / 0 ppb until then. Should be polled at 1 Hz."""
import time
from smbus2 import i2c_msg


class SGP30:
    KIND = "gas"
    FIELDS = ["eco2_ppm", "tvoc_ppb"]
    name = "SGP30"

    def __init__(self, bus, address=0x58):
        self.bus, self.addr = bus, address
        self._cmd(0x20, 0x03)   # iaq_init
        time.sleep(0.01)
        self._last = 0.0
        self._cache = {"eco2_ppm": None, "tvoc_ppb": None}

    def _cmd(self, hi, lo):
        self.bus.i2c_rdwr(i2c_msg.write(self.addr, [hi, lo]))

    def read(self):
        now = time.monotonic()
        if now - self._last < 1.0:
            return dict(self._cache)
        self._last = now
        self._cmd(0x20, 0x08)   # measure_iaq
        time.sleep(0.013)
        msg = i2c_msg.read(self.addr, 6)
        self.bus.i2c_rdwr(msg)
        d = list(msg)
        self._cache = {"eco2_ppm": (d[0] << 8) | d[1], "tvoc_ppb": (d[3] << 8) | d[4]}
        return dict(self._cache)

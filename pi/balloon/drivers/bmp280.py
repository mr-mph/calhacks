"""Bosch BMP280 / BME280 pressure + temperature (+ humidity on BME280).
Grove "Temperature & Barometer Sensor (BMP280)" sits at 0x77.
Grove "Temp & Humi & Barometer (BME280)" sits at 0x76."""
import time

CHIP_IDS = {0x58: "BMP280", 0x60: "BME280", 0x56: "BMP280", 0x57: "BMP280"}


class BMP280:
    KIND = "barometer"
    FIELDS = ["pressure_hpa", "temp_c", "humidity_pct"]

    def __init__(self, bus, address=0x77):
        self.bus = bus
        self.addr = address
        chip = bus.read_byte_data(address, 0xD0)
        if chip not in CHIP_IDS:
            raise RuntimeError("unexpected chip id 0x%02x at 0x%02x" % (chip, address))
        self.name = CHIP_IDS[chip]
        self.is_bme = chip == 0x60
        self._read_calibration()
        # humidity oversampling x1 (BME only, must be written before ctrl_meas)
        if self.is_bme:
            bus.write_byte_data(address, 0xF2, 0x01)
        # config: standby 62.5ms, IIR filter coeff 4
        bus.write_byte_data(address, 0xF5, 0x28)
        # ctrl_meas: temp x2, pressure x16, normal mode
        bus.write_byte_data(address, 0xF4, 0x57)
        time.sleep(0.1)

    def _s16(self, v):
        return v - 65536 if v > 32767 else v

    def _read_calibration(self):
        b = self.bus
        a = self.addr
        c = b.read_i2c_block_data(a, 0x88, 26)
        u16 = lambda i: c[i] | (c[i + 1] << 8)
        s16 = lambda i: self._s16(u16(i))
        self.T1 = u16(0); self.T2 = s16(2); self.T3 = s16(4)
        self.P1 = u16(6); self.P2 = s16(8); self.P3 = s16(10); self.P4 = s16(12)
        self.P5 = s16(14); self.P6 = s16(16); self.P7 = s16(18); self.P8 = s16(20); self.P9 = s16(22)
        if self.is_bme:
            self.H1 = c[25]
            h = b.read_i2c_block_data(a, 0xE1, 7)
            self.H2 = self._s16(h[0] | (h[1] << 8))
            self.H3 = h[2]
            self.H4 = self._s16((h[3] << 4) | (h[4] & 0x0F)) if (h[3] << 4) < 2048 else ((h[3] << 4) | (h[4] & 0x0F)) - 4096
            self.H5 = ((h[5] << 4) | (h[4] >> 4))
            if self.H5 > 2047:
                self.H5 -= 4096
            self.H6 = h[6] - 256 if h[6] > 127 else h[6]

    def read(self):
        n = 8 if self.is_bme else 6
        d = self.bus.read_i2c_block_data(self.addr, 0xF7, n)
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        # temperature (datasheet double-precision formula)
        v1 = (adc_t / 16384.0 - self.T1 / 1024.0) * self.T2
        v2 = (adc_t / 131072.0 - self.T1 / 8192.0) ** 2 * self.T3
        t_fine = v1 + v2
        temp = t_fine / 5120.0
        # pressure
        v1 = t_fine / 2.0 - 64000.0
        v2 = v1 * v1 * self.P6 / 32768.0
        v2 = v2 + v1 * self.P5 * 2.0
        v2 = v2 / 4.0 + self.P4 * 65536.0
        v1 = (self.P3 * v1 * v1 / 524288.0 + self.P2 * v1) / 524288.0
        v1 = (1.0 + v1 / 32768.0) * self.P1
        if v1 == 0:
            return {"pressure_hpa": None, "temp_c": round(temp, 2), "humidity_pct": None}
        p = 1048576.0 - adc_p
        p = (p - v2 / 4096.0) * 6250.0 / v1
        v1 = self.P9 * p * p / 2147483648.0
        v2 = p * self.P8 / 32768.0
        p = p + (v1 + v2 + self.P7) / 16.0
        out = {"pressure_hpa": round(p / 100.0, 3), "temp_c": round(temp, 2), "humidity_pct": None}
        if self.is_bme:
            adc_h = (d[6] << 8) | d[7]
            h = t_fine - 76800.0
            h = (adc_h - (self.H4 * 64.0 + self.H5 / 16384.0 * h)) * (
                self.H2 / 65536.0 * (1.0 + self.H6 / 67108864.0 * h * (1.0 + self.H3 / 67108864.0 * h)))
            h = h * (1.0 - self.H1 * h / 524288.0)
            out["humidity_pct"] = round(max(0.0, min(100.0, h)), 1)
        return out

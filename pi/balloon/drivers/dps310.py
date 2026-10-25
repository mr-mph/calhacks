"""Infineon DPS310 / DPS368 barometer (Grove "High Precision Barometric Pressure Sensor"), I2C 0x77 (or 0x76).
Product-ID register 0x0D reads 0x10 (DPS310) or 0x11 (DPS368). Continuous mode, 4 Hz, pressure 16x oversampled."""
import time

_KP = {0: 524288, 1: 1572864, 2: 3670016, 3: 7864320, 4: 253952, 5: 516096, 6: 1040384, 7: 2088960}


def _twos(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


class DPS310:
    KIND = "barometer"
    FIELDS = ["pressure_hpa", "temp_c", "humidity_pct"]

    def __init__(self, bus, address=0x77):
        self.bus, self.addr = bus, address
        pid = bus.read_byte_data(address, 0x0D)
        if pid & 0x0F not in (0x00, 0x01):
            raise RuntimeError("not a DPS310 (product id 0x%02x)" % pid)
        self.name = "DPS368" if pid & 0x0F == 0x01 else "DPS310"
        # soft reset, then wait for coefficients
        bus.write_byte_data(address, 0x0C, 0x89)
        time.sleep(0.05)
        for _ in range(50):
            if bus.read_byte_data(address, 0x08) & 0x80:
                break
            time.sleep(0.01)
        c = bus.read_i2c_block_data(address, 0x10, 18)
        self.c0 = _twos((c[0] << 4) | (c[1] >> 4), 12)
        self.c1 = _twos(((c[1] & 0x0F) << 8) | c[2], 12)
        self.c00 = _twos((c[3] << 12) | (c[4] << 4) | (c[5] >> 4), 20)
        self.c10 = _twos(((c[5] & 0x0F) << 16) | (c[6] << 8) | c[7], 20)
        self.c01 = _twos((c[8] << 8) | c[9], 16)
        self.c11 = _twos((c[10] << 8) | c[11], 16)
        self.c20 = _twos((c[12] << 8) | c[13], 16)
        self.c21 = _twos((c[14] << 8) | c[15], 16)
        self.c30 = _twos((c[16] << 8) | c[17], 16)
        tmp_ext = bus.read_byte_data(address, 0x28) & 0x80          # which temperature sensor the coefficients are for
        # Infineon's documented temperature-readout fix (harmless on parts that don't need it)
        for reg, val in ((0x0E, 0xA5), (0x0F, 0x96), (0x62, 0x02), (0x0E, 0x00), (0x0F, 0x00)):
            bus.write_byte_data(address, reg, val)
        prs_os, tmp_os = 4, 0                                        # pressure 16x, temperature 1x
        self.kP, self.kT = _KP[prs_os], _KP[tmp_os]
        bus.write_byte_data(address, 0x06, (0x02 << 4) | prs_os)   # 4 Hz
        bus.write_byte_data(address, 0x07, tmp_ext | (0x02 << 4) | tmp_os)
        bus.write_byte_data(address, 0x09, 0x04 if prs_os > 3 else 0x00)   # P_SHIFT when oversampling > 8x
        bus.write_byte_data(address, 0x08, 0x07)                     # continuous pressure + temperature
        time.sleep(0.3)

    def read(self):
        d = self.bus.read_i2c_block_data(self.addr, 0x00, 6)
        praw = _twos((d[0] << 16) | (d[1] << 8) | d[2], 24)
        traw = _twos((d[3] << 16) | (d[4] << 8) | d[5], 24)
        t_sc = traw / self.kT
        p_sc = praw / self.kP
        temp = self.c0 * 0.5 + self.c1 * t_sc
        p = (self.c00 + p_sc * (self.c10 + p_sc * (self.c20 + p_sc * self.c30))
             + t_sc * self.c01 + t_sc * p_sc * (self.c11 + p_sc * self.c21))
        return {"pressure_hpa": round(p / 100.0, 3), "temp_c": round(temp, 2), "humidity_pct": None}

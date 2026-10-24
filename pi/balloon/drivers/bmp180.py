"""Bosch BMP180 barometer (older Grove Barometer Sensor), address 0x77, chip id 0x55."""
import time


class BMP180:
    KIND = "barometer"
    FIELDS = ["pressure_hpa", "temp_c", "humidity_pct"]
    name = "BMP180"

    def __init__(self, bus, address=0x77):
        self.bus = bus
        self.addr = address
        if bus.read_byte_data(address, 0xD0) != 0x55:
            raise RuntimeError("not a BMP180")
        c = bus.read_i2c_block_data(address, 0xAA, 22)
        s16 = lambda i: int.from_bytes(bytes(c[i:i + 2]), "big", signed=True)
        u16 = lambda i: int.from_bytes(bytes(c[i:i + 2]), "big", signed=False)
        self.AC1, self.AC2, self.AC3 = s16(0), s16(2), s16(4)
        self.AC4, self.AC5, self.AC6 = u16(6), u16(8), u16(10)
        self.B1, self.B2, self.MB, self.MC, self.MD = s16(12), s16(14), s16(16), s16(18), s16(20)
        self.oss = 3

    def read(self):
        b, a = self.bus, self.addr
        b.write_byte_data(a, 0xF4, 0x2E)
        time.sleep(0.005)
        d = b.read_i2c_block_data(a, 0xF6, 2)
        ut = (d[0] << 8) | d[1]
        b.write_byte_data(a, 0xF4, 0x34 + (self.oss << 6))
        time.sleep(0.026)
        d = b.read_i2c_block_data(a, 0xF6, 3)
        up = ((d[0] << 16) | (d[1] << 8) | d[2]) >> (8 - self.oss)
        x1 = (ut - self.AC6) * self.AC5 >> 15
        x2 = (self.MC << 11) // (x1 + self.MD)
        b5 = x1 + x2
        temp = ((b5 + 8) >> 4) / 10.0
        b6 = b5 - 4000
        x1 = (self.B2 * (b6 * b6 >> 12)) >> 11
        x2 = self.AC2 * b6 >> 11
        x3 = x1 + x2
        b3 = (((self.AC1 * 4 + x3) << self.oss) + 2) >> 2
        x1 = self.AC3 * b6 >> 13
        x2 = (self.B1 * (b6 * b6 >> 12)) >> 16
        x3 = ((x1 + x2) + 2) >> 2
        b4 = self.AC4 * (x3 + 32768) >> 15
        b7 = (up - b3) * (50000 >> self.oss)
        p = (b7 * 2) // b4 if b7 < 0x80000000 else (b7 // b4) * 2
        x1 = (p >> 8) * (p >> 8)
        x1 = (x1 * 3038) >> 16
        x2 = (-7357 * p) >> 16
        p = p + ((x1 + x2 + 3791) >> 4)
        return {"pressure_hpa": round(p / 100.0, 3), "temp_c": round(temp, 2), "humidity_pct": None}

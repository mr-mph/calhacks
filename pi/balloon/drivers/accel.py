"""3-axis accelerometers that ship in Grove kits. All return g units.
  ADXL345   (Grove 3-Axis Digital Accelerometer ±16g)      0x53
  LIS3DHTR  (Grove 3-Axis Digital Accelerometer LIS3DHTR)  0x19 / 0x18
  MMA7660   (Grove 3-Axis Digital Accelerometer ±1.5g)     0x4C
  MPU6050 / MPU9250 / MPU6500 (Grove IMU 6/9DOF)           0x68 / 0x69  (also gyro)
"""


def _s16le(lo, hi):
    v = lo | (hi << 8)
    return v - 65536 if v > 32767 else v


def _s16be(hi, lo):
    return _s16le(lo, hi)


class ADXL345:
    KIND = "accel"
    FIELDS = ["ax_g", "ay_g", "az_g"]
    name = "ADXL345"

    def __init__(self, bus, address=0x53):
        self.bus, self.addr = bus, address
        if bus.read_byte_data(address, 0x00) != 0xE5:
            raise RuntimeError("not an ADXL345")
        bus.write_byte_data(address, 0x2C, 0x0A)   # 100 Hz
        bus.write_byte_data(address, 0x31, 0x08)   # full resolution, ±2g (3.9 mg/LSB)
        bus.write_byte_data(address, 0x2D, 0x08)   # measure

    def read(self):
        d = self.bus.read_i2c_block_data(self.addr, 0x32, 6)
        s = 0.0039
        return {"ax_g": _s16le(d[0], d[1]) * s, "ay_g": _s16le(d[2], d[3]) * s, "az_g": _s16le(d[4], d[5]) * s}


class LIS3DH:
    KIND = "accel"
    FIELDS = ["ax_g", "ay_g", "az_g"]
    name = "LIS3DHTR"

    def __init__(self, bus, address=0x19):
        self.bus, self.addr = bus, address
        if bus.read_byte_data(address, 0x0F) != 0x33:
            raise RuntimeError("not a LIS3DH")
        bus.write_byte_data(address, 0x20, 0x57)   # 100 Hz, XYZ on
        bus.write_byte_data(address, 0x23, 0x88)   # BDU, high-res, ±2g

    def read(self):
        d = self.bus.read_i2c_block_data(self.addr, 0x28 | 0x80, 6)
        # 12-bit left-justified, 1 mg/LSB in HR mode at ±2g
        conv = lambda lo, hi: (_s16le(lo, hi) >> 4) * 0.001
        return {"ax_g": conv(d[0], d[1]), "ay_g": conv(d[2], d[3]), "az_g": conv(d[4], d[5])}


class MMA7660:
    KIND = "accel"
    FIELDS = ["ax_g", "ay_g", "az_g"]
    name = "MMA7660"

    def __init__(self, bus, address=0x4C):
        self.bus, self.addr = bus, address
        bus.write_byte_data(address, 0x07, 0x00)   # standby to configure
        bus.write_byte_data(address, 0x08, 0x00)   # 120 samples/s
        bus.write_byte_data(address, 0x07, 0x01)   # active

    def read(self):
        d = self.bus.read_i2c_block_data(self.addr, 0x00, 3)

        def conv(v):
            v &= 0x3F
            if v > 31:
                v -= 64
            return v / 21.33
        return {"ax_g": conv(d[0]), "ay_g": conv(d[1]), "az_g": conv(d[2])}


class MPU6050:
    KIND = "accel"
    FIELDS = ["ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps"]

    def __init__(self, bus, address=0x68):
        self.bus, self.addr = bus, address
        who = bus.read_byte_data(address, 0x75)
        names = {0x68: "MPU6050", 0x70: "MPU6500", 0x71: "MPU9250", 0x73: "MPU9255", 0x72: "MPU6886"}
        if who not in names:
            raise RuntimeError("unexpected WHO_AM_I 0x%02x" % who)
        self.name = names[who]
        bus.write_byte_data(address, 0x6B, 0x01)   # wake, PLL clock
        bus.write_byte_data(address, 0x1C, 0x00)   # accel ±2g
        bus.write_byte_data(address, 0x1B, 0x00)   # gyro ±250 dps
        bus.write_byte_data(address, 0x1A, 0x03)   # DLPF ~44 Hz

    def read(self):
        d = self.bus.read_i2c_block_data(self.addr, 0x3B, 14)
        a = 1 / 16384.0
        g = 1 / 131.0
        return {
            "ax_g": _s16be(d[0], d[1]) * a, "ay_g": _s16be(d[2], d[3]) * a, "az_g": _s16be(d[4], d[5]) * a,
            "gx_dps": _s16be(d[8], d[9]) * g, "gy_dps": _s16be(d[10], d[11]) * g, "gz_dps": _s16be(d[12], d[13]) * g,
        }

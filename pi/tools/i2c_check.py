#!/usr/bin/env python3
"""Scan the I2C bus and say which sensor each address probably is.  Run on the Pi:  python3 tools/i2c_check.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from smbus2 import SMBus
from balloon.sensors import scan_i2c

GUESS = {0x04: "Grove Base Hat ADC", 0x08: "Grove Base Hat ADC (alt)", 0x76: "BME280 (temp/humidity/pressure)",
         0x77: "BMP280 or BMP180 barometer", 0x53: "ADXL345 accelerometer", 0x19: "LIS3DHTR accelerometer",
         0x18: "LIS3DH / H3LIS331DL accelerometer", 0x4c: "MMA7660 accelerometer", 0x68: "MPU6050/9250 IMU",
         0x58: "SGP30 VOC/eCO2", 0x60: "SI1145 sunlight/UV", 0x29: "TSL2561 light / VL53L0X", 0x5a: "CCS811 air quality",
         0x44: "SHT31 temp/humidity", 0x3c: "OLED display", 0x23: "BH1750 light"}
with SMBus(1) as bus:
    addrs = scan_i2c(bus)
if not addrs:
    print("No I2C devices found. Check: Base Hat seated on all 40 pins, I2C enabled (sudo raspi-config), sensor cables clicked in.")
for a in addrs:
    extra = ""
    if a in (0x76, 0x77):
        try:
            with SMBus(1) as bus:
                cid = bus.read_byte_data(a, 0xD0)
            extra = " chip id 0x%02x -> %s" % (cid, {0x58: "BMP280", 0x60: "BME280", 0x55: "BMP180"}.get(cid, "unknown"))
        except Exception as e:
            extra = " (%s)" % e
    print("0x%02x  %s%s" % (a, GUESS.get(a, "unknown device"), extra))

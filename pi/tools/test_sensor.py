#!/usr/bin/env python3
"""Read every detected sensor a few times and print the values. Run on the Pi:
     python3 tools/test_sensor.py            # all sensors, 5 readings
     python3 tools/test_sensor.py -n 50 -k barometer
Expected: barometer ~1000-1020 hPa and room temp; accel az ~ +1.0 g when flat (|a| ~ 1.0);
light_pct 0-100 (cover it -> drops); uv_index ~0 indoors; aq_raw ~ 50-300 in clean air (breathe on it -> rises)."""
import argparse, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("BALLOON_DATA", "/tmp/balloon-test")
from balloon.sensors import detect_sensors

ap = argparse.ArgumentParser()
ap.add_argument("-n", type=int, default=5)
ap.add_argument("-k", "--kind", help="only this KIND: barometer, accel, analog, gas, system")
a = ap.parse_args()
sensors, info = detect_sensors()
print("I2C:", info["i2c_addresses"], "| detected:", [s.name for s in sensors])
for e in info["errors"]:
    print("  !!", e)
for i in range(a.n):
    for s in sensors:
        if a.kind and s.KIND != a.kind:
            continue
        try:
            vals = s.read()
            print("%-14s %s" % (s.name, "  ".join("%s=%s" % (k, round(v, 3) if isinstance(v, float) else v) for k, v in vals.items())))
        except Exception as e:
            print("%-14s ERROR %s" % (s.name, e))
    time.sleep(0.5)

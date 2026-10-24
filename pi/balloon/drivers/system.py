"""Raspberry Pi housekeeping: CPU temperature, Wi-Fi signal, disk, load."""
import os
import shutil
import subprocess
import time


class SystemStats:
    KIND = "system"
    FIELDS = ["cpu_temp_c", "wifi_rssi_dbm", "disk_free_gb", "load_1m"]
    name = "system"

    def __init__(self, data_root):
        self.data_root = data_root
        self._last = 0.0
        self._cache = {}

    def read(self):
        now = time.monotonic()
        if now - self._last < 2.0 and self._cache:
            return dict(self._cache)
        self._last = now
        out = {"cpu_temp_c": None, "wifi_rssi_dbm": None, "disk_free_gb": None, "load_1m": None}
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                out["cpu_temp_c"] = round(int(f.read().strip()) / 1000.0, 1)
        except Exception:
            pass
        try:
            with open("/proc/net/wireless") as f:
                for line in f.read().splitlines()[2:]:
                    parts = line.split()
                    if parts and parts[0].startswith("wlan"):
                        out["wifi_rssi_dbm"] = int(float(parts[3].rstrip(".")))
                        break
        except Exception:
            pass
        try:
            root = self.data_root if os.path.isdir(self.data_root) else "/"
            out["disk_free_gb"] = round(shutil.disk_usage(root).free / 1e9, 2)
        except Exception:
            pass
        try:
            out["load_1m"] = round(os.getloadavg()[0], 2)
        except Exception:
            pass
        self._cache = out
        return dict(out)

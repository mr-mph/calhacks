"""Grove 16x2 LCD (JHD1313-style text controller at I2C 0x3E; RGB backlight at 0x62 (v1-v4) or 0x30 (v5)).
Shows live altitude and a second line of readings; runs as a thread inside the telemetry service."""
import logging
import threading
import time

log = logging.getLogger("lcd")
TXT = 0x3E


class GroveLCD:
    def __init__(self, bus, rgb_addr=None):
        self.bus = bus
        self.rgb = rgb_addr
        self._cmd(0x28); time.sleep(0.005)   # 2 lines, 5x8
        self._cmd(0x28); time.sleep(0.005)
        self._cmd(0x0C); time.sleep(0.005)   # display on, no cursor
        self.clear()
        self._cmd(0x06)                      # entry mode: left to right
        if self.rgb == 0x62:
            for reg, v in ((0x00, 0x00), (0x01, 0x00), (0x08, 0xAA)):
                self.bus.write_byte_data(0x62, reg, v)
        elif self.rgb == 0x30:
            for reg, v in ((0x00, 0x07), (0x04, 0x15)):
                self.bus.write_byte_data(0x30, reg, v)
        self.set_rgb(0, 80, 160)

    def _cmd(self, c):
        self.bus.write_byte_data(TXT, 0x80, c)

    def clear(self):
        self._cmd(0x01); time.sleep(0.002)

    def set_rgb(self, r, g, b):
        try:
            if self.rgb == 0x62:
                for reg, v in ((0x04, r), (0x03, g), (0x02, b)):
                    self.bus.write_byte_data(0x62, reg, v)
            elif self.rgb == 0x30:
                for reg, v in ((0x06, r), (0x07, g), (0x08, b)):
                    self.bus.write_byte_data(0x30, reg, v)
        except OSError:
            pass

    def write_lines(self, line1, line2=""):
        for row, text in ((0, line1), (1, line2)):
            self._cmd(0x80 | (0x40 if row else 0x00))
            data = text[:16].ljust(16).encode("ascii", "replace")
            # 16 bytes at a time is fine for the JHD1313 (control byte 0x40 = data)
            self.bus.write_i2c_block_data(TXT, 0x40, list(data))


class LcdUpdater(threading.Thread):
    """Refreshes the LCD from the telemetry object twice a second."""

    def __init__(self, telemetry, bus, rgb_addr):
        super().__init__(daemon=True, name="lcd")
        self.t = telemetry
        self.lcd = GroveLCD(bus, rgb_addr)
        self.fail = 0
        self.lcd.write_lines("BALLOON", "starting...")

    def run(self):
        last_color = None
        while True:
            try:
                s = self.t.latest()
                alt = s.get("altitude_m")
                v = s.get("vspeed_mps")
                arrow = "^" if (v or 0) > 0.15 else ("v" if (v or 0) < -0.15 else "-")
                l1 = ("ALT %+6.1fm %s" % (alt, arrow)) if alt is not None else "ALT   ---  "
                aloft = self.t.launch_alt is not None
                if aloft and s.get("alt_since_launch_m") is not None:
                    l1 = "ALT %+6.1fm %s" % (s["alt_since_launch_m"], arrow)
                t = s.get("temp_c"); aq = s.get("aq_raw"); tilt = s.get("tilt_deg")
                l2 = "%s %s %s" % ("%4.1fC" % t if t is not None else " ---C",
                                   "AQ%3d" % aq if aq is not None else "AQ---",
                                   "T%2.0f" % tilt if tilt is not None else "T--")
                self.lcd.write_lines(l1, l2)
                color = (0, 160, 40) if aloft else ((160, 60, 0) if (aq or 0) > 300 else (0, 80, 160))
                if color != last_color:
                    self.lcd.set_rgb(*color); last_color = color
                self.fail = 0
            except OSError as e:
                self.fail += 1
                if self.fail in (1, 10, 100):
                    log.warning("lcd write failed (%d): %s", self.fail, e)
                time.sleep(2)
                try:
                    self.lcd.__init__(self.lcd.bus, self.lcd.rgb)   # re-init after a glitch / unplug-replug
                except OSError:
                    pass
            time.sleep(0.5)


class LcdWatcher(threading.Thread):
    """Hot-plug friendly: polls the bus every few seconds until a Grove LCD answers, then runs the updater."""

    def __init__(self, telemetry):
        super().__init__(daemon=True, name="lcd-watch")
        self.t = telemetry
        self.updater = None

    def run(self):
        from smbus2 import SMBus
        bus = SMBus(1)
        while self.updater is None:
            try:
                bus.read_byte(TXT)
            except OSError:
                time.sleep(5)
                continue
            rgb = None
            for a in (0x62, 0x30):
                try:
                    bus.read_byte(a); rgb = a; break
                except OSError:
                    pass
            try:
                self.updater = LcdUpdater(self.t, bus, rgb)
                self.updater.start()
                log.info("Grove LCD started (rgb backlight at %s)", hex(rgb) if rgb else "none")
            except Exception as e:
                log.warning("LCD init failed: %s", e)
                time.sleep(5)


def start_lcd(telemetry, i2c_addresses=None):
    """Start watching for a Grove LCD (plug it into any I2C port at any time). Returns the watcher thread."""
    try:
        w = LcdWatcher(telemetry)
        w.start()
        return w
    except Exception as e:
        log.warning("LCD watcher not started: %s", e)
        return None

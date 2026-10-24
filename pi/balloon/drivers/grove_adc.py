"""The Grove Base Hat's onboard ADC (an STM32 at I2C 0x04 or 0x08).
Channels 0..7 map to the A0..A7 labels; the Base Hat exposes A0, A2, A4, A6 as Grove ports
(each port carries two channels, e.g. port A0 = channels 0 and 1; we use the first)."""

REG_RAW = 0x10      # 12-bit raw
REG_VOLTAGE = 0x20  # millivolts
REG_RATIO = 0x30    # 0.1 % of supply


class GroveADC:
    KIND = "adc"
    name = "GroveBaseHatADC"

    def __init__(self, bus, address=0x04):
        self.bus, self.addr = bus, address
        self.version = bus.read_word_data(address, 0x02) & 0xFF

    def raw(self, ch):
        return self.bus.read_word_data(self.addr, REG_RAW + ch)

    def millivolts(self, ch):
        return self.bus.read_word_data(self.addr, REG_VOLTAGE + ch)

    def ratio_pct(self, ch):
        return self.bus.read_word_data(self.addr, REG_RATIO + ch) / 10.0


class AnalogSensors:
    """Wraps the ADC with the analog Grove sensors we expect:
      light : Grove Light Sensor v1.2 (LS06-S photodiode)   -> light_raw, light_pct
      uv    : Grove UV Sensor (GUVA-S12SD)                   -> uv_mv, uv_index
      aq    : Grove Air Quality Sensor v1.3                  -> aq_raw, aq_level
    """
    KIND = "analog"
    FIELDS = ["light_raw", "light_pct", "uv_mv", "uv_index", "aq_raw", "aq_level"]
    name = "AnalogSensors"

    def __init__(self, adc, channels):
        self.adc = adc
        self.channels = channels

    def read(self):
        out = {}
        if "light" in self.channels:
            ch = self.channels["light"]
            out["light_raw"] = self.adc.raw(ch)
            out["light_pct"] = self.adc.ratio_pct(ch)
        if "uv" in self.channels:
            mv = self.adc.millivolts(self.channels["uv"])
            out["uv_mv"] = mv
            # Seeed wiki: illumination intensity (mW/m^2) = 307 * Vsig ; UV index ~ intensity / 200
            out["uv_index"] = round((307.0 * mv / 1000.0) / 200.0, 2)
        if "aq" in self.channels:
            raw = self.adc.raw(self.channels["aq"])
            out["aq_raw"] = raw
            # thresholds from Seeed's grove.py example (12-bit raw)
            out["aq_level"] = "high" if raw > 700 else ("low" if raw > 300 else "fresh")
        return out

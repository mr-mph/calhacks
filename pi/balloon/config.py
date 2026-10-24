"""Central configuration. Everything can be overridden with environment variables
(set them in /etc/default/balloon on the Pi, see setup.sh)."""
import os


def _env(name, default, cast=str):
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    try:
        return cast(v)
    except Exception:
        return default


# Simulation: fake sensors + fake camera so the dashboard can be developed on a laptop.
SIM = _env("BALLOON_SIM", "0") in ("1", "true", "yes")

# Where everything is written. On the Pi this is the microSD card.
DATA_ROOT = _env("BALLOON_DATA", "/data/balloon")
SESSIONS_DIR = os.path.join(DATA_ROOT, "sessions")

# Sampling
SAMPLE_HZ = _env("BALLOON_SAMPLE_HZ", 5.0, float)
HISTORY_SECONDS = _env("BALLOON_HISTORY_SECONDS", 1800, int)   # in-memory ring buffer for charts
ZERO_SAMPLES = _env("BALLOON_ZERO_SAMPLES", 25, int)          # samples averaged for ground pressure
ALT_SMOOTHING = _env("BALLOON_ALT_SMOOTHING", 0.25, float)    # EMA alpha for displayed altitude
# Sea-level pressure (QNH) for the estimated elevation above sea level. Check a local METAR/weather site
# before a flight (SF is usually 1010-1020 hPa); can be changed live with POST /api/qnh {"qnh": 1016.2}.
QNH_HPA = _env("BALLOON_QNH_HPA", 1013.25, float)

# Network
HTTP_PORT = _env("BALLOON_HTTP_PORT", 8080, int)
CAMERA_PORT = _env("BALLOON_CAMERA_PORT", 8081, int)
CAMERA_HOST = _env("BALLOON_CAMERA_HOST", "127.0.0.1")

# I2C
I2C_BUS = _env("BALLOON_I2C_BUS", 1, int)

# Analog sensors on the Grove Base Hat (channel numbers are the A0/A2/A4/A6 labels).
# Format: "name:channel,name:channel". Names understood: light, uv, aq (air quality).
# Set to "" to disable all analog sensors.
ANALOG = {}
for part in _env("BALLOON_ANALOG", "aq:4").split(","):
    if ":" in part:
        n, c = part.split(":", 1)
        try:
            ANALOG[n.strip()] = int(c)
        except ValueError:
            pass

# Camera / recording
CAMERA_RESOLUTION = _env("BALLOON_CAMERA_RES", "640x480")
CAMERA_FPS = _env("BALLOON_CAMERA_FPS", 15, int)
RECORD_SEGMENT_SECONDS = _env("BALLOON_SEGMENT_SECONDS", 60, int)
STILL_INTERVAL = _env("BALLOON_STILL_INTERVAL", 2.0, float)   # seconds between saved stills
MIN_FREE_GB = _env("BALLOON_MIN_FREE_GB", 1.0, float)         # stop video when SD is this full

# Mapper (mosaic from the downward camera)
MOSAIC_SCALE = _env("BALLOON_MOSAIC_SCALE", 0.5, float)
MOSAIC_MAX_SIZE = _env("BALLOON_MOSAIC_MAX", 3000, int)

# Optional servo for camera pan (GPIO18 = Grove PWM port D18 on the Base Hat)
SERVO_GPIO = _env("BALLOON_SERVO_GPIO", 18, int)
SERVO_ENABLED = _env("BALLOON_SERVO", "0") in ("1", "true", "yes")

# Written by the telemetry service so other services can find the current session.
CURRENT_SESSION_FILE = os.path.join(DATA_ROOT, "current_session")

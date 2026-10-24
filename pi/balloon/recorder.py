"""Records the camera to the SD card, independent of whether anyone is watching.

  video/  : ffmpeg copies the MJPEG stream into 60 s .mkv segments (no re-encode, low CPU)
  stills/ : one JPEG every STILL_INTERVAL seconds + stills/index.csv with the telemetry at that moment
            (these feed the mapper and are useful on their own)

Stops recording video when free space drops under MIN_FREE_GB so telemetry logging never starves.
"""
import csv
import json
import logging
import os
import shutil
import subprocess
import time
import urllib.request

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s recorder %(levelname)s %(message)s")
log = logging.getLogger("recorder")

CAM = "http://%s:%d" % (config.CAMERA_HOST, config.CAMERA_PORT)
API = "http://127.0.0.1:%d" % config.HTTP_PORT


def current_session():
    try:
        with open(config.CURRENT_SESSION_FILE) as f:
            d = f.read().strip()
        if d and os.path.isdir(d):
            return d
    except OSError:
        pass
    return None


def camera_online():
    try:
        with urllib.request.urlopen(CAM + "/state", timeout=2) as r:
            st = json.loads(r.read().decode())
        return bool(st.get("result", {}).get("source", {}).get("online", True))
    except Exception:
        return False


def free_gb(path):
    try:
        return shutil.disk_usage(path).free / 1e9
    except OSError:
        return 0.0


def start_ffmpeg(video_dir):
    pattern = os.path.join(video_dir, "%Y%m%d-%H%M%S.mkv")
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning",
           "-use_wallclock_as_timestamps", "1", "-fflags", "+genpts",
           "-i", CAM + "/stream",
           "-c", "copy", "-f", "segment", "-segment_time", str(config.RECORD_SEGMENT_SECONDS),
           "-reset_timestamps", "1", "-strftime", "1", pattern]
    log.info("starting ffmpeg -> %s", pattern)
    return subprocess.Popen(cmd)


def main():
    ff = None
    ff_session = None
    last_still = 0.0
    index_file = None
    index_writer = None
    index_session = None
    while True:
        session = current_session()
        if not session:
            time.sleep(2)
            continue
        free = free_gb(session)
        online = camera_online()
        low = free < config.MIN_FREE_GB

        # ---- video ----
        if ff is not None and (ff.poll() is not None or ff_session != session or low or not online):
            if ff.poll() is None:
                ff.terminate()
                try:
                    ff.wait(5)
                except subprocess.TimeoutExpired:
                    ff.kill()
            log.info("ffmpeg stopped (rc=%s, low_disk=%s, online=%s)", ff.returncode, low, online)
            ff = None
        if ff is None and online and not low:
            ff = start_ffmpeg(os.path.join(session, "video"))
            ff_session = session
            time.sleep(1)

        # ---- stills ----
        now = time.monotonic()
        if online and not low and now - last_still >= config.STILL_INTERVAL:
            last_still = now
            try:
                with urllib.request.urlopen(CAM + "/snapshot", timeout=3) as r:
                    jpeg = r.read()
                t = time.time()
                name = "%.3f.jpg" % t
                stills_dir = os.path.join(session, "stills")
                tmp = os.path.join(stills_dir, "." + name)
                with open(tmp, "wb") as f:
                    f.write(jpeg)
                os.replace(tmp, os.path.join(stills_dir, name))
                tel = {}
                try:
                    with urllib.request.urlopen(API + "/api/latest", timeout=1) as r:
                        tel = json.loads(r.read().decode())
                except Exception:
                    pass
                if index_session != session or index_file is None:
                    if index_file:
                        index_file.close()
                    p = os.path.join(stills_dir, "index.csv")
                    new = not os.path.exists(p)
                    index_file = open(p, "a", newline="", buffering=1)
                    index_writer = csv.writer(index_file)
                    if new:
                        index_writer.writerow(["file", "t_unix", "altitude_m", "pitch_deg", "roll_deg", "tilt_deg"])
                    index_session = session
                index_writer.writerow([name, "%.3f" % t] + [tel.get(k, "") for k in ("altitude_m", "pitch_deg", "roll_deg", "tilt_deg")])
            except Exception as e:
                log.warning("still failed: %s", e)
        if low and int(now) % 60 == 0:
            log.warning("low disk (%.2f GB free): video and stills paused", free)
        time.sleep(0.5)


if __name__ == "__main__":
    main()

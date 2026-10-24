"""Dashboard + telemetry HTTP server.

Runs the sampler thread (so logging continues even with no viewers) and serves:
  /                    dashboard
  /events              Server-Sent Events: every sample as JSON
  /api/latest          latest sample
  /api/history?seconds=600   recent samples (column-oriented for the charts)
  /api/status          session, detected sensors, failures
  /api/zero  (POST)    re-zero altitude at the current pressure
  /api/mark  (POST)    {"note": "..."} add a timestamped marker ("launch" also sets the since-launch reference)
  /api/qnh   (POST)    {"qnh": 1016.2} sea-level pressure for the estimated elevation
  /api/servo (POST)    {"angle": 0..180}  optional camera pan
  /api/sessions        list recorded sessions with sizes
  /data/<path>         download anything in the data directory (CSV, video, stills)
  /mosaic.jpg          latest stitched map
  /camera/snapshot.jpg proxy to the camera service
"""
import json
import logging
from html import escape
import os
import queue
import time
import urllib.request

from flask import Flask, Response, jsonify, request, send_from_directory, abort

from . import config
from .sensors import Telemetry, COLUMNS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("server")

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(HERE, "static"), static_url_path="/static")
telemetry = Telemetry()
telemetry.start()

servo = None
if config.SERVO_ENABLED:
    try:
        from .servo import Servo
        servo = Servo(config.SERVO_GPIO)
    except Exception as e:
        log.warning("servo disabled: %s", e)


@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/latest")
def api_latest():
    return jsonify(telemetry.latest())


@app.route("/api/history")
def api_history():
    seconds = request.args.get("seconds", type=int)
    rows = telemetry.history(seconds)
    cols = {c: [r.get(c) for r in rows] for c in COLUMNS if c not in ("t_iso",)}
    return jsonify({"columns": cols, "n": len(rows)})


@app.route("/api/status")
def api_status():
    st = telemetry.status()
    st["camera_port"] = config.CAMERA_PORT
    st["servo"] = servo is not None
    st["sim"] = config.SIM
    st["mosaic"] = os.path.exists(os.path.join(telemetry.session_dir, "mosaic.jpg"))
    try:
        with urllib.request.urlopen("http://%s:%d/state" % (config.CAMERA_HOST, config.CAMERA_PORT), timeout=0.5) as r:
            st["camera"] = json.loads(r.read().decode())
    except Exception:
        st["camera"] = None
    return jsonify(st)


@app.route("/api/zero", methods=["POST"])
def api_zero():
    telemetry.request_rezero()
    return jsonify({"ok": True})


@app.route("/api/qnh", methods=["POST"])
def api_qnh():
    """Set sea-level pressure (hPa) used for the estimated elevation above sea level."""
    data = request.get_json(silent=True) or {}
    try:
        q = float(data.get("qnh"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "qnh (hPa) required"}), 400
    if not 900 <= q <= 1100:
        return jsonify({"ok": False, "error": "qnh out of range"}), 400
    telemetry.qnh = q
    return jsonify({"ok": True, "qnh": q})


@app.route("/api/mark", methods=["POST"])
def api_mark():
    data = request.get_json(silent=True) or {}
    note = str(data.get("note") or request.form.get("note") or "mark")[:200]
    return jsonify(telemetry.add_marker(note))


@app.route("/api/servo", methods=["POST"])
def api_servo():
    if servo is None:
        return jsonify({"ok": False, "error": "servo not enabled"}), 400
    data = request.get_json(silent=True) or {}
    angle = float(data.get("angle", 90))
    servo.set_angle(angle)
    return jsonify({"ok": True, "angle": angle})


@app.route("/api/replay/<session>")
def api_replay(session):
    """Column-oriented dump of a past session's telemetry.csv for the dashboard's replay mode."""
    import csv as _csv
    if "/" in session or ".." in session:
        abort(400)
    p = os.path.join(config.SESSIONS_DIR, session, "telemetry.csv")
    if not os.path.exists(p):
        abort(404)
    cols = {c: [] for c in COLUMNS if c != "t_iso"}
    with open(p, newline="") as f:
        for r in _csv.DictReader(f):
            for c in cols:
                v = r.get(c, "")
                if v == "":
                    cols[c].append(None)
                else:
                    try:
                        cols[c].append(float(v))
                    except ValueError:
                        cols[c].append(v)
    markers = []
    mp = os.path.join(config.SESSIONS_DIR, session, "markers.csv")
    if os.path.exists(mp):
        with open(mp, newline="") as f:
            for r in _csv.DictReader(f):
                try:
                    markers.append({"t_unix": float(r["t_unix"]), "note": r.get("note", "")})
                except (KeyError, ValueError):
                    pass
    return jsonify({"session": session, "columns": cols, "n": len(cols["t_unix"]), "markers": markers})


@app.route("/qr.svg")
def qr_svg():
    """QR code pointing at this dashboard (for judges' phones). Pure-python, no dependency."""
    from .qr import qr_svg as _qr
    host = request.host.split(":")[0]
    url = "http://%s:%d/" % (host, config.HTTP_PORT)
    return Response(_qr(url), mimetype="image/svg+xml")


@app.route("/api/sessions")
def api_sessions():
    out = []
    if os.path.isdir(config.SESSIONS_DIR):
        for name in sorted(os.listdir(config.SESSIONS_DIR), reverse=True):
            d = os.path.join(config.SESSIONS_DIR, name)
            if not os.path.isdir(d):
                continue
            size = 0
            nvid = nstill = 0
            for root, _, files in os.walk(d):
                for f in files:
                    try:
                        size += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
                    if root.endswith("video"):
                        nvid += 1
                    elif root.endswith("stills"):
                        nstill += 1
            out.append({"name": name, "current": name == telemetry.session, "size_mb": round(size / 1e6, 1),
                        "video_segments": nvid, "stills": nstill,
                        "csv": "/data/sessions/%s/telemetry.csv" % name})
    return jsonify(out)


@app.route("/data/<path:path>")
def data_files(path):
    root = os.path.realpath(config.DATA_ROOT)
    full = os.path.realpath(os.path.join(root, path))
    # a bare prefix check would also accept a sibling like /data/balloon-old
    if full != root and not full.startswith(root + os.sep):
        abort(403)
    if os.path.isdir(full):
        entries = sorted(os.listdir(full))
        html = ["<html><body style='font-family:system-ui'><h3>/data/%s</h3><ul>" % path]
        for e in entries:
            html.append("<li><a href='/data/%s/%s'>%s</a></li>" % (escape(path.rstrip("/")), escape(e), escape(e)))
        html.append("</ul></body></html>")
        return "\n".join(html)
    return send_from_directory(config.DATA_ROOT, path, as_attachment=False, conditional=True)


@app.route("/mosaic.jpg")
def mosaic():
    p = os.path.join(telemetry.session_dir, "mosaic.jpg")
    if not os.path.exists(p):
        abort(404)
    return send_from_directory(telemetry.session_dir, "mosaic.jpg", conditional=True)


@app.route("/camera/snapshot.jpg")
def camera_snapshot():
    try:
        with urllib.request.urlopen("http://%s:%d/snapshot" % (config.CAMERA_HOST, config.CAMERA_PORT), timeout=2) as r:
            return Response(r.read(), mimetype="image/jpeg")
    except Exception as e:
        return Response("camera unavailable: %s" % e, status=503)


@app.route("/events")
def events():
    def gen():
        q = telemetry.subscribe()
        try:
            yield "retry: 1000\n"
            yield "event: hello\ndata: %s\n\n" % json.dumps({"session": telemetry.session})
            last_beat = time.time()
            while True:
                try:
                    msg = q.get(timeout=5)
                    yield "event: %s\ndata: %s\n\n" % (msg["type"], json.dumps(msg.get("sample") or msg.get("marker")))
                except queue.Empty:
                    pass
                if time.time() - last_beat > 10:
                    yield ": keepalive\n\n"
                    last_beat = time.time()
        finally:
            telemetry.unsubscribe(q)
    return Response(gen(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Connection": "keep-alive"})


def main():
    log.info("dashboard on http://0.0.0.0:%d  (sim=%s, data=%s)", config.HTTP_PORT, config.SIM, config.DATA_ROOT)
    app.run(host="0.0.0.0", port=config.HTTP_PORT, threaded=True, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()

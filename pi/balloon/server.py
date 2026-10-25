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
  /api/level (POST)    take the current orientation as upright (tilt reference)
  /api/detections (POST/GET) ground station posts YOLO detections per frame; dashboard overlays them on the video
  /api/captions (POST/GET)   laptop narrator posts spoken captions (+mp3); dashboard shows and plays them
  /api/ask (POST), /api/ask/pending, /api/ask/answer (POST), /api/ask/<id>   spoken Q&A relay (browser -> laptop)
  /api/elevation (POST) {"elevation_m": 5} calibrate the estimated elevation to the known ground elevation here
  /api/servo (POST)    {"angle": 0..180}  optional camera pan
  /api/sessions        list recorded sessions with sizes
  /data/<path>         download anything in the data directory (CSV, video, stills)
  /mosaic.jpg          latest stitched map
  /camera/snapshot.jpg proxy to the camera service
"""
import json
import logging
from html import escape
import math
import os
from urllib.parse import quote
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
app.config["MAX_CONTENT_LENGTH"] = 1 << 20   # POST bodies are small JSON; /api/detections is open to anyone on the AP
telemetry = Telemetry()
telemetry.start()

lcd = None
if not config.SIM:
    try:
        from .lcd import start_lcd
        lcd = start_lcd(telemetry, telemetry.info.get("i2c_addresses"))
    except Exception as e:
        log.warning("lcd disabled: %s", e)

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
    st["lcd"] = bool(lcd is not None and getattr(lcd, "updater", None) is not None)
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


@app.route("/api/elevation", methods=["POST"])
def api_elevation():
    """{"elevation_m": 5} -> make the estimated elevation read this value here (sets QNH from the current pressure)."""
    data = request.get_json(silent=True) or {}
    try:
        h = float(data.get("elevation_m"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "elevation_m required"}), 400
    if not -500 <= h <= 9000:
        return jsonify({"ok": False, "error": "elevation_m out of range (-500 to 9000)"}), 400
    q = telemetry.set_ground_elevation(h)
    if q is None:
        return jsonify({"ok": False, "error": "no pressure reading yet"}), 503
    return jsonify({"ok": True, "qnh": q, "elevation_m": h})


# Detections come from the ground station (laptop) which runs the YOLO model on our stills.
_det = {"latest": None, "count": 0}


@app.route("/api/detections", methods=["POST"])
def api_detections_post():
    """Ground station posts {"t_unix", "frame", "width", "height", "counts": {"car": n, "person": n},
    "detections": [{"cls": "car", "conf": 0.8, "xyxy": [x1, y1, x2, y2]}], "zones": {...optional}}"""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"ok": False, "error": "json object required"}), 400
    data["received_at"] = time.time()
    data["detections"] = [d for d in (data.get("detections") or []) if isinstance(d, dict)][:300]
    _det["latest"] = data
    _det["count"] += 1
    by_class = {}
    for d in data["detections"]:
        k = str(d.get("cls", "?"))
        by_class[k] = by_class.get(k, 0) + 1
    data["by_class"] = dict(sorted(by_class.items(), key=lambda kv: (-kv[1], kv[0])))
    data["total"] = len(data["detections"])
    c = data.get("counts") or {}
    telemetry.external = {"det_total": data["total"], "det_classes": ",".join("%s:%d" % kv for kv in data["by_class"].items()),
                          "det_cars": c.get("car"), "det_people": c.get("person"), "received_at": data["received_at"]}
    try:
        with open(os.path.join(telemetry.session_dir, "detections.jsonl"), "a") as f:
            f.write(json.dumps(data, separators=(",", ":")) + "\n")
    except OSError:
        pass
    return jsonify({"ok": True, "n": _det["count"]})


@app.route("/api/detections")
def api_detections_get():
    d = _det["latest"]
    if not d:
        return jsonify({"available": False})
    return jsonify({"available": True, "age_s": round(time.time() - d["received_at"], 1), "n": _det["count"], **d})


# ---------------- narrator: captions + spoken Q&A (the model runs on the ground laptop, see ground/narrator.py) -----------
import base64 as _b64
import threading as _threading
import uuid as _uuid
_nar = {"captions": [], "seq": 0, "questions": {}, "lock": _threading.Lock()}


def _save_audio(b64):
    if not b64:
        return None
    try:
        raw = _b64.b64decode(b64)
        d = os.path.join(telemetry.session_dir, "audio")
        os.makedirs(d, exist_ok=True)
        name = "%.3f.mp3" % time.time()
        with open(os.path.join(d, name), "wb") as f:
            f.write(raw)
        return "/data/sessions/%s/audio/%s" % (telemetry.session, name)
    except Exception as e:
        log.warning("audio save failed: %s", e)
        return None


def _add_caption(kind, text, audio_b64=None, question=None, extra=None):
    with _nar["lock"]:
        _nar["seq"] += 1
        rec = {"id": _nar["seq"], "kind": kind, "text": text, "t_unix": time.time(), "question": question,
               "audio_url": _save_audio(audio_b64)}
        if extra:
            rec.update(extra)
        _nar["captions"].append(rec)
        _nar["captions"] = _nar["captions"][-200:]
    try:
        with open(os.path.join(telemetry.session_dir, "captions.jsonl"), "a") as f:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    except OSError:
        pass
    telemetry._broadcast({"type": "caption", "marker": rec})
    return rec


@app.route("/api/captions", methods=["POST"])
def api_captions_post():
    """Laptop narrator posts {"text": "...", "audio_b64": "<mp3>", "model": "..."}."""
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text required"}), 400
    rec = _add_caption("caption", text[:600], data.get("audio_b64"), extra={"model": data.get("model")})
    return jsonify({"ok": True, "id": rec["id"], "audio_url": rec["audio_url"]})


@app.route("/api/captions")
def api_captions_get():
    since = request.args.get("since", type=int) or 0
    with _nar["lock"]:
        items = [c for c in _nar["captions"] if c["id"] > since][-50:]
        latest = _nar["captions"][-1] if _nar["captions"] else None
    return jsonify({"items": items, "latest": latest, "seq": _nar["seq"], "narrator_online": bool(latest and time.time() - latest["t_unix"] < 90)})


@app.route("/api/ask", methods=["POST"])
def api_ask():
    """Dashboard: {"text": "what do you see?"} -> {"id"}; the laptop answers via /api/ask/answer."""
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "").strip()[:500]
    if not text:
        return jsonify({"ok": False, "error": "text required"}), 400
    qid = _uuid.uuid4().hex[:10]
    with _nar["lock"]:
        _nar["questions"][qid] = {"id": qid, "text": text, "t_unix": time.time(), "answer": None}
        for k in [k for k, v in _nar["questions"].items() if time.time() - v["t_unix"] > 600]:
            _nar["questions"].pop(k, None)
    return jsonify({"ok": True, "id": qid})


@app.route("/api/ask/pending")
def api_ask_pending():
    with _nar["lock"]:
        return jsonify([q for q in _nar["questions"].values() if q["answer"] is None])


@app.route("/api/ask/answer", methods=["POST"])
def api_ask_answer():
    data = request.get_json(silent=True) or {}
    qid = data.get("id")
    with _nar["lock"]:
        q = _nar["questions"].get(qid)
    if not q:
        return jsonify({"ok": False, "error": "unknown question"}), 404
    rec = _add_caption("answer", str(data.get("text") or "")[:1000], data.get("audio_b64"), question=q["text"])
    with _nar["lock"]:
        q["answer"] = rec
    return jsonify({"ok": True, "id": rec["id"], "audio_url": rec["audio_url"]})


@app.route("/api/ask/<qid>")
def api_ask_status(qid):
    with _nar["lock"]:
        q = _nar["questions"].get(qid)
    if not q:
        return jsonify({"ok": False, "error": "unknown question"}), 404
    return jsonify({"ok": True, "id": qid, "text": q["text"], "answer": q["answer"]})


@app.route("/api/level", methods=["POST"])
def api_level():
    """Use the current orientation as 'upright' for the tilt reading (the accelerometer can be mounted any way)."""
    ref = telemetry.set_level()
    return jsonify({"ok": ref is not None, "ref": ref})


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
    try:
        angle = float(data.get("angle", 90))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "angle must be a number"}), 400
    if not math.isfinite(angle):
        return jsonify({"ok": False, "error": "angle must be finite"}), 400
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
    try:
        full = os.path.realpath(os.path.join(root, path))
    except ValueError:  # e.g. an embedded NUL byte
        abort(400)
    # a bare prefix check would also accept a sibling like /data/balloon-old
    if full != root and not full.startswith(root + os.sep):
        abort(403)
    if os.path.isdir(full):
        entries = sorted(os.listdir(full))
        html = ["<html><body style='font-family:system-ui'><h3>/data/%s</h3><ul>" % escape(path)]
        for e in entries:
            html.append("<li><a href='/data/%s/%s'>%s</a></li>" % (escape(quote(path.rstrip("/"))), escape(quote(e)), escape(e)))
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

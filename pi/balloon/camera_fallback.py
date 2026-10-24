"""Fallback MJPEG streamer (OpenCV) exposing the same URLs as ustreamer: /stream, /snapshot, /state.
Higher CPU than ustreamer but works anywhere, including a laptop webcam for testing."""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2


class Camera(threading.Thread):
    def __init__(self, device, width, height, fps):
        super().__init__(daemon=True)
        self.device, self.width, self.height, self.fps = device, width, height, fps
        self.frame = None
        self.jpeg = None
        self.seq = 0
        self.cond = threading.Condition()
        self.ok = False

    def open(self):
        src = int(self.device) if str(self.device).isdigit() else self.device
        cap = cv2.VideoCapture(src)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        return cap

    def run(self):
        period = 1.0 / self.fps
        while True:
            cap = self.open()
            if not cap.isOpened():
                self.ok = False
                time.sleep(3)
                continue
            self.ok = True
            while True:
                t = time.monotonic()
                ret, frame = cap.read()
                if not ret:
                    self.ok = False
                    break
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    with self.cond:
                        self.jpeg = buf.tobytes()
                        self.seq += 1
                        self.cond.notify_all()
                dt = period - (time.monotonic() - t)
                if dt > 0:
                    time.sleep(dt)
            cap.release()

    def wait_frame(self, last_seq, timeout=2.0):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq, timeout=timeout)
            return self.jpeg, self.seq


cam = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/snapshot":
            jpeg, _ = cam.wait_frame(-1)
            if jpeg is None:
                self.send_error(503, "no frame")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpeg)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(jpeg)
        elif path == "/state":
            body = json.dumps({"ok": True, "result": {"source": {"online": cam.ok, "captured_fps": cam.fps,
                               "resolution": {"width": cam.width, "height": cam.height}}}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        elif path in ("/stream", "/"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            seq = -1
            try:
                while True:
                    jpeg, seq = cam.wait_frame(seq)
                    if jpeg is None:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpeg))
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_error(404)


def main():
    global cam
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--res", default="640x480")
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--port", type=int, default=8081)
    a = ap.parse_args()
    w, h = (int(x) for x in a.res.lower().split("x"))
    cam = Camera(a.device, w, h, a.fps)
    cam.start()
    print("fallback camera server on :%d (device %s)" % (a.port, a.device), flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

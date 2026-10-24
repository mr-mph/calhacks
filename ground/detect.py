"""Run the aerial detector on a still, a folder of stills, or a snapshot URL; print one JSON line per frame."""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
TRAINED = HERE / "runs/visdrone/weights/best.pt"
PRETRAINED = HERE / "yolo11n.pt"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
URL_TIMEOUT_S = 10

# VisDrone names first, COCO names for the pretrained fallback.
GROUPS = {
    "car": {"car", "van", "truck", "bus"},
    "person": {"pedestrian", "people", "person"},
}


def group_of(name: str) -> str | None:
    return next((g for g, names in GROUPS.items() if name in names), None)


def default_weights() -> Path:
    return TRAINED if TRAINED.exists() else PRETRAINED


def pick_device() -> str:
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


def fetch_url(url: str) -> np.ndarray:
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"only http(s) URLs are supported: {url}")
    with urllib.request.urlopen(url, timeout=URL_TIMEOUT_S) as r:
        buf = np.frombuffer(r.read(), dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"not an image: {url}")
    return img


def frame_time(path: Path) -> float:
    # Recorder names stills "<unix time>.jpg"; anything else falls back to mtime.
    try:
        return float(path.stem)
    except ValueError:
        return path.stat().st_mtime


def iter_frames(source: str, loop_s: float | None) -> Iterator[tuple[str, float, np.ndarray]]:
    if source.startswith(("http://", "https://")):
        if loop_s is None:
            yield source, time.time(), fetch_url(source)
            return
        while True:
            try:
                yield source, time.time(), fetch_url(source)
            except (OSError, ValueError) as e:
                print(f"fetch failed, retrying: {e}", file=sys.stderr)
            time.sleep(loop_s)
    p = Path(source)
    files = sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS) if p.is_dir() else [p]
    for f in files:
        img = cv2.imread(str(f))
        if img is None:
            print(f"skip unreadable {f}", file=sys.stderr)
            continue
        yield str(f), frame_time(f), img


class Detector:
    def __init__(self, weights: Path, imgsz: int, conf: float, device: str):
        self.model = YOLO(str(weights))
        self.imgsz, self.conf, self.device = imgsz, conf, device

    def __call__(self, img: np.ndarray):
        return self.model.predict(img, imgsz=self.imgsz, conf=self.conf, device=self.device, verbose=False)[0]


def to_record(frame: str, t: float, result) -> dict:
    names = result.names
    boxes = result.boxes
    dets = [
        {"cls": names[int(c)], "conf": round(float(s), 3), "xyxy": [round(float(v), 1) for v in xyxy]}
        for c, s, xyxy in zip(boxes.cls.tolist(), boxes.conf.tolist(), boxes.xyxy.tolist())
    ]
    counts = {g: sum(1 for d in dets if group_of(d["cls"]) == g) for g in GROUPS}
    h, w = result.orig_shape
    return {"frame": frame, "t": round(t, 3), "size": [w, h], "detections": dets, "counts": counts}


def save_annotated(result, frame: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = Path(frame).name if not frame.startswith("http") else f"{time.time():.3f}.jpg"
    out = out_dir / name
    cv2.imwrite(str(out), result.plot(line_width=1, font_size=8))
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", help="image file, folder of images, or http(s) URL of a JPEG snapshot")
    ap.add_argument("--weights", type=Path, default=None, help="default: runs/visdrone/weights/best.pt, else yolo11n.pt")
    ap.add_argument("--imgsz", type=int, default=1280, help="inference size; keep near native width for small people")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--device", default=None, help="mps, cpu (default: mps when available)")
    ap.add_argument("--save", type=Path, default=None, help="folder for annotated images")
    ap.add_argument("--loop", type=float, default=None, help="for URLs: poll every N seconds until Ctrl-C")
    return ap


def main() -> None:
    args = build_parser().parse_args()
    weights = args.weights or default_weights()
    print(f"weights: {weights}", file=sys.stderr)
    det = Detector(weights, args.imgsz, args.conf, args.device or pick_device())
    for frame, t, img in iter_frames(args.source, args.loop):
        result = det(img)
        print(json.dumps(to_record(frame, t, result)), flush=True)
        if args.save:
            save_annotated(result, frame, args.save)


if __name__ == "__main__":
    main()

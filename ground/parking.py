"""Decide which parking spaces are occupied from car detections; print one JSON line per frame."""

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, Iterator

import cv2
import numpy as np

from detect import GROUPS

CAR_CLASSES = GROUPS["car"]
FREE_COLOR = (80, 200, 80)
TAKEN_COLOR = (60, 60, 230)


def load_spaces(path: Path) -> tuple[list[dict], tuple[int, int] | None]:
    cfg = json.loads(path.read_text())
    spaces = [{"id": str(s["id"]), "polygon": np.array(s["polygon"], dtype=np.float32)} for s in cfg["spaces"]]
    for s in spaces:
        if s["polygon"].ndim != 2 or s["polygon"].shape[0] < 3 or s["polygon"].shape[1] != 2:
            raise ValueError(f"space {s['id']}: polygon needs 3+ [x, y] points")
    size = tuple(cfg["image_size"]) if "image_size" in cfg else None
    return spaces, size


def scaled(spaces: list[dict], drawn_on: tuple[int, int] | None, frame_size: list[int]) -> list[dict]:
    if not drawn_on or tuple(frame_size) == drawn_on:
        return spaces
    k = np.array([frame_size[0] / drawn_on[0], frame_size[1] / drawn_on[1]], dtype=np.float32)
    return [{**s, "polygon": s["polygon"] * k} for s in spaces]


def box_poly(xyxy: list[float]) -> np.ndarray:
    x1, y1, x2, y2 = xyxy
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)


def overlap(poly: np.ndarray, xyxy: list[float]) -> float:
    """IoU between a convex space polygon and a box."""
    inter, _ = cv2.intersectConvexConvex(poly, box_poly(xyxy))
    union = cv2.contourArea(poly) + (xyxy[2] - xyxy[0]) * (xyxy[3] - xyxy[1]) - inter
    return inter / union if union > 0 else 0.0


def anchor(xyxy: list[float], mode: str) -> tuple[float, float]:
    x1, y1, x2, y2 = xyxy
    return ((x1 + x2) / 2, y2 if mode == "bottom" else (y1 + y2) / 2)


def match(space: dict, cars: list[dict], method: str, iou_thresh: float) -> dict | None:
    if method == "iou":
        scored = [(overlap(space["polygon"], c["xyxy"]), c) for c in cars]
        scored = [(s, c) for s, c in scored if s >= iou_thresh]
    else:
        scored = [
            (c["conf"], c)
            for c in cars
            if cv2.pointPolygonTest(space["polygon"], anchor(c["xyxy"], method), False) >= 0
        ]
    return max(scored, key=lambda sc: sc[0])[1] if scored else None


def occupancy(record: dict, spaces: list[dict], drawn_on, method: str, iou_thresh: float) -> dict:
    cars = [d for d in record["detections"] if d["cls"] in CAR_CLASSES]
    result = []
    for s in scaled(spaces, drawn_on, record["size"]):
        car = match(s, cars, method, iou_thresh)
        result.append({"id": s["id"], "occupied": car is not None, "conf": car["conf"] if car else None})
    taken = sum(r["occupied"] for r in result)
    return {
        "frame": record["frame"],
        "t": record["t"],
        "spaces": result,
        "totals": {"spaces": len(result), "occupied": taken, "free": len(result) - taken, "cars_seen": len(cars)},
    }


def draw(img: np.ndarray, spaces: list[dict], occ: dict) -> np.ndarray:
    out = img.copy()
    for s, r in zip(spaces, occ["spaces"]):
        pts = s["polygon"].astype(np.int32)
        cv2.polylines(out, [pts], True, TAKEN_COLOR if r["occupied"] else FREE_COLOR, 2)
        cv2.putText(out, s["id"], tuple(pts.min(axis=0) + [2, 12]), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
    t = occ["totals"]
    cv2.putText(out, f"free {t['free']}/{t['spaces']}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    return out


def records_from_jsonl(path: str) -> Iterator[dict]:
    stream = sys.stdin if path == "-" else open(path)
    for line in stream:
        if line.strip():
            yield json.loads(line)


def records_from_detector(args) -> Iterable[tuple[dict, np.ndarray]]:
    from detect import Detector, default_weights, iter_frames, pick_device, to_record

    det = Detector(args.weights or default_weights(), args.imgsz, args.conf, args.device or pick_device())
    for frame, t, img in iter_frames(args.source, args.loop):
        yield to_record(frame, t, det(img)), img


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("spaces", type=Path, help="spaces JSON (see README)")
    ap.add_argument("source", nargs="?", help="image, folder or URL; omit when using --from-jsonl")
    ap.add_argument("--from-jsonl", help="read detect.py output from this file ('-' for stdin) instead of detecting")
    ap.add_argument("--method", choices=["center", "bottom", "iou"], default="center",
                    help="center: box centre inside space (top-down camera); bottom: bottom-centre (oblique); iou")
    ap.add_argument("--iou-thresh", type=float, default=0.3)
    ap.add_argument("--weights", type=Path, default=None)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--device", default=None)
    ap.add_argument("--loop", type=float, default=None)
    ap.add_argument("--save", type=Path, default=None, help="folder for images with spaces drawn (detector mode)")
    return ap


def main() -> None:
    args = build_parser().parse_args()
    spaces, drawn_on = load_spaces(args.spaces)
    if args.from_jsonl:
        pairs = ((r, None) for r in records_from_jsonl(args.from_jsonl))
    elif args.source:
        pairs = records_from_detector(args)
    else:
        sys.exit("give a source or --from-jsonl")
    for record, img in pairs:
        occ = occupancy(record, spaces, drawn_on, args.method, args.iou_thresh)
        print(json.dumps(occ), flush=True)
        if args.save and img is not None:
            args.save.mkdir(parents=True, exist_ok=True)
            frame_spaces = scaled(spaces, drawn_on, record["size"])
            cv2.imwrite(str(args.save / Path(record["frame"]).name), draw(img, frame_spaces, occ))


if __name__ == "__main__":
    main()

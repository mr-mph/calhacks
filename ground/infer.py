"""Minimal YOLO wrapper: one image in, merged-class detections out.

Uses the VisDrone fine-tune for cars and people when it exists (else COCO yolo11n.pt), plus the RipAID
oriented-box model for rip currents when its weights exist.
"""
import os
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
VISDRONE_WEIGHTS = HERE / "runs/visdrone/weights/best.pt"
RIP_WEIGHTS = HERE / "runs/ripaid/weights/best.pt"
DEFAULT_WEIGHTS = str(VISDRONE_WEIGHTS) if VISDRONE_WEIGHTS.exists() else "yolo11n.pt"
DEFAULT_IMGSZ = 1280
DEFAULT_CONF = 0.25
RIP_IMGSZ = 960

CLASS_MAP = {
    "car": "car", "van": "car", "truck": "car", "bus": "car",
    "pedestrian": "person", "people": "person", "person": "person",
    "rip": "rip", "rip_current": "rip", "rip-current": "rip",
}


def merge_class(name: str) -> str | None:
    return CLASS_MAP.get(name.strip().lower())


# BALLOON_ALL_CLASSES=1 keeps every class the model knows (COCO's 80, for fun / demos); counts still use car/person.
ALL_CLASSES = os.environ.get("BALLOON_ALL_CLASSES", "0") in ("1", "true", "yes")


def to_detections(names: dict[int, str], cls_ids, confs, boxes) -> list[dict]:
    detections = []
    for cls_id, conf, xyxy in zip(cls_ids, confs, boxes):
        raw = names[int(cls_id)]
        merged = merge_class(raw)
        if merged is None:
            if not ALL_CLASSES:
                continue
            merged = raw.strip().lower()
        detections.append({"cls": merged, "conf": round(float(conf), 3),
                           "xyxy": [round(float(v), 1) for v in xyxy]})
    return detections


def default_rip_weights() -> str | None:
    env = os.environ.get("BALLOON_RIP_WEIGHTS")
    if env is not None:
        return env or None  # set it to "" to turn rip detection off
    return str(RIP_WEIGHTS) if RIP_WEIGHTS.exists() else None


def pick_device() -> str:
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


class Detector:
    def __init__(self, weights: str | None = None, imgsz: int | None = None, conf: float = DEFAULT_CONF,
                 rip_weights: str | None = None):
        from ultralytics import YOLO

        self.weights = weights or os.environ.get("BALLOON_WEIGHTS", DEFAULT_WEIGHTS)
        self.imgsz = imgsz or int(os.environ.get("BALLOON_IMGSZ", DEFAULT_IMGSZ))
        self.conf = conf
        self.device = pick_device()
        self.model = YOLO(self.weights)
        rip = rip_weights or default_rip_weights()
        self.rip_model = YOLO(rip) if rip else None
        stem = "yolo11n-visdrone" if Path(self.weights) == VISDRONE_WEIGHTS else Path(self.weights).stem
        base = os.environ.get("BALLOON_MODEL_NAME", stem)
        self.name = f"{base}+rip" if self.rip_model else base

    def detect(self, image: np.ndarray) -> list[dict]:
        result = self.model.predict(image, imgsz=self.imgsz, conf=self.conf, device=self.device, verbose=False)[0]
        boxes = result.boxes
        found = to_detections(result.names, boxes.cls.tolist(), boxes.conf.tolist(), boxes.xyxy.tolist())
        return found + self.detect_rips(image)

    def detect_rips(self, image: np.ndarray) -> list[dict]:
        if self.rip_model is None:
            return []
        result = self.rip_model.predict(image, imgsz=RIP_IMGSZ, conf=self.conf, device=self.device, verbose=False)[0]
        obb = result.obb
        if obb is None:
            return []
        # oriented boxes collapse to their axis-aligned bounds; the observation record only stores xyxy
        return to_detections(result.names, obb.cls.tolist(), obb.conf.tolist(), obb.xyxy.tolist())

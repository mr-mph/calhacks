"""Minimal YOLO wrapper: one image in, merged-class detections out.

Works with COCO weights (yolo11n.pt) before the VisDrone fine-tune exists, and with the VisDrone weights after.
"""
import os
from pathlib import Path

import numpy as np

DEFAULT_WEIGHTS = "yolo11n.pt"
DEFAULT_IMGSZ = 1280
DEFAULT_CONF = 0.25

CLASS_MAP = {
    "car": "car", "van": "car", "truck": "car", "bus": "car",
    "pedestrian": "person", "people": "person", "person": "person",
    "rip": "rip", "rip_current": "rip", "rip-current": "rip",
}


def merge_class(name: str) -> str | None:
    return CLASS_MAP.get(name.strip().lower())


def to_detections(names: dict[int, str], cls_ids, confs, boxes) -> list[dict]:
    detections = []
    for cls_id, conf, xyxy in zip(cls_ids, confs, boxes):
        merged = merge_class(names[int(cls_id)])
        if merged is None:
            continue
        detections.append({"cls": merged, "conf": round(float(conf), 3),
                           "xyxy": [round(float(v), 1) for v in xyxy]})
    return detections


def pick_device() -> str:
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


class Detector:
    def __init__(self, weights: str | None = None, imgsz: int | None = None, conf: float = DEFAULT_CONF):
        from ultralytics import YOLO

        self.weights = weights or os.environ.get("BALLOON_WEIGHTS", DEFAULT_WEIGHTS)
        self.imgsz = imgsz or int(os.environ.get("BALLOON_IMGSZ", DEFAULT_IMGSZ))
        self.conf = conf
        self.device = pick_device()
        self.model = YOLO(self.weights)
        self.name = os.environ.get("BALLOON_MODEL_NAME", Path(self.weights).stem)

    def detect(self, image: np.ndarray) -> list[dict]:
        result = self.model.predict(image, imgsz=self.imgsz, conf=self.conf, device=self.device, verbose=False)[0]
        boxes = result.boxes
        return to_detections(result.names, boxes.cls.tolist(), boxes.conf.tolist(), boxes.xyxy.tolist())

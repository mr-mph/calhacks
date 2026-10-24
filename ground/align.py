"""Align a frame to the site's reference frame: ORB features + RANSAC, same approach as pi/balloon/mapper.py."""
from dataclasses import dataclass

import cv2
import numpy as np

MIN_INLIERS = 15
MIN_INLIER_RATIO = 0.25
SCALE_RANGE = (0.5, 2.0)
RATIO_TEST = 0.75
RANSAC_PX = 4.0


@dataclass(frozen=True)
class Alignment:
    aligned: bool
    transform: np.ndarray | None
    inlier_ratio: float
    inliers: int
    reason: str = ""


def _failed(reason: str, inliers: int = 0, ratio: float = 0.0) -> Alignment:
    return Alignment(False, None, ratio, inliers, reason)


def _gray(image: np.ndarray, scale: float) -> np.ndarray:
    small = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return small if small.ndim == 2 else cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)


def _transform_scale(H: np.ndarray) -> float:
    return float(np.sqrt(abs(np.linalg.det(H[:2, :2]))))


class Aligner:
    """Maps frame pixels to reference-frame pixels. mode is "similarity" (nadir camera) or "homography"."""

    def __init__(self, reference: np.ndarray, scale: float = 0.5, mode: str = "similarity", nfeatures: int = 3000):
        if mode not in ("similarity", "homography"):
            raise ValueError(f"unknown alignment mode {mode!r}")
        self.scale = scale
        self.mode = mode
        self.orb = cv2.ORB_create(nfeatures=nfeatures, scaleFactor=1.2, nlevels=8)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        self.ref_kp, self.ref_des = self.orb.detectAndCompute(_gray(reference, scale), None)

    def align(self, frame: np.ndarray) -> Alignment:
        kp, des = self.orb.detectAndCompute(_gray(frame, self.scale), None)
        if des is None or self.ref_des is None or len(kp) < MIN_INLIERS:
            return _failed("too few features")
        pairs = self.matcher.knnMatch(des, self.ref_des, k=2)
        good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < RATIO_TEST * p[1].distance]
        if len(good) < MIN_INLIERS:
            return _failed(f"{len(good)} matches")
        src = np.float32([kp[m.queryIdx].pt for m in good])
        dst = np.float32([self.ref_kp[m.trainIdx].pt for m in good])
        H_small, mask = self._estimate(src, dst)
        if H_small is None or mask is None:
            return _failed("RANSAC found no model")
        inliers = int(mask.sum())
        ratio = inliers / len(good)
        if inliers < MIN_INLIERS or ratio < MIN_INLIER_RATIO:
            return _failed(f"{inliers} inliers ({ratio:.2f})", inliers, ratio)
        S = np.diag([self.scale, self.scale, 1.0])
        H = np.linalg.inv(S) @ H_small @ S
        if not SCALE_RANGE[0] < _transform_scale(H) < SCALE_RANGE[1]:
            return _failed("implausible scale", inliers, ratio)
        return Alignment(True, H, ratio, inliers)

    def _estimate(self, src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray | None, np.ndarray | None]:
        if self.mode == "homography":
            return cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_PX)
        A, mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=RANSAC_PX)
        return (None, None) if A is None else (np.vstack([A, [0, 0, 1]]), mask)


def to_reference(transform: np.ndarray, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not points:
        return []
    pts = np.float64(points).reshape(-1, 1, 2)
    return [tuple(p) for p in cv2.perspectiveTransform(pts, transform).reshape(-1, 2).tolist()]

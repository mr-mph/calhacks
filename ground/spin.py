"""Track the camera's spin about its vertical axis from consecutive stills (ORB + RANSAC similarity).
Returns an accumulated heading in degrees (0 = first frame). Lightweight enough for every still at 2 fps."""
import cv2
import numpy as np


class SpinTracker:
    def __init__(self, scale=0.5, min_matches=20):
        self.scale = scale
        self.min_matches = min_matches
        self.orb = cv2.ORB_create(nfeatures=1200)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        self.prev = None          # (kp, des)
        self.heading = 0.0
        self.confidence = 0.0

    def update(self, image) -> dict:
        small = cv2.resize(image, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        kp, des = self.orb.detectAndCompute(gray, None)
        out = {"heading_deg": round(self.heading, 1), "spin_conf": 0.0, "spin_step_deg": None}
        if des is None or len(kp) < self.min_matches:
            self.prev = None
            return out
        if self.prev is not None and self.prev[1] is not None:
            matches = self.matcher.knnMatch(des, self.prev[1], k=2)
            good = [m[0] for m in matches if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
            if len(good) >= self.min_matches:
                src = np.float32([kp[m.queryIdx].pt for m in good])
                dst = np.float32([self.prev[0][m.trainIdx].pt for m in good])
                A, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
                if A is not None and inl is not None and int(inl.sum()) >= self.min_matches:
                    step = float(np.degrees(np.arctan2(A[1, 0], A[0, 0])))   # rotation current -> previous
                    if abs(step) < 60:                                        # reject wild estimates
                        self.heading = (self.heading + step + 180) % 360 - 180
                        self.confidence = min(1.0, int(inl.sum()) / 80.0)
                        out = {"heading_deg": round(self.heading, 1), "spin_conf": round(self.confidence, 2), "spin_step_deg": round(step, 2)}
        self.prev = (kp, des)
        return out

    def reset(self):
        self.heading = 0.0

"""Builds a mosaic ("map") from the downward-facing camera.

Incremental mode (service): watches <session>/stills/, aligns each new still to the previous one with
ORB features + a RANSAC similarity transform (rotation/scale/translation, stable for a nadir camera),
and pastes it onto a growing canvas. Writes <session>/mosaic.jpg which the dashboard shows in the Map tab.

Batch mode (post-flight, better quality):  python3 -m balloon.mapper --batch <session>/stills -o map.jpg
uses OpenCV's SCANS stitcher over all stills.
"""
import argparse
import logging
import os
import time

import cv2
import numpy as np

from . import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s mapper %(levelname)s %(message)s")
log = logging.getLogger("mapper")


class Mosaic:
    def __init__(self, scale=0.5, max_size=3000, min_matches=15):
        self.scale = scale
        self.max_size = max_size
        self.min_matches = min_matches
        self.orb = cv2.ORB_create(nfeatures=2000, scaleFactor=1.2, nlevels=8)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        self.canvas = None
        self.H = None          # maps current frame -> canvas
        self.prev_gray = None
        self.prev_kp = None
        self.prev_des = None
        self.frames = 0
        self.skipped = 0

    def _features(self, gray):
        kp, des = self.orb.detectAndCompute(gray, None)
        return kp, des

    def _paste(self, img, H):
        h, w = img.shape[:2]
        corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
        warped = cv2.perspectiveTransform(corners, H).reshape(-1, 2)
        ch, cw = self.canvas.shape[:2]
        minx, miny = np.floor(warped.min(axis=0)).astype(int)
        maxx, maxy = np.ceil(warped.max(axis=0)).astype(int)
        # expand canvas if needed (translation keeps existing content in place)
        tx = -minx if minx < 0 else 0
        ty = -miny if miny < 0 else 0
        new_w = max(cw + tx, maxx + tx)
        new_h = max(ch + ty, maxy + ty)
        if new_w > self.max_size or new_h > self.max_size:
            return False
        if tx or ty or new_w != cw or new_h != ch:
            nc = np.zeros((new_h, new_w, 3), np.uint8)
            nc[ty:ty + ch, tx:tx + cw] = self.canvas
            self.canvas = nc
            T = np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]], np.float64)
            H = T @ H
            self.H = H
        ch, cw = self.canvas.shape[:2]
        warped_img = cv2.warpPerspective(img, H, (cw, ch))
        mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), H, (cw, ch))
        mask = cv2.erode(mask, np.ones((5, 5), np.uint8))   # trim ragged edges
        self.canvas[mask > 0] = warped_img[mask > 0]
        return True

    def add(self, frame):
        small = cv2.resize(frame, None, fx=self.scale, fy=self.scale, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        kp, des = self._features(gray)
        if self.canvas is None:
            self.canvas = small.copy()
            self.H = np.eye(3)
            self.prev_gray, self.prev_kp, self.prev_des = gray, kp, des
            self.frames = 1
            return True
        if des is None or self.prev_des is None or len(kp) < self.min_matches:
            self.skipped += 1
            return False
        matches = self.matcher.knnMatch(des, self.prev_des, k=2)
        good = [m[0] for m in matches if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
        if len(good) < self.min_matches:
            self.skipped += 1
            return False
        src = np.float32([kp[m.queryIdx].pt for m in good])
        dst = np.float32([self.prev_kp[m.trainIdx].pt for m in good])
        A, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0)
        if A is None or inliers is None or int(inliers.sum()) < self.min_matches:
            self.skipped += 1
            return False
        H_rel = np.vstack([A, [0, 0, 1]])        # current -> previous
        s = np.sqrt(abs(np.linalg.det(A[:, :2])))
        if not (0.5 < s < 2.0):                  # reject absurd scale jumps
            self.skipped += 1
            return False
        H_cur = self.H @ H_rel                   # current -> canvas
        self.H = H_cur
        if not self._paste(small, H_cur):
            log.warning("canvas limit reached; not expanding further")
        self.prev_gray, self.prev_kp, self.prev_des = gray, kp, des
        self.frames += 1
        return True

    def save(self, path):
        if self.canvas is None:
            return
        tmp = path + ".tmp.jpg"
        cv2.imwrite(tmp, self.canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])
        os.replace(tmp, path)


def current_session():
    try:
        with open(config.CURRENT_SESSION_FILE) as f:
            d = f.read().strip()
        return d if d and os.path.isdir(d) else None
    except OSError:
        return None


def run_service():
    mosaic = None
    session = None
    seen = set()
    while True:
        s = current_session()
        if s != session:
            session, mosaic, seen = s, Mosaic(config.MOSAIC_SCALE, config.MOSAIC_MAX_SIZE), set()
            log.info("session %s", s)
        if not session:
            time.sleep(2)
            continue
        stills = os.path.join(session, "stills")
        try:
            names = sorted(f for f in os.listdir(stills) if f.endswith(".jpg") and not f.startswith("."))
        except OSError:
            names = []
        new = [f for f in names if f not in seen]
        added = 0
        for f in new:
            seen.add(f)
            img = cv2.imread(os.path.join(stills, f))
            if img is None:
                continue
            if mosaic.add(img):
                added += 1
        if added:
            mosaic.save(os.path.join(session, "mosaic.jpg"))
            log.info("mosaic: %d frames, %d skipped, canvas %sx%s", mosaic.frames, mosaic.skipped,
                     mosaic.canvas.shape[1], mosaic.canvas.shape[0])
        time.sleep(1.0)


def run_batch(stills_dir, out, every=1, scale=0.5):
    names = sorted(f for f in os.listdir(stills_dir) if f.endswith(".jpg"))[::every]
    imgs = []
    for f in names:
        im = cv2.imread(os.path.join(stills_dir, f))
        if im is not None:
            imgs.append(cv2.resize(im, None, fx=scale, fy=scale))
    log.info("stitching %d images", len(imgs))
    stitcher = cv2.Stitcher_create(cv2.Stitcher_SCANS)
    status, pano = stitcher.stitch(imgs)
    if status != cv2.Stitcher_OK:
        log.error("stitcher failed with status %s; falling back to incremental mosaic", status)
        m = Mosaic(scale=1.0, max_size=6000)
        for im in imgs:
            m.add(im)
        pano = m.canvas
    cv2.imwrite(out, pano)
    log.info("wrote %s (%dx%d)", out, pano.shape[1], pano.shape[0])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", help="stills directory to stitch in one go")
    ap.add_argument("-o", "--out", default="map.jpg")
    ap.add_argument("--every", type=int, default=1, help="use every Nth still in batch mode")
    a = ap.parse_args()
    if a.batch:
        run_batch(a.batch, a.out, a.every)
    else:
        run_service()

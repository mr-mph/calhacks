import cv2
import numpy as np

from align import Aligner, to_reference


def test_consecutive_real_frames_align(real_images):
    ref = cv2.imread(str(real_images["street_a"]))
    frame = cv2.imread(str(real_images["street_b"]))
    result = Aligner(ref).align(frame)
    assert result.aligned and result.inlier_ratio > 0.25
    assert result.transform.shape == (3, 3)


def test_known_shift_and_rotation_is_recovered(real_images):
    ref = cv2.imread(str(real_images["street_a"]))
    h, w = ref.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), 5, 1.0)
    M[:, 2] += (40, -25)
    moved = cv2.warpAffine(ref, M, (w, h))
    result = Aligner(ref).align(moved)
    assert result.aligned
    expected = np.linalg.inv(np.vstack([M, [0, 0, 1]]))
    probe = [(w / 2, h / 2), (300.0, 200.0)]
    got = np.array(to_reference(result.transform, probe))
    want = np.array(to_reference(expected, probe))
    assert np.abs(got - want).max() < 4.0


def test_unrelated_scene_fails(real_images):
    ref = cv2.imread(str(real_images["street_a"]))
    other = cv2.imread(str(real_images["other_scene"]))
    result = Aligner(ref).align(other)
    assert not result.aligned and result.transform is None and result.reason


def test_homography_mode(real_images):
    ref = cv2.imread(str(real_images["street_a"]))
    frame = cv2.imread(str(real_images["street_b"]))
    assert Aligner(ref, mode="homography").align(frame).aligned

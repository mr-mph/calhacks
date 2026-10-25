import cv2

from infer import default_rip_weights, merge_class, to_detections


def test_visdrone_and_coco_names_merge():
    assert [merge_class(n) for n in ("car", "van", "truck", "bus")] == ["car"] * 4
    assert [merge_class(n) for n in ("pedestrian", "people", "person")] == ["person"] * 3
    assert merge_class("bicycle") is None and merge_class("motor") is None


def test_to_detections_drops_unmapped_classes():
    names = {0: "pedestrian", 1: "bicycle", 2: "van"}
    dets = to_detections(names, [0, 1, 2], [0.91234, 0.5, 0.4], [[1, 2, 3, 4], [5, 6, 7, 8], [9.04, 10, 11, 12]])
    assert dets == [{"cls": "person", "conf": 0.912, "xyxy": [1.0, 2.0, 3.0, 4.0]},
                    {"cls": "car", "conf": 0.4, "xyxy": [9.0, 10.0, 11.0, 12.0]}]


def test_coco_model_finds_cars_in_a_real_drone_frame(detector, real_images):
    dets = detector.detect(cv2.imread(str(real_images["cars"])))
    cars = [d for d in dets if d["cls"] == "car"]
    assert len(cars) >= 5
    assert all(set(d) == {"cls", "conf", "xyxy"} for d in dets)


def test_rip_weights_env_overrides_and_empty_disables(monkeypatch):
    monkeypatch.setenv("BALLOON_RIP_WEIGHTS", "custom-rip.pt")
    assert default_rip_weights() == "custom-rip.pt"
    monkeypatch.setenv("BALLOON_RIP_WEIGHTS", "")
    assert default_rip_weights() is None

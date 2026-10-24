import json
import math
import socket
from datetime import datetime, timezone

import pytest
from PIL import Image

import satellite


def test_bbox_is_centered_and_metric():
    w, s, e, n = satellite.bbox_from_center(37.7598, -122.5107, 150)
    assert (w + e) / 2 == pytest.approx(-122.5107)
    assert (s + n) / 2 == pytest.approx(37.7598)
    assert (n - s) * satellite.M_PER_DEG_LAT == pytest.approx(300)
    assert (e - w) * satellite.M_PER_DEG_LAT * math.cos(math.radians(37.7598)) == pytest.approx(300)


@pytest.mark.parametrize("args", [(37.0, -122.0, 0), (95.0, 0.0, 10)])
def test_bbox_rejects_bad_input(args):
    with pytest.raises(ValueError):
        satellite.bbox_from_center(*args)


def test_car_pixels():
    assert satellite.car_pixels(10.0) == pytest.approx(0.45)
    assert satellite.car_pixels(0.6) == pytest.approx(7.5)
    with pytest.raises(ValueError):
        satellite.car_pixels(0)


def test_balloon_gsd():
    gsd = satellite.balloon_gsd_m(100, 70, 1920)
    assert gsd == pytest.approx(2 * 100 * math.tan(math.radians(35)) / 1920)
    assert gsd * 100 == pytest.approx(7.29, abs=0.01)
    with pytest.raises(ValueError):
        satellite.balloon_gsd_m(0, 70, 1920)


def test_age_days():
    a = datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert satellite.age_days(a, datetime(2026, 10, 11, 12, tzinfo=timezone.utc)) == 10.5


def _summary(tmp_path):
    naip = tmp_path / "naip.png"
    Image.new("RGB", (50, 50), (10, 90, 40)).save(naip)
    s2 = tmp_path / "s2.png"
    Image.new("RGB", (3, 3), (10, 90, 40)).save(s2)
    return {"sources": [
        {"source": "sentinel2", "acquired_at": "2026-10-15T18:53:49+00:00", "age_days": 9.2, "gsd_m": 10.0,
         "cloud_cover": 0.0, "pixel_size_of_a_car_px": 0.45, "png_path": str(s2)},
        {"source": "naip", "acquired_at": "2022-05-19T16:00:00+00:00", "age_days": 1619.3, "gsd_m": 0.6,
         "cloud_cover": None, "pixel_size_of_a_car_px": 7.5, "png_path": str(naip)},
    ]}


def test_compare_row_and_image(tmp_path):
    frame = tmp_path / "frame.png"
    Image.new("RGB", (1920, 1080), (80, 80, 80)).save(frame)
    now = datetime.fromtimestamp(1042.0, timezone.utc)
    obs = {"t": 1000.0, "alt_m": 100, "counts": {"car": 37, "person": 12}}
    row = satellite.compare(frame, obs, _summary(tmp_path), tmp_path / "out", 70, 8, now)
    assert row["balloon"]["age_seconds"] == 42
    assert row["balloon"]["gsd_cm_per_px"] == pytest.approx(7.29, abs=0.01)
    assert row["balloon"]["cars_resolvable"] is True
    assert row["balloon"]["counts"] == {"car": 37, "person": 12}
    s2, naip = row["satellite"]
    assert s2["cars_resolvable"] is False and naip["cars_resolvable"] is False
    assert naip["age_days"] == 1619.3
    assert Image.open(row["png_path"]).width > 1000
    saved = json.loads((tmp_path / "out" / "compare.json").read_text())
    assert saved["assumption"]["min_car_px"] == 8


def test_compare_needs_altitude():
    with pytest.raises(satellite.SatelliteError):
        satellite.build_row((100, 100), {"counts": {}}, {"sources": []}, 70, 8, datetime.now(timezone.utc))


def _online() -> bool:
    try:
        socket.create_connection(("planetarycomputer.microsoft.com", 443), timeout=3).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _online(), reason="offline")
def test_fetch_ocean_beach_smoke(tmp_path):
    summary = satellite.fetch(37.7598, -122.5107, 150, tmp_path)
    assert not summary["errors"], summary["errors"]
    by_source = {s["source"]: s for s in summary["sources"]}
    assert by_source["sentinel2"]["gsd_m"] == pytest.approx(10.0)
    assert by_source["sentinel2"]["cloud_cover"] < satellite.MAX_CLOUD_COVER
    assert by_source["naip"]["gsd_m"] < 1.5
    for s in summary["sources"]:
        assert Image.open(s["png_path"]).size == tuple(s["size_px"])

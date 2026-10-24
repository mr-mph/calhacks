import sys
import urllib.request
import zipfile
from pathlib import Path

import pytest

GROUND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GROUND))

VISDRONE_VAL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/VisDrone2019-DET-val.zip"
REAL_IMAGES = {
    "street_a": "0000280_00001_d_0000612.jpg",
    "street_b": "0000280_00201_d_0000613.jpg",
    "other_scene": "0000244_00001_d_0000001.jpg",
    "cars": "0000271_05801_d_0000401.jpg",
}


@pytest.fixture(scope="session")
def real_images(pytestconfig) -> dict[str, Path]:
    """Real drone frames from the public VisDrone2019 val set, downloaded once into the pytest cache."""
    cache = Path(pytestconfig.cache.mkdir("visdrone"))
    wanted = {key: cache / name for key, name in REAL_IMAGES.items()}
    if all(p.is_file() for p in wanted.values()):
        return wanted
    archive = cache / "val.zip"
    try:
        if not archive.is_file():
            urllib.request.urlretrieve(VISDRONE_VAL, archive)
        with zipfile.ZipFile(archive) as zf:
            for path in wanted.values():
                path.write_bytes(zf.read(f"VisDrone2019-DET-val/images/{path.name}"))
    except OSError as e:
        pytest.skip(f"VisDrone val images unavailable: {e}")
    archive.unlink()
    return wanted


@pytest.fixture(scope="session")
def detector(pytestconfig):
    """COCO yolo11n, downloaded by ultralytics into the pytest cache on first use."""
    from infer import Detector

    weights = Path(pytestconfig.cache.mkdir("weights")) / "yolo11n.pt"
    try:
        return Detector(str(weights), imgsz=960)
    except Exception as e:
        pytest.skip(f"yolo11n weights unavailable: {e}")

"""Train an oriented-box rip-current detector on RipAID (CC BY 4.0, zenodo.org/records/15082427).

Unzip RipAID_v1.0.0.zip somewhere (default ~/data/ripaid) and run:
    python train_rip.py --prepare-only     # build ground/datasets/ripaid (symlinks, no copies)
    python train_rip.py                    # train yolo11n-obb on it
"""

import argparse
import re
from pathlib import Path

import yaml
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
DATASET = HERE / "datasets" / "ripaid"
RUNS = HERE / "runs"
DEFAULT_SRC = Path.home() / "data" / "ripaid" / "RipAID_v1.0.0"

RIP, DOUBT = "0", "1"
# One camera per beach site is held out, so validation measures cameras the model has never seen.
VAL_CAMERAS = {"clm_s_03", "snb_s_02"}
CAMERA = re.compile(r"^(.*?)_\d{4}-\d{2}-\d{2}")


def camera_of(name: str) -> str:
    m = CAMERA.match(name)
    return m.group(1) if m else name


def rip_lines(label: Path) -> tuple[list[str], bool]:
    """Confident rip boxes, and whether the file had any 'doubt' box."""
    if not label.exists():
        return [], False
    lines = [ln for ln in label.read_text().splitlines() if ln.strip()]
    return [ln for ln in lines if ln.split()[0] == RIP], any(ln.split()[0] == DOUBT for ln in lines)


def link(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists():
        dst.symlink_to(src)


def prepare(src: Path) -> Path:
    images = src / "images" / "default"
    labels = src / f"{src.name}_yolo-obb" / "labels" / "train"
    counts = {"train": 0, "val": 0, "rip_images": 0, "negatives": 0, "skipped_doubt_only": 0}
    for img in sorted(images.glob("*.png")):
        rips, had_doubt = rip_lines(labels / f"{img.stem}.txt")
        # Images whose only boxes are 'doubt' are ambiguous; using them as negatives would teach the wrong thing.
        if not rips and had_doubt:
            counts["skipped_doubt_only"] += 1
            continue
        split = "val" if camera_of(img.stem) in VAL_CAMERAS else "train"
        link(img, DATASET / "images" / split / img.name)
        out = DATASET / "labels" / split / f"{img.stem}.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(rips) + ("\n" if rips else ""))
        counts[split] += 1
        counts["rip_images" if rips else "negatives"] += 1
    cfg = {"path": str(DATASET), "train": "images/train", "val": "images/val", "names": {0: "rip_current"}}
    data = DATASET / "ripaid.yaml"
    data.write_text(yaml.safe_dump(cfg, sort_keys=False))
    print(counts)
    return data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--model", default="yolo11n-obb.pt")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--name", default="ripaid")
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()

    data = prepare(args.src)
    if args.prepare_only:
        return

    model = YOLO(args.model)

    # Ultralytics forces workers=0 on MPS; PNG decode then starves the GPU.
    def restore_workers(trainer) -> None:
        trainer.args.workers = args.workers

    model.add_callback("on_pretrain_routine_start", restore_workers)
    model.train(
        data=str(data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device="mps",
        project=str(RUNS),
        name=args.name,
        exist_ok=True,
        plots=True,
    )


if __name__ == "__main__":
    main()

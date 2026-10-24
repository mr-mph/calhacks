"""Fine-tune YOLO on VisDrone2019-DET (drone view) with datasets kept under ground/datasets/."""

import argparse
from pathlib import Path

import yaml
from ultralytics import YOLO
from ultralytics.utils import ROOT as ULTRALYTICS_ROOT

HERE = Path(__file__).resolve().parent
DATASETS = HERE / "datasets"
RUNS = HERE / "runs"


def visdrone_yaml() -> Path:
    cfg = yaml.safe_load((ULTRALYTICS_ROOT / "cfg/datasets/VisDrone.yaml").read_text())
    cfg["path"] = str(DATASETS / "VisDrone")
    out = DATASETS / "VisDrone.yaml"
    DATASETS.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="yolo11n.pt")
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--fraction", type=float, default=1.0)
    ap.add_argument("--name", default="visdrone")
    ap.add_argument("--download-only", action="store_true")
    args = ap.parse_args()

    data = visdrone_yaml()
    if args.download_only:
        from ultralytics.data.utils import check_det_dataset

        check_det_dataset(str(data), autodownload=True)
        return

    model = YOLO(args.model)

    # Ultralytics forces workers=0 on MPS; JPEG decode + mosaic then starves the GPU on VisDrone's 2000px images.
    def restore_workers(trainer) -> None:
        trainer.args.workers = args.workers

    model.add_callback("on_pretrain_routine_start", restore_workers)
    model.train(
        data=str(data),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        fraction=args.fraction,
        device="mps",
        project=str(RUNS),
        name=args.name,
        exist_ok=True,
        plots=True,
    )


if __name__ == "__main__":
    main()

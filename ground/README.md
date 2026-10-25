# Ground station detector

Laptop-side code that finds cars and people in the balloon's downward stills and decides which parking spaces are
taken. Nothing here runs on the Pi; `pi/` stays stdlib + apt only.

| File | What it does |
|---|---|
| `train.py` | Fine-tunes YOLO11n on VisDrone2019-DET (real drone footage), datasets kept in `ground/datasets/` |
| `detect.py` | Runs the model on a still, a folder of stills, or a snapshot URL and prints one JSON line per frame |
| `parking.py` | Turns car detections into per-space occupied/free using polygons from a spaces JSON file |
| `examples/visdrone_val_spaces.json` | 12 spaces drawn on the real VisDrone val frame `0000129_02411_d_0000138.jpg` (1920x1080, top-down) |

## Setup

```bash
cd ground
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Tested with Python 3.14.8 on an Apple M5 Pro (24 GB, MPS). `requirements.txt` pins ultralytics 8.4.173 and torch 2.14.1.

## Training

Dataset: VisDrone2019-DET, 6,471 train and 548 val images from drones over Chinese cities, 10 classes
(pedestrian, people, bicycle, car, van, truck, tricycle, awning-tricycle, bus, motor). `train.py` copies the
Ultralytics `VisDrone.yaml`, points it at `ground/datasets/VisDrone`, and Ultralytics downloads and converts it
(about 2 GB) on first use. Start weights: the COCO-pretrained `yolo11n.pt`.

The run in progress was started with:

```bash
cd ground
PYTHONUNBUFFERED=1 nohup .venv/bin/python train.py --epochs 50 --imgsz 640 --batch 16 --workers 8 --name visdrone \
  > runs/train.log 2>&1 &
```

- Output: `runs/visdrone/` (`weights/best.pt`, `results.csv`, plots). Log: `runs/train.log`.
- Speed on the M5 Pro: epoch 1 took 197 s including validation, so 50 epochs is about 2.75 h.
- Ultralytics forces 0 dataloader workers on MPS; `train.py` turns them back on (8), which gave about 15% more
  throughput on VisDrone's large JPEGs. Batch 32 was no faster per image than batch 16.
- Why 640: VisDrone frames are about 2000 px wide, so training at 640 shrinks people to roughly the 7-11 px they
  measure in a native 1080p balloon frame at 60-100 m. Run inference at 1280 or more (the default) to keep that scale.

Check progress, then evaluate when it finishes:

```bash
tail -c 2000 runs/train.log | tr '\r' '\n' | tail -3
cat runs/visdrone/results.csv
.venv/bin/yolo val model=runs/visdrone/weights/best.pt data=datasets/VisDrone.yaml imgsz=640 device=mps
```

The val command prints per-class mAP50; read the `car` and `pedestrian`/`people` rows.

### Metrics

Final run: 50 epochs, YOLO11n, 640 px, VisDrone2019-DET val (548 images, 38,759 boxes), weights at
`runs/visdrone/weights/best.pt` (5.4 MB, gitignored; copy it from the training Mac). Validation results:

| Class | mAP50 | mAP50-95 |
|---|---|---|
| car | 0.721 | 0.475 |
| van | 0.333 | 0.225 |
| bus | 0.414 | 0.282 |
| truck | 0.282 | 0.180 |
| pedestrian | 0.310 | 0.126 |
| people | 0.226 | 0.077 |
| all 10 classes | 0.293 | 0.166 |

Cars are the reliable class. People are only a few pixels tall from above, so person counts are approximate and the
alerts say so. Inference: 5 ms per image on an M5 Pro (MPS).

### Rip currents

`train_rip.py` trains YOLO11n-OBB on RipAID (CC BY 4.0): 2,186 training images, validated on 289 images from two beach
cameras held out of training (`clm_s_03`, `snb_s_02`), 40 epochs at 960 px. Weights: `runs/ripaid/weights/best.pt`.
Validation: mAP50 0.32, mAP50-95 0.17, precision 0.49, recall 0.27 (66 rips). It finds about a quarter of real rips on
unseen cameras and about half its flags are right, which is why every rip alert goes to a person to confirm.

## Detection

```bash
.venv/bin/python detect.py path/to/still.jpg
.venv/bin/python detect.py /data/balloon/sessions/20261025-101500/stills --save out/annotated
.venv/bin/python detect.py http://balloon.local:8080/camera/snapshot.jpg --loop 2
```

Weights default to `runs/visdrone/weights/best.pt` and fall back to the COCO `yolo11n.pt` if training has not
produced one. Other flags: `--weights`, `--imgsz` (default 1280), `--conf` (default 0.25), `--device`.

Each frame prints one line:

```json
{"frame": "stills/1792875950.951.jpg", "t": 1792875950.951, "size": [1920, 1080],
 "detections": [{"cls": "car", "conf": 0.982, "xyxy": [546.1, 761.2, 605.1, 821.9]}],
 "counts": {"car": 119, "person": 5}}
```

- `t` is the Unix time from the recorder's still filename (`<unix>.jpg`), the file's mtime otherwise, or the fetch
  time for URLs.
- `cls` is the model's own class name. `counts.car` adds up car, van, truck and bus; `counts.person` adds up
  pedestrian and people (VisDrone's label for people sitting or standing still). With the COCO fallback model,
  `person` maps to person.
- `xyxy` is in pixels of the original frame.

On the M5 Pro with MPS, one frame takes about 17 ms at imgsz 640 and 20 ms at 1280, end to end, measured while
training was using the GPU.

## Parking occupancy

```bash
.venv/bin/python parking.py examples/visdrone_val_spaces.json datasets/VisDrone/images/val/0000129_02411_d_0000138.jpg --save out/parking
.venv/bin/python detect.py stills/ | .venv/bin/python parking.py spaces.json --from-jsonl -
```

Spaces file (one per camera setup; draw the polygons on a reference frame from that setup):

```json
{
  "image_size": [1920, 1080],
  "spaces": [
    {"id": "A1", "polygon": [[1557, 562], [1597, 562], [1597, 634], [1557, 634]]}
  ]
}
```

- `polygon` is 3 or more `[x, y]` pixel points, convex (a parking space quad).
- `image_size` is the size of the frame the polygons were drawn on. Frames of another size get the polygons scaled.
  Leave it out to use the coordinates as they are.

A space is occupied when a car-group detection matches it. `--method center` (default, for a top-down camera)
uses the box centre inside the polygon. `--method bottom` uses the bottom-centre, for an oblique camera.
`--method iou` needs box/polygon IoU of at least `--iou-thresh` (default 0.3).

Each frame prints one line:

```json
{"frame": "...0000129_02411_d_0000138.jpg", "t": 1792875950.951,
 "spaces": [{"id": "A1", "occupied": true, "conf": 0.568}, {"id": "A2", "occupied": false, "conf": null}],
 "totals": {"spaces": 12, "occupied": 9, "free": 3, "cars_seen": 119}}
```

`conf` is the confidence of the car that filled the space. `cars_seen` counts every car in the frame, parked or not.

On the example frame with the epoch-1 weights, 9 of 12 spaces came out occupied. By eye, 10 hold a vehicle: the
model missed the covered cart in A7, and A2 and B1 are really empty.

## Not done yet

- Fine-tuning on CARPK / PKLot or our own balloon frames.
- Tiled inference for full-resolution stills (people at 100 m are 7 px).
- Rip-current detection.

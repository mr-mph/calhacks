# Ground station architecture

How the balloon's stills become a parking map, beach alerts, prices and markets. Build every piece against the data
shapes here, so the pieces fit when we join them Saturday night.

```
Pi on the balloon                         Laptop ("ground station", ground/)                   Cloud + phones
-----------------                         ---------------------------------                   --------------
stills/*.jpg every 2 s  --HTTP-->  station: pull newest still --> detector (YOLO, MPS)
telemetry (alt, tilt)   --HTTP-->           |                         |
                                            v                         v
                                     observation record  <-- zones/spaces for this site
                                            |
              +-----------------------------+------------------------------+
              v                             v                              v
     Convex: observations,          Claude agents                  Spacetime: markets
     prices, alerts  --> live map   (alert writer, pricing,         (bets, prices, settlement)
     on phones                       market maker)  --writes-->     --> market page
```

The Pi stays as it is (stdlib and apt only). Everything new runs on the laptop or in the cloud, so a crash there
never stops the recording on the balloon.

## 1. Getting frames from the Pi

- Session and latest sample: `GET http://balloon.local:8080/api/status` and `/api/latest` (altitude, tilt, pressure).
- Stills: sessions are served under `/data/sessions/<session>/`; `stills/index.csv` (columns `file, t_unix,
  altitude_m, pitch_deg, roll_deg, tilt_deg`) lists each still with its
  timestamp and the telemetry at that moment. Poll it every 2 s and fetch only new rows.
- Live single frame: `GET :8080/camera/snapshot.jpg`.
- Replay: point the station at a session folder on disk (from `./fetch.sh`) to run the whole pipeline on a recorded
  flight. The demo must work this way if we can't fly at judging.

## 2. Site file: what each part of the frame means

`ground/sites/<site>.json`, drawn once per tether spot on a reference frame:

```json
{
  "site": "marina-green-lot",
  "reference_frame": "stills/000123.jpg",
  "zones": [
    {"id": "lot-a", "kind": "lot", "polygon": [[x, y], ...], "capacity": 48},
    {"id": "beach", "kind": "beach", "polygon": [[x, y], ...]},
    {"id": "water", "kind": "water", "polygon": [[x, y], ...]},
    {"id": "crosswalk-1", "kind": "crossing", "polygon": [[x, y], ...]}
  ],
  "spaces": [{"id": "A01", "zone": "lot-a", "polygon": [[x, y], ...]}]
}
```

Coordinates are pixels in the reference frame. When the balloon drifts, the station aligns each new frame to the
reference with the same ORB + RANSAC step the Pi's mosaic mapper already uses (`pi/balloon/mapper.py`), then maps
the polygons into it. If alignment fails, the frame is marked low-confidence and skipped by pricing and settlement.

## 3. Observation record (one per processed frame)

```json
{
  "t": 1792880000.0,
  "session": "20261024-153000",
  "frame": "stills/000456.jpg",
  "alt_m": 92.4,
  "tilt_deg": 6.1,
  "model": "yolo11n-visdrone-v1",
  "aligned": true,
  "confidence": 0.86,
  "counts": {"car": 37, "person": 12},
  "zones": {"lot-a": {"car": 37, "occupancy": 0.77}, "beach": {"person": 9}, "water": {"person": 3}},
  "spaces": {"A01": true, "A02": false},
  "rip": [{"xyxy": [x1, y1, x2, y2], "conf": 0.7}]
}
```

`confidence` is a single frame-quality score: alignment success, tilt under ~15 degrees, and stable counts against the
previous few frames. Every consumer must ignore or down-weight frames below 0.5 and say so.

## 4. Consumers

**Beach alerts (Anthropic track).** When the frame shows a rip candidate, or people in the water near one, the alert
writer sends Claude the frame, the detections and the counts. Claude writes a short alert for a patrol member or
parent ("Rip forming north of the stairs, 2 people in the water near it"), states its uncertainty, and never claims to
identify anyone. A person confirms before anything is sent anywhere. Stored in Convex `alerts`.

**Surge pricing (Hyphenate track).** Each lot zone has a price that follows occupancy: base price below 60% full,
rising to a cap as it fills, falling as spaces free up. The pricing agent may change a price at most once every 5
minutes and by at most 25% per step, never outside a floor and ceiling, and holds the price when frame confidence is
low. Every decision is logged with its inputs and reasoning, so a judge can ask "why did the price go up at 4:10?"
and get an answer. Stored in Convex `prices` and `decisions`.

**Prediction markets (Hyphenate + Spacetime).** Binary markets on counts the balloon can settle, such as "40 or more
cars in lot A at 5:00 PM" or "more than 150 people cross crosswalk 1 between 4 and 5 PM". Spacetime holds the
markets, positions and an automated market maker (LMSR), and settles when the station posts the observed value: the
median over the frames within 60 s of the close, with confidence at least 0.5. If there aren't enough good frames,
the market is voided and stakes returned. The market agent proposes markets from the day's history, sets opening
odds, settles them and explains each settlement.

**Live map (Convex track).** One phone-friendly page: the latest frame with free spaces in green, lot prices,
people counts, and alerts. Updates live through Convex queries.

**Satellite comparison (SpaceXAI track).** For the same place, fetch a recent free satellite tile and put it next to
the balloon frame. The balloon's car and person labels are ground truth: show what the satellite can and can't see,
and how stale it is.

## 5. Who builds what

| Piece | Folder | Status |
|---|---|---|
| Detector and parking occupancy | `ground/detect.py`, `ground/parking.py`, `ground/train.py` | Done; VisDrone model trained (mAP50 about 0.30 on held-out val), rip-current model next (`ground/train_rip.py`) |
| Station loop, site files, observation records | `ground/station.py`, `ground/sites/` | Done; `ground/demo.sh` replays a session through everything |
| Claude agents (alerts, pricing, markets) | `ground/agents/` | Done; spend guard, Haiku for text, Sonnet for vision |
| Live map | `web/` (Convex + React) | Live at https://overhead-live.vercel.app (Convex prod) |
| Markets | `market/` (Spacetime module) | Live at https://overhead-market.vercel.app (maincloud `overhead-market`) |
| Jira incidents | `atlassian/` (Forge app "Balloon Patrol") | Installed on one-atlas-dqcx.atlassian.net; 4-alert smoke test passes |
| Satellite comparison | `ground/satellite.py` | After the above |

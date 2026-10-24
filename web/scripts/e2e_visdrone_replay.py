"""End-to-end check of ground/convex_sink.py and the live map with real VisDrone val frames.

Real: the three frames, their detections (ground/detect.py) and space occupancy (ground/parking.py), the parking
spaces drawn on 0000129_02411_d_0000138.jpg (ground/examples/visdrone_val_spaces.json).
Illustrative, and labelled as such in the data it writes: the frame confidence rule, the pricing decisions and their
explanations (a simple rule here, not the pricing agent or Claude), and one TEST alert to exercise Confirm/Dismiss.

    detect.py <dir> --weights <w> > detections.jsonl
    parking.py ground/examples/visdrone_val_spaces.json --from-jsonl <reference frame line> > parking.jsonl
    python web/scripts/e2e_visdrone_replay.py <frames dir> detections.jsonl parking.jsonl
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ground"))

from convex import ConvexClient  # noqa: E402
from convex_sink import CONFIG_PATH, ConvexSink, load_config  # noqa: E402

SESSION = "visdrone-val-replay"
REFERENCE = "0000129_02411_d_0000138.jpg"
ORDER = ["0000253_00001_d_0000001.jpg", "0000271_00001_d_0000374.jpg", REFERENCE]
LOT = "lot-a"
BASE_PRICE, CAP_PRICE, MAX_STEP = 3.0, 9.0, 0.25
FRAME_GAP_S = 3.0


def build_site() -> dict:
    spaces_file = json.loads((ROOT / "ground/examples/visdrone_val_spaces.json").read_text())
    xs = [x for s in spaces_file["spaces"] for x, _ in s["polygon"]]
    ys = [y for s in spaces_file["spaces"] for _, y in s["polygon"]]
    pad = 6
    lot = [[min(xs) - pad, min(ys) - pad], [max(xs), min(ys) - pad], [max(xs), max(ys) + pad], [min(xs) - pad, max(ys) + pad]]
    return {
        "site": "visdrone-val-0000129",
        "name": "VisDrone val 0000129 (test site)",
        "reference_frame": f"visdrone/{REFERENCE}",
        "image_size": spaces_file["image_size"],
        "zones": [{"id": LOT, "kind": "lot", "name": "Lot A", "polygon": lot, "capacity": len(spaces_file["spaces"])}],
        "spaces": [{"id": s["id"], "zone": LOT, "polygon": s["polygon"]} for s in spaces_file["spaces"]],
    }


def observation(det: dict, parking: dict | None, t: float) -> dict:
    name = Path(det["frame"]).name
    aligned = name == REFERENCE
    obs = {
        "t": t,
        "session": SESSION,
        "frame": f"visdrone/{name}",
        "model": "yolo11n-visdrone-epoch4",
        "aligned": aligned,
        # Test rule: the reference frame aligns with the site map, the other two scenes do not.
        "confidence": 0.9 if aligned else 0.3,
        "counts": det["counts"],
    }
    if aligned and parking:
        occupied = {s["id"]: s["occupied"] for s in parking["spaces"]}
        taken = sum(occupied.values())
        obs["spaces"] = occupied
        obs["zones"] = {LOT: {"car": taken, "occupancy": round(taken / len(occupied), 3)}}
    return obs


def decide(obs: dict, price: float) -> dict:
    inputs = {"confidence": obs["confidence"], "aligned": obs["aligned"], "price_before": price}
    if obs["confidence"] < 0.5:
        return {
            "t": obs["t"], "zone": LOT, "action": "hold", "price_before": price, "price_after": price,
            "inputs": inputs, "model": "test-rule",
            "explanation": f"Test rule, not Claude: held at ${price:.2f} because frame confidence "
                           f"{obs['confidence']:.2f} is under 0.5 (frame not aligned to the lot map).",
        }
    occ = obs["zones"][LOT]["occupancy"]
    target = BASE_PRICE if occ < 0.6 else BASE_PRICE + (CAP_PRICE - BASE_PRICE) * (occ - 0.6) / 0.4
    new = round(min(target, price * (1 + MAX_STEP)), 2)
    return {
        "t": obs["t"], "zone": LOT, "action": "raise" if new > price else "lower" if new < price else "hold",
        "price_before": price, "price_after": new,
        "inputs": {**inputs, "occupancy": occ, "spaces_free": sum(1 for v in obs["spaces"].values() if not v)},
        "outputs": {"target_price": round(target, 2), "step_cap": MAX_STEP},
        "model": "test-rule",
        "explanation": f"Test rule, not Claude: lot is {occ:.0%} full (over 60%), so the target is ${target:.2f}; "
                       f"one step may rise at most 25%, so ${price:.2f} becomes ${new:.2f}.",
    }


def main() -> None:
    frames_dir, det_path, parking_path = (Path(a) for a in sys.argv[1:4])
    dets = {Path(d["frame"]).name: d for d in map(json.loads, det_path.read_text().splitlines())}
    parking = {Path(p["frame"]).name: p for p in map(json.loads, parking_path.read_text().splitlines())}

    sink = ConvexSink()
    sink.set_site(build_site())
    price = BASE_PRICE
    for name in ORDER:
        det = dets[name]
        t = time.time()
        obs = observation(det, parking.get(name), t)
        sink.upload_frame(str(frames_dir / name), SESSION, t, tuple(det["size"]), name=obs["frame"])
        sink.write_observations([obs])
        decision = decide(obs, price)
        price = decision["price_after"]
        sink.write_decision(decision)
        if name == "0000271_00001_d_0000374.jpg":
            sink.write_alert({
                "t": t, "session": SESSION, "frame": obs["frame"], "severity": "info", "model": "test",
                "text": f"TEST ALERT, not a real rip current: pipeline check on a city crossing. "
                        f"{det['counts']['person']} people detected in this frame.",
                "uncertainty": "High. This frame has no beach or water; it only exercises Confirm and Dismiss.",
            })
        assert sink.flush(60), "sink did not drain"
        print(f"sent {name}: counts={det['counts']} confidence={obs['confidence']} price={price}")
        time.sleep(FRAME_GAP_S)
    sink.close()
    print("sink totals:", sink.sent)

    client = ConvexClient(load_config(CONFIG_PATH)["url"])
    now = client.query("live:now")
    lots = client.query("live:lots")
    alerts = client.query("live:alerts")
    assert now["frame"]["name"] == f"visdrone/{REFERENCE}", now["frame"]["name"]
    assert now["observation"]["counts"] == {k: float(v) for k, v in dets[REFERENCE]["counts"].items()}
    assert now["site"]["site"] == "visdrone-val-0000129"
    assert any(lot["id"] == LOT and lot["prices"][-1]["price"] == price for lot in lots)
    assert alerts["open"], "expected the TEST alert to be open"
    print("live:now frame", now["frame"]["name"], "counts", now["observation"]["counts"], "OK")


if __name__ == "__main__":
    main()

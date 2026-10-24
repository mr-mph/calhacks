"""Turn one frame's detections into an observation record (docs/architecture.md section 3)."""
import json
import statistics
from collections.abc import Sequence
from pathlib import Path

from align import Alignment, to_reference

ZONE_KINDS = ("lot", "beach", "water", "crossing")
COUNTED = ("car", "person")
MAX_TILT_DEG = 15.0
STABILITY_FRAMES = 5
STABILITY_FLOOR = 5

ALIGN_FAILED = 0.4
TILT_UNKNOWN = 0.9
TILT_EXCEEDED = 0.4
STABILITY_UNKNOWN = 0.9


class SiteError(ValueError):
    pass


def _check_polygon(owner: str, polygon) -> None:
    if not isinstance(polygon, list) or len(polygon) < 3:
        raise SiteError(f"{owner}: polygon needs at least 3 points")
    if not all(isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p) for p in polygon):
        raise SiteError(f"{owner}: polygon points must be [x, y] numbers")


def _check_zone(zone: dict) -> None:
    zid = zone.get("id")
    if not isinstance(zid, str) or not zid:
        raise SiteError("every zone needs a string id")
    if zone.get("kind") not in ZONE_KINDS:
        raise SiteError(f"zone {zid}: kind must be one of {', '.join(ZONE_KINDS)}")
    _check_polygon(f"zone {zid}", zone.get("polygon"))
    capacity = zone.get("capacity")
    if zone["kind"] == "lot" and capacity is not None and (not isinstance(capacity, int) or capacity <= 0):
        raise SiteError(f"zone {zid}: capacity must be a positive integer")


def validate_site(site: dict) -> dict:
    if not isinstance(site.get("site"), str) or not site["site"]:
        raise SiteError("site needs a name in 'site'")
    zones = site.get("zones", [])
    spaces = site.get("spaces", [])
    for zone in zones:
        _check_zone(zone)
    zone_ids = [z["id"] for z in zones]
    if len(set(zone_ids)) != len(zone_ids):
        raise SiteError("zone ids must be unique")
    lots = {z["id"] for z in zones if z["kind"] == "lot"}
    for space in spaces:
        sid = space.get("id")
        if space.get("zone") not in lots:
            raise SiteError(f"space {sid}: zone must be the id of a lot zone")
        _check_polygon(f"space {sid}", space.get("polygon"))
    if len({s["id"] for s in spaces}) != len(spaces):
        raise SiteError("space ids must be unique")
    return site


def load_site(path: str | Path) -> dict:
    with open(path) as f:
        return validate_site(json.load(f))


def resolve_reference(site: dict, site_path: Path, session_dir: Path | None) -> Path | None:
    ref = Path(site.get("reference_frame", ""))
    candidates = [ref, site_path.parent / ref] + ([session_dir / ref] if session_dir else [])
    return next((c for c in candidates if str(ref) and c.is_file()), None)


def point_in_polygon(x: float, y: float, polygon: Sequence[Sequence[float]]) -> bool:
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def center(xyxy: Sequence[float]) -> tuple[float, float]:
    return ((xyxy[0] + xyxy[2]) / 2, (xyxy[1] + xyxy[3]) / 2)


def count_classes(detections: list[dict]) -> dict[str, int]:
    return {cls: sum(1 for d in detections if d["cls"] == cls) for cls in COUNTED}


def _inside(points: list[tuple[str, tuple[float, float]]], cls: str, polygon) -> int:
    return sum(1 for c, (x, y) in points if c == cls and point_in_polygon(x, y, polygon))


def zone_stats(points, site: dict, occupied: dict[str, bool]) -> dict[str, dict]:
    stats = {}
    for zone in site.get("zones", []):
        if zone["kind"] != "lot":
            stats[zone["id"]] = {"person": _inside(points, "person", zone["polygon"])}
            continue
        cars = _inside(points, "car", zone["polygon"])
        zone_spaces = [s["id"] for s in site.get("spaces", []) if s["zone"] == zone["id"]]
        entry = {"car": cars}
        if zone_spaces:
            entry["occupancy"] = round(sum(occupied[s] for s in zone_spaces) / len(zone_spaces), 3)
        elif zone.get("capacity"):
            entry["occupancy"] = round(min(cars / zone["capacity"], 1.0), 3)
        stats[zone["id"]] = entry
    return stats


def space_occupancy(points, site: dict) -> dict[str, bool]:
    return {s["id"]: _inside(points, "car", s["polygon"]) > 0 for s in site.get("spaces", [])}


def alignment_factor(alignment: Alignment | None) -> float:
    if alignment is None:
        return 1.0
    if not alignment.aligned:
        return ALIGN_FAILED
    return 0.7 + 0.3 * min(1.0, alignment.inlier_ratio / 0.5)


def tilt_factor(tilt_deg: float | None) -> float:
    if tilt_deg is None:
        return TILT_UNKNOWN
    if abs(tilt_deg) > MAX_TILT_DEG:
        return TILT_EXCEEDED
    return 1.0 - 0.2 * abs(tilt_deg) / MAX_TILT_DEG


def stability_factor(counts: dict[str, int], history: Sequence[dict[str, int]]) -> float:
    recent = list(history)[-STABILITY_FRAMES:]
    if len(recent) < 2:
        return STABILITY_UNKNOWN
    worst = 0.0
    for cls in COUNTED:
        med = statistics.median(h.get(cls, 0) for h in recent)
        worst = max(worst, abs(counts.get(cls, 0) - med) / max(med, STABILITY_FLOOR))
    return 1.0 - 0.5 * min(worst, 1.0)


def confidence(alignment: Alignment | None, tilt_deg: float | None, counts: dict[str, int],
               history: Sequence[dict[str, int]]) -> float:
    """alignment=None means no site is configured, so alignment neither helps nor hurts."""
    score = alignment_factor(alignment) * tilt_factor(tilt_deg) * stability_factor(counts, history)
    return round(score, 3)


def build_observation(*, t: float, session: str, frame: str, alt_m: float | None, tilt_deg: float | None,
                      model: str, detections: list[dict], site: dict | None, alignment: Alignment | None,
                      history: Sequence[dict[str, int]]) -> dict:
    counts = count_classes(detections)
    aligned = bool(alignment and alignment.aligned)
    zones: dict = {}
    spaces: dict = {}
    if site and aligned:
        centers = to_reference(alignment.transform, [center(d["xyxy"]) for d in detections])
        points = [(d["cls"], c) for d, c in zip(detections, centers)]
        spaces = space_occupancy(points, site)
        zones = zone_stats(points, site, spaces)
    return {
        "t": t,
        "session": session,
        "frame": frame,
        "alt_m": alt_m,
        "tilt_deg": tilt_deg,
        "model": model,
        "aligned": aligned,
        "confidence": confidence(alignment if site else None, tilt_deg, counts, history),
        "counts": counts,
        "zones": zones,
        "spaces": spaces,
        "rip": [{"xyxy": d["xyxy"], "conf": d["conf"]} for d in detections if d["cls"] == "rip"],
    }

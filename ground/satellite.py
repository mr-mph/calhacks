"""Free satellite imagery for a place, and a side-by-side against a balloon frame.

fetch:   Sentinel-2 L2A (10 m) and NAIP (about 0.6 m) from Microsoft Planetary Computer, anonymous, cropped to a
         radius around a point. Writes PNGs and summary.json.
compare: a balloon frame + its observation record (alt_m, counts) against those crops: ground sample distance,
         data age, and whether a car is resolvable at each resolution.

    python satellite.py fetch --lat 37.7598 --lon -122.5107 --radius-m 150 --out out/satellite/ocean-beach
    python satellite.py compare --frame f.jpg --obs obs.json --summary out/satellite/ocean-beach/summary.json --out out/compare
"""
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
CAR_LENGTH_M = 4.5
MAX_CLOUD_COVER = 20
M_PER_DEG_LAT = 111_320.0
DEFAULT_HFOV_DEG = 70.0
# Assumption, not a measurement: a car needs about this many pixels along its length to be told from clutter.
DEFAULT_MIN_CAR_PX = 8.0
SEARCH_LIMIT = 20
PANEL_HEIGHT = 480


class SatelliteError(RuntimeError):
    pass


def bbox_from_center(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    """(west, south, east, north) of the square whose half-side is radius_m."""
    if radius_m <= 0:
        raise ValueError("radius_m must be positive")
    if not -90 < lat < 90:
        raise ValueError("lat out of range")
    dlat = radius_m / M_PER_DEG_LAT
    dlon = radius_m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def car_pixels(gsd_m: float) -> float:
    if gsd_m <= 0:
        raise ValueError("gsd_m must be positive")
    return CAR_LENGTH_M / gsd_m


def balloon_gsd_m(alt_m: float, hfov_deg: float, frame_width_px: int) -> float:
    """Metres per pixel of a nadir frame: ground width 2*h*tan(HFOV/2) over the frame width."""
    if alt_m <= 0 or frame_width_px <= 0 or not 0 < hfov_deg < 180:
        raise ValueError("alt_m, frame width and hfov must be positive (hfov under 180)")
    return 2 * alt_m * math.tan(math.radians(hfov_deg) / 2) / frame_width_px


def age_days(acquired: datetime, now: datetime) -> float:
    return (now - acquired).total_seconds() / 86400


def _parse_time(value: str) -> datetime:
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _catalog():
    import planetary_computer
    import pystac_client

    return pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)


def _crop(href: str, bbox: tuple[float, float, float, float], bands: list[int]):
    """Window of a COG covering bbox (lon/lat). Returns (array HxWxC uint8, gsd_m) or None if bbox is not inside it."""
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import Window, from_bounds

    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="1"):
        with rasterio.open(href) as src:
            native = transform_bounds("EPSG:4326", src.crs, *bbox)
            win = from_bounds(*native, transform=src.transform).round_offsets().round_lengths()
            if win.width < 1 or win.height < 1:
                return None
            if not Window(0, 0, src.width, src.height).intersection(win) == win:
                return None
            if src.crs.linear_units not in ("metre", "meter"):
                raise SatelliteError(f"unexpected raster units {src.crs.linear_units}")
            data = src.read(bands, window=win)
            gsd = abs(src.res[0])
    return np.moveaxis(data, 0, -1), gsd


def _fetch_source(catalog, source: str, bbox, out_dir: Path, now: datetime) -> dict:
    if source == "sentinel2":
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            query={"eo:cloud_cover": {"lt": MAX_CLOUD_COVER}},
            sortby=[{"field": "datetime", "direction": "desc"}],
            max_items=SEARCH_LIMIT,
        )
        asset_key, bands = "visual", [1, 2, 3]
    else:
        search = catalog.search(
            collections=["naip"],
            bbox=bbox,
            sortby=[{"field": "datetime", "direction": "desc"}],
            max_items=SEARCH_LIMIT,
        )
        asset_key, bands = "image", [1, 2, 3]
    for item in search.items():
        got = _crop(item.assets[asset_key].href, bbox, bands)
        if got is None:
            continue
        pixels, gsd = got
        if pixels.dtype != np.uint8:
            raise SatelliteError(f"{source}: expected 8-bit imagery, got {pixels.dtype}")
        png = out_dir / f"{source}.png"
        Image.fromarray(pixels).save(png)
        acquired = _parse_time(item.properties["datetime"])
        cloud = item.properties.get("eo:cloud_cover")
        return {
            "source": source,
            "item_id": item.id,
            "acquired_at": acquired.isoformat(),
            "age_days": round(age_days(acquired, now), 1),
            "gsd_m": round(gsd, 3),
            "cloud_cover": cloud,
            "bbox": list(bbox),
            "size_px": [pixels.shape[1], pixels.shape[0]],
            "pixel_size_of_a_car_px": round(car_pixels(gsd), 2),
            "png_path": str(png),
        }
    raise SatelliteError(f"{source}: no scene fully covering the area")


def fetch(lat: float, lon: float, radius_m: float, out_dir: Path, sources=("sentinel2", "naip")) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    bbox = bbox_from_center(lat, lon, radius_m)
    now = datetime.now(timezone.utc)
    catalog = _catalog()
    results, errors = [], {}
    for source in sources:
        try:
            results.append(_fetch_source(catalog, source, bbox, out_dir, now))
        except Exception as e:  # one source failing (NAIP is US only) must not hide the other
            errors[source] = str(e)
    summary = {
        "lat": lat,
        "lon": lon,
        "radius_m": radius_m,
        "fetched_at": now.isoformat(),
        "car_length_m": CAR_LENGTH_M,
        "sources": results,
        "errors": errors,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def _source_view(src: dict, min_car_px: float) -> dict:
    car_px = src["pixel_size_of_a_car_px"]
    return {
        "source": src["source"],
        "gsd_cm_per_px": round(src["gsd_m"] * 100, 1),
        "age_days": src["age_days"],
        "acquired_at": src["acquired_at"],
        "cloud_cover": src["cloud_cover"],
        "car_px": car_px,
        "cars_resolvable": car_px >= min_car_px,
        "png_path": src["png_path"],
    }


def build_row(frame_size: tuple[int, int], obs: dict, summary: dict, hfov_deg: float, min_car_px: float, now: datetime) -> dict:
    alt = obs.get("alt_m")
    if alt is None:
        raise SatelliteError("observation has no alt_m, cannot compute balloon detail")
    gsd = balloon_gsd_m(alt, hfov_deg, frame_size[0])
    car_px = car_pixels(gsd)
    counts = obs.get("counts") or {}
    age_s = None if obs.get("t") is None else round(now.timestamp() - obs["t"], 1)
    return {
        "balloon": {
            "alt_m": alt,
            "hfov_deg": hfov_deg,
            "frame_px": list(frame_size),
            "gsd_cm_per_px": round(gsd * 100, 2),
            "footprint_m": round(gsd * frame_size[0], 1),
            "car_px": round(car_px, 1),
            "cars_resolvable": car_px >= min_car_px,
            "age_seconds": age_s,
            "counts": {"car": counts.get("car"), "person": counts.get("person")},
        },
        "satellite": [_source_view(s, min_car_px) for s in summary["sources"]],
        "assumption": {"min_car_px": min_car_px, "car_length_m": CAR_LENGTH_M},
    }


def _panel(img: Image.Image, label: str) -> Image.Image:
    scale = PANEL_HEIGHT / img.height
    img = img.resize((max(1, round(img.width * scale)), PANEL_HEIGHT), Image.NEAREST)
    bar = 26
    canvas = Image.new("RGB", (img.width, PANEL_HEIGHT + bar), (24, 24, 24))
    canvas.paste(img, (0, bar))
    ImageDraw.Draw(canvas).text((6, 7), label, fill=(240, 240, 240))
    return canvas


def compare(frame: Path, obs: dict, summary: dict, out_dir: Path, hfov_deg: float, min_car_px: float, now: datetime) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    balloon = Image.open(frame).convert("RGB")
    row = build_row(balloon.size, obs, summary, hfov_deg, min_car_px, now)
    b = row["balloon"]
    panels = [_panel(balloon, f"balloon {b['gsd_cm_per_px']} cm/px, {b['age_seconds']} s old")]
    for s in row["satellite"]:
        img = Image.open(s["png_path"]).convert("RGB")
        panels.append(_panel(img, f"{s['source']} {s['gsd_cm_per_px']} cm/px, {s['age_days']} d old"))
    sheet = Image.new("RGB", (sum(p.width for p in panels) + 8 * (len(panels) - 1), panels[0].height), (24, 24, 24))
    x = 0
    for p in panels:
        sheet.paste(p, (x, 0))
        x += p.width + 8
    png = out_dir / "compare.png"
    sheet.save(png)
    row["png_path"] = str(png)
    (out_dir / "compare.json").write_text(json.dumps(row, indent=2) + "\n")
    return row


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="download and crop Sentinel-2 and NAIP")
    f.add_argument("--lat", type=float, required=True)
    f.add_argument("--lon", type=float, required=True)
    f.add_argument("--radius-m", type=float, default=150)
    f.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare", help="balloon frame next to the satellite crops")
    c.add_argument("--frame", type=Path, required=True)
    c.add_argument("--obs", type=Path, required=True, help="observation record JSON (alt_m, counts, t)")
    c.add_argument("--summary", type=Path, required=True, help="summary.json written by fetch")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--hfov-deg", type=float, default=DEFAULT_HFOV_DEG)
    c.add_argument("--min-car-px", type=float, default=DEFAULT_MIN_CAR_PX)
    return p


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    if args.cmd == "fetch":
        result = fetch(args.lat, args.lon, args.radius_m, args.out)
    else:
        result = compare(
            args.frame,
            json.loads(args.obs.read_text()),
            json.loads(args.summary.read_text()),
            args.out,
            args.hfov_deg,
            args.min_car_px,
            datetime.now(timezone.utc),
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

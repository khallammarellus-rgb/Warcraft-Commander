#!/usr/bin/env python3
"""
Detect landmass blobs on the Azeroth master poster and write poster_placement
into config/globe.json for each map region.

The poster is the source of truth for where each land mass sits on the globe.
"""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path

from PIL import Image

# Blob indices for the legacy square PNG (Azeroth Master Reference.png).
REGION_BLOB_LEGACY = {
    "northrend": 0,
    "kalimdor": 1,
    "eastern_kingdoms": 2,
    "dragon_isles": 3,
    "pandaria": 5,
    "broken_isles": 6,
    "kul_tiras": 7,
    "zandalar": 8,
    "maelstrom": 9,
    "kezan": 10,
    "founders_point": 11,
    "tol_barad": 12,
    "mechagon": 13,
    "siren_isle": 15,
    "nazjatar": 16,
    "khaz_algar": 17,
    "wandering_isle": 18,
    "razorwind_shores": 21,
}

# Blob indices for the artistic parchment map (Azeroth Reference 2.jpg).
REGION_BLOB_ARTISTIC = {
    "northrend": 1,
    "kalimdor": 0,
    "eastern_kingdoms": 3,
    "dragon_isles": 5,
    "pandaria": 4,
    "broken_isles": 9,
    "kul_tiras": 14,
    "zandalar": 7,
    # maelstrom: placed via northrend/pandaria midpoint (see apply_maelstrom_midpoint)
    "kezan": 18,
    "founders_point": 2,
    "tol_barad": 19,
    "mechagon": 25,
    "siren_isle": 53,
    "nazjatar": 51,
    "khaz_algar": 13,
    "wandering_isle": 17,
    "razorwind_shores": 24,
}

POSTER_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def is_land_legacy(r: int, g: int, b: int, a: int) -> bool:
    if a < 20:
        return False
    if r < 35 and g < 70 and b < 100 and (r + g + b) < 120:
        return False
    return (r + g + b) > 80 or a > 200


def is_land_artistic(r: int, g: int, b: int, a: int) -> bool:
    if a < 20:
        return False
    if r > 100 and g < 60 and b < 60:
        return False
    chroma = min(r, g) - b
    if chroma > 55 and (r + g) > 220:
        return True
    if chroma > 40 and (r + g) > 300:
        return True
    return False


def poster_style(poster_path: Path, width: int, height: int) -> str:
    name = poster_path.name.lower()
    if "reference 2" in name or "reference2" in name or "azerothreference2" in name:
        return "artistic"
    if max(width, height) >= 2000:
        return "artistic"
    return "legacy"


def detection_params(style: str, width: int, height: int) -> tuple:
    if style == "artistic":
        scale = max(4, min(width, height) // 400)
        margin_frac = 0.06
        min_area = 40
        return is_land_artistic, scale, margin_frac, min_area
    return is_land_legacy, 2, 0.0, 30


def detect_blobs(poster_path: Path, style: str | None = None) -> list[dict]:
    poster = Image.open(poster_path).convert("RGBA")
    width, height = poster.size
    pixels = poster.load()

    if style is None:
        style = poster_style(poster_path, width, height)
    is_land, scale, margin_frac, min_area = detection_params(style, width, height)

    mx = int(width * margin_frac)
    my = int(height * margin_frac)
    small_w = max(1, (width - 2 * mx) // scale)
    small_h = max(1, (height - 2 * my) // scale)

    mask = Image.new("1", (small_w, small_h), 0)
    mask_px = mask.load()
    for y in range(small_h):
        for x in range(small_w):
            r, g, b, a = pixels[mx + x * scale, my + y * scale]
            if is_land(r, g, b, a):
                mask_px[x, y] = 1

    visited: set[tuple[int, int]] = set()
    blobs: list[dict] = []
    for y in range(small_h):
        for x in range(small_w):
            if mask_px[x, y] == 0 or (x, y) in visited:
                continue
            queue = deque([(x, y)])
            visited.add((x, y))
            points: list[tuple[int, int]] = []
            while queue:
                cx, cy = queue.popleft()
                points.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx + dx, cy + dy
                    if (
                        0 <= nx < small_w
                        and 0 <= ny < small_h
                        and mask_px[nx, ny] == 1
                        and (nx, ny) not in visited
                    ):
                        visited.add((nx, ny))
                        queue.append((nx, ny))
            if len(points) < min_area:
                continue

            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            x0 = min(xs) * scale + mx
            y0 = min(ys) * scale + my
            x1 = (max(xs) + 1) * scale + mx
            y1 = (max(ys) + 1) * scale + my
            if (x1 - x0) > width * 0.85 and (y1 - y0) > height * 0.85:
                continue

            blobs.append(
                {
                    "x0": x0,
                    "y0": y0,
                    "x1": x1,
                    "y1": y1,
                    "cx": sum(xs) / len(xs) * scale + mx,
                    "cy": sum(ys) / len(ys) * scale + my,
                    "area": len(points),
                }
            )

    blobs.sort(key=lambda item: -item["area"])
    return blobs


def find_poster(poster_dir: Path, preferred: str | None) -> Path:
    if preferred:
        candidate = poster_dir / preferred
        if candidate.exists():
            return candidate
    for suffix in POSTER_SUFFIXES:
        matches = sorted(poster_dir.glob(f"*{suffix}"))
        matches = [path for path in matches if path.name != ".gitkeep"]
        if matches:
            return matches[0]
    raise SystemExit(f"No poster image found in {poster_dir}")


def layer_center(config: dict, layer_id: str) -> list[float] | None:
    for layer in config.get("layers", []):
        if layer.get("id") != layer_id:
            continue
        placement = layer.get("poster_placement")
        if placement and placement.get("poster_center"):
            return placement["poster_center"]
    return None


def apply_maelstrom_midpoint(config: dict, poster_width: int, poster_height: int) -> list[float] | None:
    """
    Pin the Maelstrom (and Pacific anchor) to the poster midpoint between Northrend and Pandaria.
    """
    northrend = layer_center(config, "northrend")
    pandaria = layer_center(config, "pandaria")
    if not northrend or not pandaria:
        return None

    cx = (float(northrend[0]) + float(pandaria[0])) / 2
    cy = (float(northrend[1]) + float(pandaria[1])) / 2
    half = max(80, int(min(poster_width, poster_height) * 0.045))
    rect = [
        round(cx - half, 1),
        round(cy - half, 1),
        round(cx + half, 1),
        round(cy + half, 1),
    ]
    center = [round(cx, 1), round(cy, 1)]

    for layer in config.get("layers", []):
        if layer.get("id") != "maelstrom":
            continue
        layer["poster_placement"] = {
            "poster_rect": rect,
            "poster_center": center,
            "blob_index": -1,
            "placement_mode": "northrend_pandaria_midpoint",
        }
        break

    return center


def region_blob_map(style: str) -> dict[str, int]:
    if style == "artistic":
        return REGION_BLOB_ARTISTIC
    return REGION_BLOB_LEGACY


def main() -> None:
    parser = argparse.ArgumentParser(description="Derive poster_placement from the Azeroth reference map")
    parser.add_argument(
        "--poster",
        help="Poster filename in 01-raw-export/maps/azeroth/poster (default: config world_poster.file)",
    )
    parser.add_argument("--list-blobs", action="store_true", help="Print detected blobs and exit")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "globe.json"
    poster_dir = project_root / "01-raw-export" / "maps" / "azeroth" / "poster"

    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)

    preferred = args.poster or config.get("world_poster", {}).get("file")
    poster_path = find_poster(poster_dir, preferred)
    poster_file = poster_path.name

    poster = Image.open(poster_path)
    style = poster_style(poster_path, poster.size[0], poster.size[1])
    blobs = detect_blobs(poster_path, style=style)
    print(f"Poster: {poster_path.name} ({poster.size[0]}x{poster.size[1]}, style={style})")
    print(f"Detected {len(blobs)} landmass blobs\n")

    for index, blob in enumerate(blobs):
        width = blob["x1"] - blob["x0"]
        height = blob["y1"] - blob["y0"]
        print(
            f"  blob {index:02d}: area={blob['area']:5d}  "
            f"center=({blob['cx']:.0f},{blob['cy']:.0f})  "
            f"rect=[{blob['x0']:.0f},{blob['y0']:.0f},{blob['x1']:.0f},{blob['y1']:.0f}]  "
            f"size={width:.0f}x{height:.0f}"
        )

    if args.list_blobs:
        return

    region_map = region_blob_map(style)
    print()

    config.setdefault("world_poster", {})
    config["world_poster"].update(
        {
            "file": poster_file,
            "width": poster.size[0],
            "height": poster.size[1],
            "anchor_earth_lon": config.get("anchor", {}).get("earth_lon", -160.0),
            "anchor_earth_lat": config.get("anchor", {}).get("earth_lat", 0.0),
            "span_lon_degrees": config.get("coverage", {}).get("span_lon_degrees", 150.0),
            "span_lat_degrees": config.get("coverage", {}).get("span_lat_degrees", 85.0),
            "description": "Master layout image — landmass positions on this poster define globe placement.",
        }
    )

    for layer in config.get("layers", []):
        layer_id = layer.get("id")
        if layer_id in ("azeroth", "maelstrom"):
            continue
        if layer_id not in region_map:
            continue
        blob_index = region_map[layer_id]
        if blob_index >= len(blobs):
            print(f"[!] {layer_id}: blob {blob_index} missing — skipped")
            continue
        blob = blobs[blob_index]
        rect = [round(blob["x0"], 1), round(blob["y0"], 1), round(blob["x1"], 1), round(blob["y1"], 1)]
        layer["poster_placement"] = {
            "poster_rect": rect,
            "poster_center": [round(blob["cx"], 1), round(blob["cy"], 1)],
            "blob_index": blob_index,
        }
        print(f"  {layer_id:18} -> blob {blob_index:02d}  rect={rect}")

    anchor = apply_maelstrom_midpoint(config, poster.size[0], poster.size[1])
    if anchor:
        maelstrom_layer = next(layer for layer in config.get("layers", []) if layer.get("id") == "maelstrom")
        print(
            f"  {'maelstrom':18} -> midpoint NR/Pandaria  "
            f"rect={maelstrom_layer['poster_placement']['poster_rect']}"
        )

    if anchor:
        config["world_poster"]["anchor_pixel"] = [round(anchor[0]), round(anchor[1])]
        print(f"\nAnchor pixel set to Maelstrom center: {config['world_poster']['anchor_pixel']}")

    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")

    print(f"\nUpdated {config_path}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Build a Google Earth KML superoverlay from wow.export MINIMAP tiles.

MapTiler Engine struggles with large multi-tile grids in the GUI. This script
does the same job: mosaic your map##_##.png tiles into a zoom pyramid and
write a doc.kml that Google Earth Pro can open.

No GDAL required — only Pillow (pip3 install Pillow).

Usage:
    python3 scripts/build_kml_superoverlay.py

Optional:
    python3 scripts/build_kml_superoverlay.py --input 01-raw-export/maps/azeroth/minimap
    python3 scripts/build_kml_superoverlay.py --name Azeroth

Output:
    02-tiles/azeroth/     pyramid PNG tiles (z/x/y.png)
    03-kml/azeroth/doc.kml   open this file in Google Earth Pro
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from globe_placement import (
    layer_by_id,
    layer_earth_bounds,
    layer_overlay_rotation_deg,
    resolve_grid_reference_input,
    resolve_raw_input,
)
from tile_filters import is_empty_ocean_file, is_empty_ocean_tile

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Run: pip3 install Pillow")
    sys.exit(1)

Image.MAX_IMAGE_PIXELS = None  # continent PNGs (e.g. EK 16384×26624) exceed Pillow's default cap

SOURCE_TILE_PX = 512
OUTPUT_TILE_PX = 256
TILE_PATTERN = re.compile(r"map(\d+)_(\d+)\.png$", re.IGNORECASE)
WMO_PATTERN = re.compile(r".*_wmo_minimap\.png$", re.IGNORECASE)
KML_NS = "http://www.opengis.net/kml/2.2"


def find_wmo_minimap(input_dir: Path) -> Path | None:
    matches = sorted(input_dir.rglob("*_wmo_minimap.png"))
    if not matches:
        return None
    return matches[0]


def find_single_map_png(input_dir: Path, layer: dict | None) -> Path | None:
    if not layer:
        return None
    rel = layer.get("single_map_png")
    if not rel:
        return None
    path = input_dir / rel
    return path if path.exists() else None


def load_minimap_tiles(input_dir: Path) -> dict[tuple[int, int], Path]:
    tiles: dict[tuple[int, int], Path] = {}
    for path in input_dir.rglob("map*_*.png"):
        match = TILE_PATTERN.match(path.name)
        if match:
            tiles[(int(match.group(1)), int(match.group(2)))] = path
    return tiles


def mosaic_minimap(input_dir: Path) -> Image.Image | None:
    """Stitch wow.export map##_## tiles into one RGBA image."""
    tiles = load_minimap_tiles(input_dir)
    if not tiles:
        return None
    xs = [x for x, _ in tiles]
    ys = [y for _, y in tiles]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    width = (x_max - x_min + 1) * SOURCE_TILE_PX
    height = (y_max - y_min + 1) * SOURCE_TILE_PX
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for (x, y), path in tiles.items():
        with Image.open(path) as tile:
            rgba = tile.convert("RGBA")
            px = (x - x_min) * SOURCE_TILE_PX
            py = (y - y_min) * SOURCE_TILE_PX
            canvas.alpha_composite(rgba, (px, py))
    return canvas


def prepare_minimap_mosaic_detail_png(
    project_root: Path,
    layer: dict,
    tiles_root: Path,
    *,
    max_long_edge: int,
    globe_config: dict | None,
) -> Path:
    """Build overview_detail.png from minimap tiles (Darkmoon-style close-up)."""
    input_dir = project_root / layer["input"]
    mosaic = mosaic_minimap(input_dir)
    if mosaic is None:
        raise FileNotFoundError(
            f"minimap_mosaic detail tier: no map##_#_ tiles under {input_dir}"
        )
    staging = tiles_root / "_detail_mosaic_src.png"
    tiles_root.mkdir(parents=True, exist_ok=True)
    mosaic.save(staging)
    print(
        f"  Detail mosaic: {len(load_minimap_tiles(input_dir))} tiles "
        f"{mosaic.size[0]}x{mosaic.size[1]}px from {input_dir.name}"
    )
    return prepare_overview_png(
        staging,
        tiles_root,
        tier_id="detail",
        max_long_edge=max_long_edge,
        globe_config=globe_config,
    )


def discover_tiles(input_dir: Path, *, required: bool = True) -> tuple[dict[tuple[int, int], Path], int, int, int, int] | None:
    tiles: dict[tuple[int, int], Path] = {}
    for path in input_dir.rglob("map*_*.png"):
        match = TILE_PATTERN.match(path.name)
        if match:
            tiles[(int(match.group(1)), int(match.group(2)))] = path

    if not tiles:
        if required:
            raise SystemExit(f"No map##_##.png files found under {input_dir}")
        return None

    xs = [x for x, _ in tiles]
    ys = [y for _, y in tiles]
    return tiles, min(xs), max(xs), min(ys), max(ys)


def discover_wmo_source(
    wmo_path: Path,
) -> tuple[dict[tuple[int, int], Path], int, int, int, int, int, int]:
    """Single static WMO minimap — one zoom level, no tile stitching."""
    img = Image.open(wmo_path)
    width, height = img.size
    img.close()
    tiles = {(0, 0): wmo_path}
    return tiles, 0, 0, 0, 0, width, height


def build_wmo_pyramid(wmo_path: Path, tiles_root: Path) -> int:
    """Write one z0 tile from a WMO minimap PNG."""
    img = Image.open(wmo_path).convert("RGBA")
    out_dir = tiles_root / "0" / "0"
    out_dir.mkdir(parents=True, exist_ok=True)
    img.save(out_dir / "0.png")
    print(f"WMO minimap: single tile {img.size[0]}x{img.size[1]} -> z0/0/0.png")
    return 0


def grid_size(min_x: int, max_x: int, min_y: int, max_y: int) -> tuple[int, int, int, int]:
    cols = max_x - min_x + 1
    rows = max_y - min_y + 1
    width = cols * SOURCE_TILE_PX
    height = rows * SOURCE_TILE_PX
    return width, height, cols, rows


def max_zoom(width: int, height: int) -> int:
    return max(
        math.ceil(math.log2(max(1, width / OUTPUT_TILE_PX))),
        math.ceil(math.log2(max(1, height / OUTPUT_TILE_PX))),
    )


def tiles_at_zoom(width: int, height: int, zoom: int, max_z: int) -> tuple[int, int]:
    scale = 2 ** (max_z - zoom)
    nx = math.ceil(width / (OUTPUT_TILE_PX * scale))
    ny = math.ceil(height / (OUTPUT_TILE_PX * scale))
    return max(1, nx), max(1, ny)


def load_source_region(
    tiles: dict[tuple[int, int], Path],
    min_x: int,
    min_y: int,
    gx0: int,
    gy0: int,
    gx1: int,
    gy1: int,
) -> Image.Image:
    """Load a rectangle of global pixels from the source tile grid."""
    region_w = max(1, gx1 - gx0)
    region_h = max(1, gy1 - gy0)
    canvas = Image.new("RGBA", (region_w, region_h), (0, 0, 0, 0))

    start_tx = gx0 // SOURCE_TILE_PX
    end_tx = (max(0, gx1 - 1)) // SOURCE_TILE_PX
    start_ty = gy0 // SOURCE_TILE_PX
    end_ty = (max(0, gy1 - 1)) // SOURCE_TILE_PX

    for ty in range(start_ty, end_ty + 1):
        for tx in range(start_tx, end_tx + 1):
            world_x = min_x + tx
            world_y = min_y + ty
            src_path = tiles.get((world_x, world_y))
            if not src_path:
                continue

            tile = Image.open(src_path).convert("RGBA")
            tile_x0 = tx * SOURCE_TILE_PX
            tile_y0 = ty * SOURCE_TILE_PX

            crop_x0 = max(0, gx0 - tile_x0)
            crop_y0 = max(0, gy0 - tile_y0)
            crop_x1 = min(SOURCE_TILE_PX, gx1 - tile_x0)
            crop_y1 = min(SOURCE_TILE_PX, gy1 - tile_y0)

            if crop_x1 <= crop_x0 or crop_y1 <= crop_y0:
                continue

            fragment = tile.crop((crop_x0, crop_y0, crop_x1, crop_y1))
            paste_x = tile_x0 + crop_x0 - gx0
            paste_y = tile_y0 + crop_y0 - gy0
            canvas.paste(fragment, (paste_x, paste_y))

    return canvas


def render_tile_from_sources(
    tiles: dict[tuple[int, int], Path],
    min_x: int,
    min_y: int,
    width: int,
    height: int,
    zoom: int,
    max_z: int,
    tx: int,
    ty: int,
) -> Image.Image:
    scale = 2 ** (max_z - zoom)
    gx0 = tx * OUTPUT_TILE_PX * scale
    gy0 = ty * OUTPUT_TILE_PX * scale
    gx1 = min(width, gx0 + OUTPUT_TILE_PX * scale)
    gy1 = min(height, gy0 + OUTPUT_TILE_PX * scale)

    region = load_source_region(tiles, min_x, min_y, gx0, gy0, gx1, gy1)
    if region.size != (OUTPUT_TILE_PX, OUTPUT_TILE_PX):
        region = region.resize((OUTPUT_TILE_PX, OUTPUT_TILE_PX), Image.Resampling.LANCZOS)
    return region


def render_tile_from_children(child_paths: list[Path]) -> Image.Image:
    """Downsample four child tiles (or fewer at edges) into one parent tile."""
    canvas = Image.new("RGBA", (OUTPUT_TILE_PX * 2, OUTPUT_TILE_PX * 2), (0, 0, 0, 0))
    positions = [(0, 0), (OUTPUT_TILE_PX, 0), (0, OUTPUT_TILE_PX), (OUTPUT_TILE_PX, OUTPUT_TILE_PX)]
    for path, (px, py) in zip(child_paths, positions):
        if path.exists():
            canvas.paste(Image.open(path).convert("RGBA"), (px, py))
    return canvas.resize((OUTPUT_TILE_PX, OUTPUT_TILE_PX), Image.Resampling.LANCZOS)


MAJOR_LAYER_IDS = frozenset({
    "kalimdor",
    "eastern_kingdoms",
    "northrend",
    "pandaria",
    "broken_isles",
    "dragon_isles",
    "kul_tiras",
    "zandalar",
    "khaz_algar",
    "maelstrom",
    "outland",
    "draenor",
    "shadowlands",
    "emerald_dream",
    "zereth_mortis",
    "mardum",
    "karesh",
    "voidstorm",
})


def merge_variant_config(globe_config: dict, variant: str | None) -> dict:
    cfg = dict(globe_config or {})
    if not variant:
        return cfg
    variant_cfg = (globe_config or {}).get("world_variants", {}).get(variant, {})
    tile_filter = {**cfg.get("tile_filter", {}), **variant_cfg.get("tile_filter", {})}
    cfg["tile_filter"] = tile_filter
    if variant_cfg.get("lod_model"):
        cfg["lod_model"] = variant_cfg["lod_model"]
    if variant_cfg.get("campaign_kml"):
        cfg["campaign_kml"] = variant_cfg["campaign_kml"]
    return cfg


def uses_tactical_lod(globe_config: dict | None) -> bool:
    return (globe_config or {}).get("lod_model") == "tactical_3tier"


def resolve_lod_class(layer: dict | None) -> str:
    if not layer:
        return "major"
    if layer.get("lod_class"):
        return str(layer["lod_class"])
    if layer.get("layer_type") == "subterranean":
        return "subterranean"
    if layer.get("parent_region"):
        return "island"
    if layer.get("id") in MAJOR_LAYER_IDS:
        return "major"
    return "island"


def pyramid_z_for_tier(pyramid_z: int | str, max_z: int) -> int:
    if pyramid_z == "max":
        return max_z
    return max(0, min(int(pyramid_z), max_z))


def lod_overlap_fraction(globe_config: dict | None) -> float:
    return float((globe_config or {}).get("zoom_transition", {}).get("lod_overlap_fraction", 0.12))


def lod_overlap_pad(handoff: int, globe_config: dict | None) -> int:
    return max(1, int(handoff * lod_overlap_fraction(globe_config)))


def apply_lod_overlap(min_px: int, max_px: int, overlap_frac: float) -> tuple[int, int]:
    if max_px < 0:
        pad = max(1, int(min_px * overlap_frac))
        return max(64, min_px - pad), -1
    min_pad = max(1, int(min_px * overlap_frac))
    max_pad = max(1, int(max_px * overlap_frac))
    return max(64, min_px - min_pad), max_px + max_pad


def normalize_lod_plan(
    z_plan: list[tuple[int, tuple[int, int], int]],
    handoff: int,
    globe_config: dict | None,
) -> list[tuple[int, tuple[int, int], int]]:
    """
    Seal adjacent LOD bands — overlapping transitions prevent GE flicker at thresholds.
    """
    if len(z_plan) < 2:
        return z_plan
    pad = lod_overlap_pad(handoff, globe_config)
    sealed: list[tuple[int, tuple[int, int], int]] = [z_plan[0]]
    for z, (mn, mx), draw in z_plan[1:]:
        prev_z, (prev_mn, prev_mx), prev_draw = sealed[-1]
        if prev_mx >= 0:
            if mn > prev_mx + 1:
                sealed[-1] = (prev_z, (prev_mn, prev_mx + (mn - prev_mx - 1)), prev_draw)
            overlap_min = max(64, prev_mx - pad + 1)
            if mn > overlap_min:
                mn = overlap_min
        sealed.append((z, (mn, mx), draw))
    return sealed


def tactical_tier_pixel_band(
    handoff: int,
    min_miles: float,
    max_miles: float,
    globe_config: dict | None,
) -> tuple[int, int]:
    """Convert a display-tier mileage window to KML Lod pixels (farther = fewer pixels)."""
    overlap = float((globe_config or {}).get("zoom_transition", {}).get("lod_overlap_fraction", 0.08))
    # Open-ended toward ground (battle tier): min at max_miles, no upper cap
    if min_miles <= 0:
        min_px = pixels_for_eye_altitude(handoff, max(max_miles, 1.0), globe_config)
        pad = max(1, int(min_px * overlap))
        return max(64, min_px - pad), -1

    far_px = pixels_for_eye_altitude(handoff, max(max_miles, 1.0), globe_config)
    close_px = pixels_for_eye_altitude(handoff, max(min_miles, 1.0), globe_config)
    min_px = min(far_px, close_px)
    max_px = max(far_px, close_px)
    return apply_lod_overlap(min_px, max_px, overlap)


def tactical_display_tiers(
    globe_config: dict | None,
    lod_class: str,
    kml_tier: str,
) -> list[dict]:
    profiles = (globe_config or {}).get("zoom_transition", {}).get("lod_profiles", {})
    profile = profiles.get(lod_class, profiles.get("major", {}))
    tiers = profile.get("display_tiers", [])
    if kml_tier == "overview":
        return [t for t in tiers if t.get("id") == "theater"]
    if kml_tier == "detail":
        return [t for t in tiers if t.get("id") != "theater"]
    return tiers


def tactical_z_emits(
    globe_config: dict | None,
    layer: dict | None,
    kml_tier: str,
    max_z: int,
) -> list[tuple[int, dict]]:
    lod_class = resolve_lod_class(layer)
    emits: list[tuple[int, dict]] = []
    for spec in tactical_display_tiers(globe_config, lod_class, kml_tier):
        z = pyramid_z_for_tier(spec.get("pyramid_z", "max"), max_z)
        emits.append((z, spec))
    return emits


def detail_link_min_lod_pixels_tactical(
    handoff: int,
    globe_config: dict | None,
    layer: dict | None,
) -> int:
    """NetworkLink loads when the first detail tier becomes relevant (farthest detail mileage)."""
    lod_class = resolve_lod_class(layer)
    tiers = tactical_display_tiers(globe_config, lod_class, "detail")
    if not tiers:
        return handoff
    farthest = max(float(t.get("max_miles", 2000)) for t in tiers)
    min_px = pixels_for_eye_altitude(handoff, farthest, globe_config)
    overlap = float((globe_config or {}).get("zoom_transition", {}).get("lod_overlap_fraction", 0.08))
    pad = max(1, int(min_px * overlap))
    return max(64, min_px - pad)


def tile_filter_kwargs(globe_config: dict | None) -> dict:
    cfg = (globe_config or {}).get("tile_filter", {})
    return {
        "uniformity": float(cfg.get("uniformity", 0.92)),
        "min_land_fraction": float(cfg.get("min_land_fraction", 0.003)),
    }


def skip_empty_ocean(globe_config: dict | None) -> tuple[bool, dict]:
    cfg = (globe_config or {}).get("tile_filter", {})
    enabled = bool(cfg.get("skip_empty_ocean", False))
    return enabled, tile_filter_kwargs(globe_config)


def load_globe_config(project_root: Path) -> dict:
    config_path = project_root / "config" / "globe.json"
    if not config_path.exists():
        return {}
    with config_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def compute_earth_bounds(
    width: int,
    height: int,
    min_x: int,
    min_y: int,
    globe_config: dict,
) -> tuple[float, float, float, float]:
    """
    Map mosaic pixels to a region on Earth (not the full globe).
    Anchor: a WoW tile (e.g. Maelstrom) -> Pacific lat/lon from config/globe.json.
    Returns (west, south, east, north).
    """
    anchor = globe_config.get("anchor", {})
    coverage = globe_config.get("coverage", {})

    anchor_tx = int(anchor.get("wow_tile_x", 33))
    anchor_ty = int(anchor.get("wow_tile_y", 30))
    center_lat = float(anchor.get("earth_lat", 0.0))
    center_lon = float(anchor.get("earth_lon", -160.0))
    span_lon = float(coverage.get("span_lon_degrees", 150.0))
    span_lat = float(coverage.get("span_lat_degrees", 85.0))

    # Anchor position inside this mosaic (pixels)
    anchor_px = (anchor_tx - min_x + 0.5) * SOURCE_TILE_PX
    anchor_py = (anchor_ty - min_y + 0.5) * SOURCE_TILE_PX

    west = center_lon - (anchor_px / width) * span_lon
    east = west + span_lon
    north = center_lat + ((height - anchor_py) / height) * span_lat
    south = north - span_lat
    return west, south, east, north


def pixel_rect_to_latlon(
    gx0: int,
    gy0: int,
    gx1: int,
    gy1: int,
    width: int,
    height: int,
    earth_bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Convert a mosaic pixel rectangle to KML north/south/east/west."""
    west, south, east, north = earth_bounds
    u0, u1 = gx0 / width, gx1 / width
    v0, v1 = gy0 / height, gy1 / height

    tile_west = west + (east - west) * u0
    tile_east = west + (east - west) * u1
    tile_north = north - (north - south) * v0
    tile_south = north - (north - south) * v1
    return tile_north, tile_south, tile_east, tile_west


def tile_lat_lon_bounds(
    tx: int,
    ty: int,
    zoom: int,
    max_z: int,
    width: int,
    height: int,
    earth_bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Lat/lon for one pyramid tile using anchored regional bounds."""
    scale = 2 ** (max_z - zoom)
    gx0 = tx * OUTPUT_TILE_PX * scale
    gy0 = ty * OUTPUT_TILE_PX * scale
    gx1 = min(width, gx0 + OUTPUT_TILE_PX * scale)
    gy1 = min(height, gy0 + OUTPUT_TILE_PX * scale)
    return pixel_rect_to_latlon(gx0, gy0, gx1, gy1, width, height, earth_bounds)


def handoff_pixels_for_bounds(
    earth_bounds: tuple[float, float, float, float],
    globe_config: dict | None,
) -> int:
    """
    Convert eye-altitude handoff (miles) to KML Lod pixels for a region's overview tile.

    Used for the single z0 overview (whole-region footprint) and NetworkLink preload.
    Detail pyramid tiles use per-tile LOD (see compute_lod_pixels).
    """
    zoom_cfg = (globe_config or {}).get("zoom_transition", {})
    tiers = zoom_cfg.get("camera_tiers", {})
    handoff_miles = float(tiers.get("detail_start_miles", 2000))
    ref = float(tiers.get("lod_calibration_ref", 72533))

    west, south, east, north = earth_bounds
    span = max(abs(east - west), abs(north - south))
    pixels = int(ref * span / max(handoff_miles, 1.0))
    return max(64, min(pixels, 8192))


def overview_max_lod_pixels(handoff: int, globe_config: dict | None) -> int:
    zoom_cfg = (globe_config or {}).get("zoom_transition", {})
    tiers = zoom_cfg.get("camera_tiers", {})
    factor = float(zoom_cfg.get("overview_max_lod_factor", 1.0))
    detail_start = float(tiers.get("detail_start_miles", 2000))
    visible_until = float(tiers.get("overview_visible_until_miles", detail_start))
    extension = detail_start / max(visible_until, 1.0)
    computed = max(64, int(handoff * extension * factor))
    # Never let overview outlive detail NetworkLink preload — avoids doubled layers at handoff.
    preload = detail_link_min_lod_pixels(handoff, globe_config)
    return min(computed, max(64, preload - 1))


def pixels_for_eye_altitude(handoff: int, eye_alt_miles: float, globe_config: dict | None) -> int:
    """Map region screen pixels to eye altitude using detail_start_miles calibration."""
    tiers = (globe_config or {}).get("zoom_transition", {}).get("camera_tiers", {})
    detail_start = float(tiers.get("detail_start_miles", 2000))
    if eye_alt_miles <= 0:
        return handoff
    return max(1, int(handoff * detail_start / eye_alt_miles))


def overview_visibility_min_pixels(handoff: int, globe_config: dict | None) -> int:
    """Minimum on-screen pixels before any overview tile appears (eye alt at visibility max miles)."""
    zoom_cfg = (globe_config or {}).get("zoom_transition", {})
    tiers = zoom_cfg.get("camera_tiers", {})
    visibility_max = float(
        tiers.get(
            "overview_visibility_max_miles",
            tiers.get("overview_hold_until_miles", 6000),
        )
    )
    min_factor = float(zoom_cfg.get("overview_min_lod_factor", 1.0))
    return max(64, int(pixels_for_eye_altitude(handoff, visibility_max, globe_config) * min_factor))


def overview_lod_boundaries(handoff: int, globe_config: dict | None, top: int) -> list[int]:
    """
    Mileage-calibrated overview LOD breakpoints (z0..ztop).

    Maps appear when the camera is closer than overview_visibility_max_miles (default 6k mi).
    Overview ends at detail_start_miles (default 2k mi). Interior bands are log-spaced between.
    """
    vis_min = overview_visibility_min_pixels(handoff, globe_config)

    if top <= 0:
        return [vis_min, handoff]

    if top == 1:
        mid = max(vis_min + 1, (vis_min + handoff) // 2)
        return [vis_min, mid, handoff]

    bounds = [vis_min]
    ratio = handoff / max(vis_min, 1)
    for level in range(1, top):
        frac = level / top
        bounds.append(max(bounds[-1] + 1, int(vis_min * (ratio**frac))))

    bounds.append(max(bounds[-1] + 1, handoff))
    return bounds


def detail_link_min_lod_pixels(handoff: int, globe_config: dict | None) -> int:
    """Load detail KML before overview unloads — overlap avoids blank frames at handoff."""
    zoom = (globe_config or {}).get("zoom_transition", {})
    pad = lod_overlap_pad(handoff, globe_config)
    factor = float(zoom.get("detail_link_preload_factor", 1.0))
    preload = max(64, handoff - pad)
    if factor >= 1.0:
        return preload
    return max(64, min(preload, int(handoff * factor)))


def vignette_island_lod_plan(
    handoff: int,
    max_z: int,
    layer: dict,
    globe_config: dict | None,
    span_priority: int,
) -> list[tuple[int, tuple[int, int], int]]:
    """
    Two-tier detail for vignette-only islands.

    Bridge z1 preloads under the vignette (lower drawOrder). Max-z takes over with overlap
    before roads_visible_miles (~600 mi) without 1px gap flicker.
    """
    zoom = (globe_config or {}).get("zoom_transition", {})
    pad = lod_overlap_pad(handoff, globe_config)
    cam = zoom.get("camera_tiers", {})
    from_far = float(cam.get("silhouette_visible_from_miles", 10000))
    until = layer_png_detail_handoff_miles(layer, globe_config)
    _, vig_max = png_tier_lod_band(handoff, globe_config, from_far, until)
    roads_miles = float(
        zoom.get("roads_visible_miles", cam.get("intermediate_target_miles", 600))
    )
    roads_px = pixels_for_eye_altitude(handoff, roads_miles, globe_config)
    close_min = max(vig_max - pad + 1, roads_px - pad)

    bridge_min = max(64, vig_max - pad + 1)
    bridge_max = close_min + pad
    max_z_min = max(64, close_min - pad)

    bridge_draw = max(0, span_priority - 1)
    sharp_draw = 100 + max_z + span_priority
    return normalize_lod_plan(
        [
            (1, (bridge_min, bridge_max), bridge_draw),
            (max_z, (max_z_min, -1), sharp_draw),
        ],
        handoff,
        globe_config,
    )


def detail_link_min_lod_pixels_for_layer(
    handoff: int,
    layer: dict | None,
    globe_config: dict | None,
) -> int:
    """NetworkLink preload threshold aligned to this layer's first detail overlay band."""
    if layer and is_vignette_only_overview(layer):
        zoom = (globe_config or {}).get("zoom_transition", {})
        cam = zoom.get("camera_tiers", {})
        from_far = float(cam.get("silhouette_visible_from_miles", 10000))
        until = layer_png_detail_handoff_miles(layer, globe_config)
        _, vig_max = png_tier_lod_band(handoff, globe_config, from_far, until)
        pad = lod_overlap_pad(handoff, globe_config)
        preload = max(64, vig_max - pad + 1 - pad)
        factor = float(zoom.get("detail_link_preload_factor", 1.0))
        if factor >= 1.0:
            return preload
        return max(64, min(preload, int(preload * factor)))
    return detail_link_min_lod_pixels(handoff, globe_config)


def detail_emit_levels(layer: dict | None, max_z: int, tier: str) -> list[int] | None:
    """Optional per-layer pyramid z levels to emit in the detail tier (e.g. [7] = max zoom only)."""
    if tier != "detail" or not layer:
        return None
    raw = layer.get("detail_emit_z")
    if not raw:
        return None
    levels = sorted({max(1, min(int(z), max_z)) for z in raw})
    return levels or None


def filtered_detail_z_plan(
    emit_levels: list[int],
    max_z: int,
    globe_config: dict | None,
    handoff: int,
    layer: dict | None = None,
) -> list[tuple[int, tuple[int, int], int]]:
    """LOD plan for a subset of detail pyramid levels — avoids multi-step clipping on sparse grids."""
    plan: list[tuple[int, tuple[int, int], int]] = []
    for i, z in enumerate(emit_levels):
        if len(emit_levels) == 1:
            plan.append((z, (handoff + 1, -1), 100 + z))
            continue
        min_lod, max_lod = compute_lod_pixels(
            z, max_z, globe_config, "detail", handoff=handoff, layer=layer
        )
        if i == 0:
            min_lod = handoff + 1
        if i > 0:
            prev_z = emit_levels[i - 1]
            _, prev_max = compute_lod_pixels(
                prev_z, max_z, globe_config, "detail", handoff=handoff, layer=layer
            )
            min_lod = prev_max + 1
        if i == len(emit_levels) - 1:
            max_lod = -1
        plan.append((z, (min_lod, max_lod), 100 + z))
    return plan


def uses_classic_detail_lod(
    layer: dict | None,
    tier: str,
    globe_config: dict | None = None,
) -> bool:
    """Region-unified LOD bands (not per-tile divisors). Applies to detail and full pyramids."""
    if tier not in ("detail", "full"):
        return False
    if layer and layer.get("detail_lod_model"):
        return layer["detail_lod_model"] == "classic"
    return (globe_config or {}).get("zoom_transition", {}).get("detail_lod_model") == "classic"


def silhouette_z0_lod_band(
    handoff: int,
    globe_config: dict | None,
    *,
    layer: dict | None = None,
) -> tuple[int, int]:
    """
    Fixed-resolution z0 / continent PNG — visible from planet view down toward detail handoff.
    Overlaps detail tier minLod so the map never blanks between overview and pyramid.
    """
    zoom = (globe_config or {}).get("zoom_transition", {})
    tiers = zoom.get("camera_tiers", {})
    overlap = float(zoom.get("lod_overlap_fraction", 0.12))
    from_miles = float(tiers.get("silhouette_visible_from_miles", 10000))
    min_px = max(48, pixels_for_eye_altitude(handoff, from_miles, globe_config))
    until_miles = float(
        tiers.get(
            "continent_overview_until_miles",
            tiers.get("roads_visible_miles", tiers.get("detail_start_miles", 2000)),
        )
    )
    if layer and (layer.get("overview_png") or layer.get("overview_png_tiers")):
        until_miles = layer_png_detail_handoff_miles(layer, globe_config)
    max_px = max(min_px + 1, pixels_for_eye_altitude(handoff, until_miles, globe_config))
    return apply_lod_overlap(min_px, max_px, overlap)


def lod_tier_for_pyramid_z(
    z: int,
    tier: str,
    classic_detail: bool,
) -> str:
    """Full pyramid: z0 silhouette band; z1+ detail bands (region-unified, no per-tile doubling)."""
    if tier == "full" and classic_detail:
        return "silhouette" if z == 0 else "detail"
    if classic_detail:
        return "detail"
    return tier


def region_span_priority(layer: dict | None) -> int:
    """Smaller regions paint above larger neighbors in overlap zones (higher drawOrder)."""
    if not layer:
        return 0
    ep = layer.get("earth_placement") or {}
    span = max(float(ep.get("span_lon", 30)), float(ep.get("span_lat", 30)))
    return max(0, min(99, int(100 - span)))


def resolve_tiles_subdir(
    layer: dict | None,
    variant_cfg: dict,
    raw_root: str | None,
    cli_subdir: str | None,
) -> str | None:
    """Resolve 02-tiles/<subdir>/<layer>/ — false on layer uses 02-tiles/<layer>/ (world_lazy style)."""
    if layer is not None and "tiles_subdir" in layer:
        sub = layer.get("tiles_subdir")
        return sub if sub else None
    if cli_subdir:
        return cli_subdir
    if raw_root:
        return variant_cfg.get("tiles_subdir") or None
    return None


def tile_lod_pixels(min_lod: int, max_lod: int, nx: int, ny: int) -> tuple[int, int]:
    """
    Scale region-level LOD bands to a single pyramid tile's footprint.

    Google Earth applies minLodPixels/maxLodPixels to each overlay's Region
    bbox. A tile covering 1/N of the region is ~N× smaller on screen, so
    thresholds must be divided by the tile grid extent at that zoom level.
    """
    divisor = max(1, nx, ny)
    tile_min = max(1, min_lod // divisor)
    if max_lod < 0:
        return tile_min, -1
    tile_max = max(tile_min + 1, max_lod // divisor)
    return tile_min, tile_max


def detail_lod_scale(globe_config: dict | None) -> float:
    """
    Scale detail LOD thresholds so higher-res pyramid levels activate earlier.

    Calibrated from eye altitude: tactical_miles / quality_reference_miles looks sharp,
    roads_visible_miles / intermediate_target_miles is softer — scale = reference / intermediate.
    """
    zoom = (globe_config or {}).get("zoom_transition", {})
    tiers = zoom.get("camera_tiers", {})
    reference = float(
        tiers.get("tactical_miles", tiers.get("quality_reference_miles", 152))
    )
    intermediate = float(
        tiers.get("roads_visible_miles", tiers.get("intermediate_target_miles", 350))
    )
    if intermediate <= 0:
        return 1.0
    return max(0.2, min(1.0, reference / intermediate))


def scale_lod_band(min_lod: int, max_lod: int, scale: float) -> tuple[int, int]:
    min_scaled = max(1, int(min_lod * scale))
    if max_lod < 0:
        return min_scaled, -1
    max_scaled = max(min_scaled + 1, int(max_lod * scale) + 1)
    return min_scaled, max_scaled


def compute_lod_pixels(
    z: int,
    max_z: int,
    globe_config: dict | None,
    tier: str,
    handoff: int | None = None,
    layer: dict | None = None,
) -> tuple[int, int]:
    """
    Contiguous LOD bands — exactly one pyramid level visible at any screen size.

    tier overview: z0 only, visible when zoomed out (1 .. handoff)
    tier detail:   z>=1, visible when zoomed in (handoff .. inf)
    tier full:     entire pyramid without split (legacy single-file merge)
    """
    if handoff is None:
        handoff = int((globe_config or {}).get("zoom_transition", {}).get("overview_handoff_lod_pixels", 512))

    if tier == "silhouette":
        if z == 0:
            return silhouette_z0_lod_band(handoff, globe_config, layer=layer)
        return compute_lod_pixels(z, max_z, globe_config, "detail", handoff=handoff, layer=layer)

    if tier == "overview":
        overview_levels = int((globe_config or {}).get("zoom_transition", {}).get("overview_zoom_levels", 2))
        top = min(max_z, max(0, overview_levels))
        if z == 0 and (globe_config or {}).get("zoom_transition", {}).get("camera_tiers", {}).get(
            "silhouette_visible_from_miles"
        ):
            return silhouette_z0_lod_band(handoff, globe_config, layer=layer)
        bounds = overview_lod_boundaries(handoff, globe_config, top)
        if top <= 0:
            if z == 0:
                return (bounds[0], max(bounds[0] + 1, handoff - 1))
            return (bounds[0], max(bounds[0] + 1, handoff - 1))
        if z == 0:
            return (bounds[0], bounds[1])
        if z == top:
            min_lod = bounds[z] + 1 if z < len(bounds) - 1 else bounds[-2] + 1
            return (min_lod, bounds[-1])
        min_lod = bounds[z] + (0 if z == 1 else 1)
        max_lod = bounds[z + 1]
        return (min_lod, max_lod)

    if tier == "detail":
        lod_scale = detail_lod_scale(globe_config)
        overlap = float((globe_config or {}).get("zoom_transition", {}).get("lod_overlap_fraction", 0.12))
        overlap_pad = max(1, int(handoff * overlap))
        z1_min, z1_max = scale_lod_band(1, OUTPUT_TILE_PX * 2, lod_scale)
        if layer and is_vignette_only_overview(layer):
            cam = (globe_config or {}).get("zoom_transition", {}).get("camera_tiers", {})
            from_far = float(cam.get("silhouette_visible_from_miles", 10000))
            until = layer_png_detail_handoff_miles(layer, globe_config)
            _, vig_max = png_tier_lod_band(handoff, globe_config, from_far, until)
            z1_start = max(64, vig_max - overlap_pad + 1)
        elif layer and layer.get("overview_png_tiers"):
            detail_from_px = pixels_for_eye_altitude(
                handoff,
                layer_png_detail_handoff_miles(layer, globe_config),
                globe_config,
            )
            z1_start = max(64, detail_from_px - overlap_pad)
        else:
            z1_start = max(64, handoff - overlap_pad)
        shift = max(0, z1_start - z1_min)
        if z == 1:
            return (z1_start, z1_max + shift)
        tiers = (globe_config or {}).get("zoom_transition", {}).get("camera_tiers", {})
        roads_miles = float(tiers.get("roads_visible_miles", tiers.get("intermediate_target_miles", 600)))
        tactical_miles = float(tiers.get("tactical_miles", tiers.get("quality_reference_miles", 150)))
        roads_px = pixels_for_eye_altitude(handoff, roads_miles, globe_config)
        tactical_px = pixels_for_eye_altitude(handoff, tactical_miles, globe_config)
        if z == max_z:
            prev_min, prev_max = compute_lod_pixels(
                max_z - 1, max_z, globe_config, tier, handoff=handoff, layer=layer
            )
            return (max(prev_max + 1, tactical_px - overlap_pad), -1)
        prev_min, prev_max = compute_lod_pixels(
            z - 1, max_z, globe_config, tier, handoff=handoff, layer=layer
        )
        _, band_max = scale_lod_band(
            OUTPUT_TILE_PX * (2 ** (z - 1)),
            OUTPUT_TILE_PX * (2 ** z),
            lod_scale,
        )
        min_lod = prev_max + 1
        max_lod = band_max + shift
        if z == max_z - 1:
            min_lod = max(min_lod, roads_px - overlap_pad)
            max_lod = max(max_lod, tactical_px + overlap_pad)
        return (min_lod, max_lod)

    # full — classic doubling chain (no duplicate gaps)
    if z == max_z:
        return (OUTPUT_TILE_PX // 2, -1)
    if z == 0:
        return (1, OUTPUT_TILE_PX)
    return (OUTPUT_TILE_PX * (2 ** (z - 1)), OUTPUT_TILE_PX * (2 ** z))


def tile_png_href(
    kml_path: Path,
    tiles_root: Path,
    z: int,
    tx: int,
    ty: int,
) -> str:
    """Href from a region KML file to its pyramid PNG (correct depth for NetworkLink detail)."""
    png_path = (tiles_root / str(z) / str(tx) / f"{ty}.png").resolve()
    return Path(os.path.relpath(png_path, kml_path.parent.resolve())).as_posix()


def asset_href(kml_path: Path, asset_path: Path) -> str:
    """Href from a region KML file to an arbitrary project asset."""
    return Path(os.path.relpath(asset_path.resolve(), kml_path.parent.resolve())).as_posix()


GE_MAX_TEXTURE_PX = 16384


def resolve_overview_png_tiers(
    layer: dict,
    globe_config: dict | None,
) -> list[dict] | None:
    """
    Optional multi-PNG overview stack: planet (low-res) → theater (mid-res) → detail tiles.
    Each tier may set its own ``file``; otherwise the shared ``source`` / ``overview_png`` is used.
    """
    cfg = layer.get("overview_png_tiers")
    if not cfg:
        return None
    default_source = cfg.get("source") or layer.get("overview_png")

    def tier_section(key: str) -> dict:
        section = cfg.get(key)
        return section if isinstance(section, dict) else {}

    cam = (globe_config or {}).get("zoom_transition", {}).get("camera_tiers", {})
    from_far = float(cam.get("silhouette_visible_from_miles", 10000))
    planet_until = float(
        tier_section("planet").get(
            "visible_until_miles",
            cam.get("planet_overview_until_miles", 4500),
        )
    )
    theater_from_default = float(
        cam.get("detail_start_miles", 2000),
    )
    theater_until_default = float(
        (globe_config or {})
        .get("zoom_transition", {})
        .get("roads_visible_miles", cam.get("intermediate_target_miles", 600))
    )
    theater_until = float(
        tier_section("theater").get(
            "visible_until_miles",
            theater_until_default,
        )
    )
    silhouette_until = float(
        tier_section("silhouette").get(
            "visible_until_miles",
            cam.get("silhouette_overview_until_miles", 2000),
        )
    )
    if (
        cfg.get("planet") is False
        and cfg.get("theater") is False
        and layer
        and is_vignette_only_overview(layer)
    ):
        silhouette_until = island_vignette_until_miles(layer, globe_config)
    zoom_cfg = (globe_config or {}).get("zoom_transition", {})
    silhouette_max_edge = int(zoom_cfg.get("silhouette_png_max_long_edge", 400))

    specs: list[dict] = []
    if cfg.get("silhouette") is not False:
        silhouette_cfg = tier_section("silhouette")
        silhouette_source = silhouette_cfg.get("file")
        if not silhouette_source:
            planet_file = tier_section("planet").get("file") or default_source or ""
            if planet_file:
                silhouette_source = (
                    planet_file.replace("/Planet/", "/Silhouette/")
                    .replace("_planet.png", "_silhouette.png")
                )
        if silhouette_source:
            specs.append(
                {
                    "id": "silhouette",
                    "source_rel": silhouette_source,
                    "max_long_edge": int(
                        silhouette_cfg.get("max_long_edge", silhouette_max_edge)
                    ),
                    "visible_from_miles": float(
                        silhouette_cfg.get("visible_from_miles", from_far)
                    ),
                    "visible_until_miles": float(
                        silhouette_cfg.get("visible_until_miles", silhouette_until)
                    ),
                }
            )
    if cfg.get("planet") is not False:
        planet_cfg = tier_section("planet")
        specs.append(
            {
                "id": "planet",
                "source_rel": planet_cfg.get("file") or default_source,
                "max_long_edge": int(planet_cfg.get("max_long_edge", 4096)),
                "visible_from_miles": silhouette_until,
                "visible_until_miles": planet_until,
            }
        )
    if cfg.get("theater") is not False:
        theater_cfg = tier_section("theater")
        specs.append(
            {
                "id": "theater",
                "source_rel": theater_cfg.get("file") or default_source,
                "max_long_edge": int(theater_cfg.get("max_long_edge", 12288)),
                "visible_from_miles": float(
                    theater_cfg.get("visible_from_miles", theater_from_default)
                ),
                "visible_until_miles": theater_until,
            }
        )
    detail_pyramids = layer_detail_pyramids_enabled(layer, globe_config)
    if cfg.get("detail") is not False and not detail_pyramids:
        detail_cfg = tier_section("detail")
        planet_cfg = tier_section("planet")
        detail_source = detail_cfg.get("file") or detail_cfg.get("source")
        if not detail_source:
            planet_file = planet_cfg.get("file") or ""
            if planet_file:
                detail_source = (
                    planet_file.replace("/Planet/", "/Detail/")
                    .replace("_planet.png", "_detail.png")
                )
        close_feet = float(cam.get("overview_png_close_feet", 700))
        close_miles = max(close_feet / 5280.0, 0.01)
        if detail_source:
            if cfg.get("theater") is False and cfg.get("planet") is False:
                detail_from = silhouette_until
            elif cfg.get("theater") is False:
                detail_from = planet_until
            else:
                detail_from = theater_until
            detail_from = float(
                detail_cfg.get("visible_from_miles", detail_from)
            )
            specs.append(
                {
                    "id": "detail",
                    "source_rel": detail_source,
                    "max_long_edge": int(
                        detail_cfg.get(
                            "max_long_edge",
                            (globe_config or {})
                            .get("zoom_transition", {})
                            .get("detail_png_max_long_edge", 8192),
                        )
                    ),
                    "visible_from_miles": detail_from,
                    "visible_until_miles": close_miles,
                    "no_max_lod": True,
                }
            )
    if not specs:
        return None
    return specs


def is_vignette_only_overview(layer: dict | None) -> bool:
    """Mid-zoom vignette PNG only (planet/theater tiers disabled)."""
    if not layer:
        return False
    tiers = layer.get("overview_png_tiers")
    if not tiers:
        return False
    return (
        tiers.get("planet") is False
        and tiers.get("theater") is False
        and tiers.get("silhouette") is not False
    )


def island_vignette_until_miles(layer: dict, globe_config: dict | None) -> float:
    """
    Far-zoom vignette fade for secondary/minor isles.

    Continents use silhouette_overview_until_miles (~2k mi). Small islands share the
    same mileage in pixel space only near 2k mi eye alt, so their vignette vanished
    by ~700 mi while detail had not taken over. Default to roads_visible_miles (~600 mi).
    """
    tiers_cfg = layer.get("overview_png_tiers") or {}
    silhouette = tiers_cfg.get("silhouette")
    if isinstance(silhouette, dict) and silhouette.get("visible_until_miles") is not None:
        return float(silhouette["visible_until_miles"])
    zoom = (globe_config or {}).get("zoom_transition", {})
    cam = zoom.get("camera_tiers", {})
    return float(
        cam.get(
            "island_vignette_until_miles",
            zoom.get("roads_visible_miles", cam.get("intermediate_target_miles", 600)),
        )
    )


def layer_detail_pyramids_enabled(layer: dict, globe_config: dict | None) -> bool:
    if "detail_pyramids_enabled" in layer:
        return bool(layer["detail_pyramids_enabled"])
    return (globe_config or {}).get("zoom_transition", {}).get(
        "detail_pyramids_enabled", True
    )


def layer_png_detail_handoff_miles(layer: dict | None, globe_config: dict | None) -> float:
    """Eye altitude (mi) where PNG overview ends and the tile pyramid begins."""
    if layer:
        tiers_cfg = layer.get("overview_png_tiers") or {}
        if is_vignette_only_overview(layer):
            return island_vignette_until_miles(layer, globe_config)
        theater = tiers_cfg.get("theater") or {}
        if isinstance(theater, dict) and theater.get("visible_until_miles") is not None:
            return float(theater["visible_until_miles"])
        if layer.get("overview_until_miles") is not None:
            return float(layer["overview_until_miles"])
    cam = (globe_config or {}).get("zoom_transition", {}).get("camera_tiers", {})
    return float(
        cam.get(
            "continent_overview_until_miles",
            cam.get("detail_start_miles", 2000),
        )
    )


def png_tier_lod_band(
    handoff: int,
    globe_config: dict | None,
    visible_from_miles: float,
    visible_until_miles: float,
    *,
    overlap_min: bool = False,
) -> tuple[int, int]:
    """
    Mileage-calibrated LOD window for one PNG overview tier.

    ``visible_from_miles`` is the far (zoomed-out) edge; ``visible_until_miles`` is the
    near (zoomed-in) edge. Only the near edge is overlap-padded so tiers do not bleed
    into the band above (e.g. silhouettes must not appear above 10k mi while the Pacific
    vignette is active).
    """
    overlap = lod_overlap_fraction(globe_config)
    min_px = max(48, pixels_for_eye_altitude(handoff, visible_from_miles, globe_config))
    max_px = max(min_px + 1, pixels_for_eye_altitude(handoff, visible_until_miles, globe_config))
    if overlap_min:
        min_px, max_px = apply_lod_overlap(min_px, max_px, overlap)
    else:
        max_pad = max(1, int(max_px * overlap))
        max_px = max_px + max_pad
    return max(64, min_px), max_px


def overview_link_lod_band(
    layer: dict,
    handoff: int,
    globe_config: dict | None,
) -> tuple[int, int | None]:
    """
    Single NetworkLink LOD window for merged overview.kml.

    Spans the farthest tier's visible_from to the nearest tier's drawable band.
    Inner GroundOverlay Regions gate which PNG actually draws; the link only
    needs to preload slightly before the first tier becomes visible.
    """
    specs = resolve_overview_png_tiers(layer, globe_config)
    if not specs:
        return max(48, handoff), None

    farthest = specs[0]
    overlap = lod_overlap_fraction(globe_config)
    min_px, _ = png_tier_lod_band(
        handoff,
        globe_config,
        farthest["visible_from_miles"],
        farthest["visible_until_miles"],
    )
    pad = max(1, int(min_px * overlap))
    link_min = max(48, min_px - pad)

    nearest = specs[-1]
    if nearest.get("no_max_lod"):
        return link_min, None

    if layer and is_vignette_only_overview(layer):
        if layer_detail_pyramids_enabled(layer, globe_config):
            return link_min, None

    _, link_max = png_tier_lod_band(
        handoff,
        globe_config,
        nearest["visible_from_miles"],
        nearest["visible_until_miles"],
    )
    return link_min, link_max


def prepare_overview_png(
    source: Path,
    tiles_root: Path,
    *,
    tier_id: str = "continent",
    max_long_edge: int = GE_MAX_TEXTURE_PX,
    globe_config: dict | None = None,
) -> Path:
    """
    Cache a downscaled continent PNG per tier under 02-tiles/<region>/overview_<tier>.png.
    Google Earth clips textures above ~16384px per side.
    """
    max_long_edge = max(256, min(int(max_long_edge), GE_MAX_TEXTURE_PX))
    tiles_root.mkdir(parents=True, exist_ok=True)
    cached = tiles_root / f"overview_{tier_id}.png"
    if cached.exists() and cached.stat().st_mtime >= source.stat().st_mtime:
        with Image.open(cached) as existing:
            if max(existing.size) <= max_long_edge:
                return cached

    with Image.open(source) as im:
        w, h = im.size
        if max(w, h) > max_long_edge:
            scale = max_long_edge / max(w, h)
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            print(f"  Overview {tier_id}: {w}x{h} → {new_size[0]}x{new_size[1]}")
            im = im.resize(new_size, Image.Resampling.LANCZOS)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        compress = int(
            ((globe_config or {}).get("zoom_transition") or {}).get(
                "overview_png_compress_level", 9
            )
        )
        im.save(cached, optimize=True, compress_level=max(1, min(9, compress)))
        return cached


def write_overview_png_overlay(
    document: ET.Element,
    name: str,
    output_kml: Path,
    overview_png: Path,
    earth_bounds: tuple[float, float, float, float],
    min_lod: int,
    max_lod: int | None,
    draw: int,
    is_subterranean: bool,
    sub_altitude: float | None,
    sub_draw_base: int,
    tier_label: str = "overview",
    rotation_deg: float = 0.0,
) -> None:
    """Single GroundOverlay for planet/theater view using a continent PNG."""
    west, south, east, north = earth_bounds
    overlay = ET.SubElement(document, f"{{{KML_NS}}}GroundOverlay")
    ET.SubElement(overlay, f"{{{KML_NS}}}name").text = f"{name} {tier_label}"
    if is_subterranean:
        draw = sub_draw_base + draw
    ET.SubElement(overlay, f"{{{KML_NS}}}drawOrder").text = str(draw)
    if sub_altitude is not None:
        ET.SubElement(overlay, f"{{{KML_NS}}}altitude").text = f"{sub_altitude:.1f}"
        ET.SubElement(overlay, f"{{{KML_NS}}}altitudeMode").text = "absolute"

    region = ET.SubElement(overlay, f"{{{KML_NS}}}Region")
    box = ET.SubElement(region, f"{{{KML_NS}}}LatLonAltBox")
    ET.SubElement(box, f"{{{KML_NS}}}north").text = f"{north:.8f}"
    ET.SubElement(box, f"{{{KML_NS}}}south").text = f"{south:.8f}"
    ET.SubElement(box, f"{{{KML_NS}}}east").text = f"{east:.8f}"
    ET.SubElement(box, f"{{{KML_NS}}}west").text = f"{west:.8f}"
    lod = ET.SubElement(region, f"{{{KML_NS}}}Lod")
    ET.SubElement(lod, f"{{{KML_NS}}}minLodPixels").text = str(min_lod)
    if max_lod is not None:
        ET.SubElement(lod, f"{{{KML_NS}}}maxLodPixels").text = str(max_lod)

    icon = ET.SubElement(overlay, f"{{{KML_NS}}}Icon")
    ET.SubElement(icon, f"{{{KML_NS}}}href").text = asset_href(output_kml, overview_png)

    latlon = ET.SubElement(overlay, f"{{{KML_NS}}}LatLonBox")
    ET.SubElement(latlon, f"{{{KML_NS}}}north").text = f"{north:.8f}"
    ET.SubElement(latlon, f"{{{KML_NS}}}south").text = f"{south:.8f}"
    ET.SubElement(latlon, f"{{{KML_NS}}}east").text = f"{east:.8f}"
    ET.SubElement(latlon, f"{{{KML_NS}}}west").text = f"{west:.8f}"
    if rotation_deg:
        ET.SubElement(latlon, f"{{{KML_NS}}}rotation").text = f"{rotation_deg:.2f}"


def write_standalone_tier_kml(
    output_kml: Path,
    name: str,
    overview_png: Path,
    earth_bounds: tuple[float, float, float, float],
    min_lod: int,
    max_lod: int | None,
    draw: int,
    tier_label: str,
    *,
    is_subterranean: bool = False,
    sub_altitude: float | None = None,
    sub_draw_base: int = 50,
    rotation_deg: float = 0.0,
) -> None:
    """One GroundOverlay per file — used for tier-split lazy NetworkLinks."""
    kml = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(kml, f"{{{KML_NS}}}Document")
    ET.SubElement(document, f"{{{KML_NS}}}name").text = f"{name} {tier_label}"
    write_overview_png_overlay(
        document,
        name,
        output_kml,
        overview_png,
        earth_bounds,
        min_lod,
        max_lod,
        draw,
        is_subterranean,
        sub_altitude,
        sub_draw_base,
        tier_label=tier_label,
        rotation_deg=rotation_deg,
    )
    tree = ET.ElementTree(kml)
    ET.indent(tree, space="  ")
    output_kml.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_kml, encoding="utf-8", xml_declaration=True)


def write_kml(
    output_kml: Path,
    name: str,
    tiles_root: Path,
    width: int,
    height: int,
    max_z: int,
    earth_bounds: tuple[float, float, float, float],
    globe_config: dict | None = None,
    tier: str = "full",
    project_root: Path | None = None,
    layer: dict | None = None,
) -> None:
    ET.register_namespace("", KML_NS)
    doc = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(doc, f"{{{KML_NS}}}Document")
    ET.SubElement(document, f"{{{KML_NS}}}name").text = name

    # Open centered on the map so zoomed-out view shows Azeroth immediately
    west, south, east, north = earth_bounds
    center_lon = (west + east) / 2
    center_lat = (south + north) / 2
    anchor = (globe_config or {}).get("anchor", {})
    if "earth_lon" in anchor:
        center_lon = float(anchor["earth_lon"])
    if "earth_lat" in anchor:
        center_lat = float(anchor["earth_lat"])

    look_at = ET.SubElement(document, f"{{{KML_NS}}}LookAt")
    ET.SubElement(look_at, f"{{{KML_NS}}}longitude").text = f"{center_lon:.6f}"
    ET.SubElement(look_at, f"{{{KML_NS}}}latitude").text = f"{center_lat:.6f}"
    ET.SubElement(look_at, f"{{{KML_NS}}}altitude").text = "0"
    ET.SubElement(look_at, f"{{{KML_NS}}}range").text = "25000000"
    ET.SubElement(look_at, f"{{{KML_NS}}}tilt").text = "0"
    ET.SubElement(look_at, f"{{{KML_NS}}}heading").text = "0"

    handoff = handoff_pixels_for_bounds(earth_bounds, globe_config)
    overlay_rotation = layer_overlay_rotation_deg(layer)
    filter_ocean, ocean_kwargs = skip_empty_ocean(globe_config)
    skipped_ocean = 0

    sub_cfg = (layer or {}).get("subterranean") or {}
    is_subterranean = (layer or {}).get("layer_type") == "subterranean"
    sub_altitude = float(sub_cfg.get("depth_m", -1500)) if is_subterranean else None
    sub_draw_base = int((globe_config or {}).get("subterranean_defaults", {}).get("draw_order_base", 50))

    tactical = uses_tactical_lod(globe_config)
    z_min = 0
    z_max = max_z
    if tier == "overview":
        overview_levels = int((globe_config or {}).get("zoom_transition", {}).get("overview_zoom_levels", 2))
        z_max = min(max_z, max(0, overview_levels))
    elif tier == "detail":
        z_min = 1

    span_priority = region_span_priority(layer)
    classic_detail = uses_classic_detail_lod(layer, tier, globe_config)

    overview_png_tiers = (
        resolve_overview_png_tiers(layer, globe_config)
        if tier == "overview" and layer
        else None
    )
    overview_png_rel = (layer or {}).get("overview_png") if tier == "overview" else None
    if overview_png_tiers:
        if not project_root:
            raise ValueError("project_root required when layer.overview_png_tiers is set")
        for spec in overview_png_tiers:
            cached = tiles_root / f"overview_{spec['id']}.png"
            source_rel = spec.get("source_rel")
            if source_rel == "minimap_mosaic":
                if not layer:
                    raise ValueError("minimap_mosaic detail tier requires layer config")
                png = prepare_minimap_mosaic_detail_png(
                    project_root,
                    layer,
                    tiles_root,
                    max_long_edge=spec["max_long_edge"],
                    globe_config=globe_config,
                )
            elif source_rel:
                source = (project_root / source_rel).resolve()
                if not source.exists():
                    raise FileNotFoundError(
                        f"overview_png_tiers {spec['id']} source not found: {source}"
                    )
                png = prepare_overview_png(
                    source,
                    tiles_root,
                    tier_id=spec["id"],
                    max_long_edge=spec["max_long_edge"],
                    globe_config=globe_config,
                )
            elif cached.exists():
                png = cached
                print(f"  Overview PNG {spec['id']}: reusing cached {cached.name}")
            else:
                raise FileNotFoundError(
                    f"overview_png_tiers {spec['id']}: no source file and no cached {cached}"
                )
            min_lod, max_lod = png_tier_lod_band(
                handoff,
                globe_config,
                spec["visible_from_miles"],
                spec["visible_until_miles"],
            )
            if (
                spec["id"] == "detail"
                and layer
                and is_vignette_only_overview(layer)
            ):
                sil_spec = next(
                    (s for s in overview_png_tiers if s["id"] == "silhouette"),
                    None,
                )
                if sil_spec:
                    _, vig_max = png_tier_lod_band(
                        handoff,
                        globe_config,
                        sil_spec["visible_from_miles"],
                        sil_spec["visible_until_miles"],
                    )
                    pad = lod_overlap_pad(handoff, globe_config)
                    min_lod = max(64, vig_max - pad + 1)
            tier_draw = span_priority + {
                "silhouette": 0,
                "planet": 1,
                "theater": 2,
                "detail": 3,
            }.get(spec["id"], 0)
            if spec["id"] == "detail" and layer and is_vignette_only_overview(layer):
                tier_draw = max(0, span_priority - 1)
            if spec.get("no_max_lod"):
                max_lod = None
            write_overview_png_overlay(
                document,
                name,
                output_kml,
                png,
                earth_bounds,
                min_lod,
                max_lod,
                tier_draw,
                is_subterranean,
                sub_altitude,
                sub_draw_base,
                tier_label=spec["id"],
                rotation_deg=overlay_rotation,
            )
            max_label = "∞" if max_lod is None else str(max_lod)
            close_feet = (globe_config or {}).get("zoom_transition", {}).get(
                "camera_tiers", {}
            ).get("overview_png_close_feet")
            until = spec["visible_until_miles"]
            if spec["id"] == "detail" and close_feet:
                until_label = f"{until:.3f} mi (~{close_feet} ft)"
            else:
                until_label = f"{until:.0f} mi"
            print(
                f"  Overview PNG {spec['id']}: {spec['visible_from_miles']:.0f}"
                f"–{until_label} (LOD {min_lod}–{max_label}px)"
            )
            if (globe_config or {}).get("zoom_transition", {}).get(
                "overview_tier_lazy_links", True
            ):
                tier_kml = output_kml.parent / f"overview_{spec['id']}.kml"
                write_standalone_tier_kml(
                    tier_kml,
                    name,
                    png,
                    earth_bounds,
                    min_lod,
                    max_lod,
                    tier_draw,
                    spec["id"],
                    is_subterranean=is_subterranean,
                    sub_altitude=sub_altitude,
                    sub_draw_base=sub_draw_base,
                    rotation_deg=overlay_rotation,
                )
    elif overview_png_rel:
        if not project_root:
            raise ValueError("project_root required when layer.overview_png is set")
        overview_png = (project_root / overview_png_rel).resolve()
        if not overview_png.exists():
            raise FileNotFoundError(f"overview_png not found: {overview_png}")
        overview_png = prepare_overview_png(overview_png, tiles_root)
        min_lod, max_lod = compute_lod_pixels(
            0, max_z, globe_config, "overview", handoff=handoff, layer=layer
        )
        write_overview_png_overlay(
            document,
            name,
            output_kml,
            overview_png,
            earth_bounds,
            min_lod,
            max_lod,
            span_priority,
            is_subterranean,
            sub_altitude,
            sub_draw_base,
            rotation_deg=overlay_rotation,
        )
        print(f"  Overview: single PNG ({overview_png_rel})")
    elif tactical:
        z_plan: list[tuple[int, tuple[int, int], int]] = []
        for pyramid_z, spec in tactical_z_emits(globe_config, layer, tier, max_z):
            min_miles = float(spec.get("min_miles", 0))
            max_miles = float(spec.get("max_miles", 2000))
            min_lod, max_lod = tactical_tier_pixel_band(handoff, min_miles, max_miles, globe_config)
            draw = {"theater": 0, "campaign": 104, "battle": 107}.get(spec.get("id", ""), 100 + pyramid_z)
            z_plan.append((pyramid_z, (min_lod, max_lod), draw))
    else:
        emit_levels = detail_emit_levels(layer, max_z, tier)
        if emit_levels:
            z_plan = filtered_detail_z_plan(
                emit_levels, max_z, globe_config, handoff, layer=layer
            )
        elif (
            tier == "detail"
            and layer
            and is_vignette_only_overview(layer)
            and max_z > 1
        ):
            z_plan = vignette_island_lod_plan(
                handoff, max_z, layer, globe_config, span_priority
            )
        else:
            z_plan = []
            for z in range(z_min, z_max + 1):
                lod_tier = lod_tier_for_pyramid_z(z, tier, classic_detail)
                min_lod, max_lod = compute_lod_pixels(
                    z, max_z, globe_config, lod_tier, handoff=handoff, layer=layer
                )
                if tier == "full":
                    draw = z + span_priority
                elif tier == "overview":
                    draw = span_priority
                else:
                    draw = 100 + z + span_priority
                z_plan.append((z, (min_lod, max_lod), draw))
            if tier == "detail" and len(z_plan) > 1:
                z_plan = normalize_lod_plan(z_plan, handoff, globe_config)

    if not overview_png_tiers and not overview_png_rel:
        for pyramid_z, (min_lod, max_lod), draw_base in z_plan:
            nx, ny = tiles_at_zoom(width, height, pyramid_z, max_z)

            for ty in range(ny):
                for tx in range(nx):
                    png_path = tiles_root / str(pyramid_z) / str(tx) / f"{ty}.png"
                    if not png_path.exists():
                        continue
                    if filter_ocean and is_empty_ocean_file(png_path, **ocean_kwargs):
                        skipped_ocean += 1
                        continue

                    north, south, east, west = tile_lat_lon_bounds(
                        tx, ty, pyramid_z, max_z, width, height, earth_bounds
                    )
                    rel_href = tile_png_href(output_kml, tiles_root, pyramid_z, tx, ty)

                    overlay = ET.SubElement(document, f"{{{KML_NS}}}GroundOverlay")
                    ET.SubElement(overlay, f"{{{KML_NS}}}name").text = f"{name} z{pyramid_z} {tx}/{ty}"
                    draw = draw_base
                    if is_subterranean:
                        draw = sub_draw_base + draw
                    ET.SubElement(overlay, f"{{{KML_NS}}}drawOrder").text = str(draw)
                    if sub_altitude is not None:
                        ET.SubElement(overlay, f"{{{KML_NS}}}altitude").text = f"{sub_altitude:.1f}"
                        ET.SubElement(overlay, f"{{{KML_NS}}}altitudeMode").text = "absolute"

                    region = ET.SubElement(overlay, f"{{{KML_NS}}}Region")
                    box = ET.SubElement(region, f"{{{KML_NS}}}LatLonAltBox")
                    ET.SubElement(box, f"{{{KML_NS}}}north").text = f"{north:.8f}"
                    ET.SubElement(box, f"{{{KML_NS}}}south").text = f"{south:.8f}"
                    ET.SubElement(box, f"{{{KML_NS}}}east").text = f"{east:.8f}"
                    ET.SubElement(box, f"{{{KML_NS}}}west").text = f"{west:.8f}"
                    if classic_detail or tier in ("overview", "full"):
                        tile_min, tile_max = min_lod, max_lod
                    else:
                        tile_min, tile_max = tile_lod_pixels(min_lod, max_lod, nx, ny)
                    lod = ET.SubElement(region, f"{{{KML_NS}}}Lod")
                    ET.SubElement(lod, f"{{{KML_NS}}}minLodPixels").text = str(tile_min)
                    ET.SubElement(lod, f"{{{KML_NS}}}maxLodPixels").text = str(tile_max)

                    icon = ET.SubElement(overlay, f"{{{KML_NS}}}Icon")
                    ET.SubElement(icon, f"{{{KML_NS}}}href").text = rel_href

                    latlon = ET.SubElement(overlay, f"{{{KML_NS}}}LatLonBox")
                    ET.SubElement(latlon, f"{{{KML_NS}}}north").text = f"{north:.8f}"
                    ET.SubElement(latlon, f"{{{KML_NS}}}south").text = f"{south:.8f}"
                    ET.SubElement(latlon, f"{{{KML_NS}}}east").text = f"{east:.8f}"
                    ET.SubElement(latlon, f"{{{KML_NS}}}west").text = f"{west:.8f}"

    if skipped_ocean:
        print(f"  Skipped {skipped_ocean} empty-ocean tile(s) in KML")

    tree = ET.ElementTree(doc)
    ET.indent(tree, space="  ")
    output_kml.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_kml, encoding="utf-8", xml_declaration=True)


def build_pyramid(
    tiles: dict[tuple[int, int], Path],
    min_x: int,
    min_y: int,
    width: int,
    height: int,
    tiles_root: Path,
    globe_config: dict | None = None,
) -> int:
    tiles_root.mkdir(parents=True, exist_ok=True)
    max_z = max_zoom(width, height)
    filter_ocean, ocean_kwargs = skip_empty_ocean(globe_config)
    skipped_ocean = 0

    print(f"Source grid: {width}x{height} pixels")
    print(f"Zoom levels: 0 .. {max_z}")

    # Highest detail level — one output tile at a time (low memory)
    nx, ny = tiles_at_zoom(width, height, max_z, max_z)
    total = nx * ny
    print(f"Building zoom {max_z}: {nx} x {ny} = {total} tiles ...")
    done = 0
    t0 = time.time()
    for ty in range(ny):
        for tx in range(nx):
            tile = render_tile_from_sources(tiles, min_x, min_y, width, height, max_z, max_z, tx, ty)
            if filter_ocean and is_empty_ocean_tile(tile, **ocean_kwargs):
                skipped_ocean += 1
                continue
            out_dir = tiles_root / str(max_z) / str(tx)
            out_dir.mkdir(parents=True, exist_ok=True)
            tile.save(out_dir / f"{ty}.png", optimize=True)
            done += 1
            if done % 100 == 0 or done == total:
                elapsed = time.time() - t0
                print(f"  {done}/{total} ({elapsed:.0f}s)")

    # Lower zoom levels from children
    for z in range(max_z - 1, -1, -1):
        cnx, cny = tiles_at_zoom(width, height, z + 1, max_z)
        nx, ny = tiles_at_zoom(width, height, z, max_z)
        print(f"Building zoom {z}: {nx} x {ny} tiles ...")
        for ty in range(ny):
            for tx in range(nx):
                child_paths = []
                for cy in range(2):
                    for cx in range(2):
                        ctx = tx * 2 + cx
                        cty = ty * 2 + cy
                        child_paths.append(tiles_root / str(z + 1) / str(ctx) / f"{cty}.png")
                tile = render_tile_from_children(child_paths)
                if filter_ocean and is_empty_ocean_tile(tile, **ocean_kwargs):
                    skipped_ocean += 1
                    continue
                out_dir = tiles_root / str(z) / str(tx)
                out_dir.mkdir(parents=True, exist_ok=True)
                tile.save(out_dir / f"{ty}.png", optimize=True)

    if skipped_ocean:
        print(f"Skipped {skipped_ocean} empty-ocean tile(s) in pyramid")

    return max_z


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Google Earth KML superoverlay from wow.export minimap tiles")
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Folder with map##_##.png files (default: 01-raw-export/maps/azeroth/minimap)",
    )
    parser.add_argument("--name", default=None, help="Map name used in KML and output folders")
    parser.add_argument(
        "--layer-id",
        default=None,
        help="Build one layer from config/globe.json using poster_placement georeferencing.",
    )
    parser.add_argument(
        "--full-globe",
        action="store_true",
        help="Legacy mode: stretch over entire Earth (-180..180). Default uses config/globe.json anchor.",
    )
    parser.add_argument(
        "--kml-only",
        action="store_true",
        help="Skip tile pyramid rebuild; only regenerate doc.kml (fast, after editing config/globe.json).",
    )
    parser.add_argument(
        "--tier",
        choices=("full", "overview", "detail"),
        default="full",
        help="full=single pyramid; overview=z0 only; detail=z1+ for two-tier world globe",
    )
    parser.add_argument(
        "--variant",
        default=None,
        help="World variant from config world_variants (e.g. world).",
    )
    parser.add_argument(
        "--raw-root",
        default=None,
        help="Alternate raw export folder (e.g. rawfilenoocean). Replaces 01-raw-export in layer paths.",
    )
    parser.add_argument(
        "--tiles-subdir",
        default=None,
        help="Subfolder under 02-tiles/ for pyramid output (e.g. noocean). Used with --raw-root.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    globe_config = merge_variant_config(load_globe_config(project_root), args.variant)

    raw_root = args.raw_root
    if not raw_root and args.variant == "noocean":
        raw_root = globe_config.get("raw_export_noocean", "rawfilenoocean")

    layer = layer_by_id(globe_config, args.layer_id) if args.layer_id else None
    if layer:
        rel_input = layer.get("input", "")
        input_dir = resolve_raw_input(project_root, rel_input, raw_root)
        name = args.name or layer.get("label", layer.get("id", "layer"))
        slug = layer.get("id", name.lower().replace(" ", "_"))
    else:
        input_dir = args.input or (project_root / "01-raw-export" / "maps" / "azeroth" / "minimap")
        name = args.name or "Azeroth"
        slug = name.lower().replace(" ", "_")

    variant_cfg = globe_config.get("world_variants", {}).get(args.variant or "", {})
    tiles_subdir = resolve_tiles_subdir(layer, variant_cfg, raw_root, args.tiles_subdir)
    if tiles_subdir:
        tiles_root = project_root / "02-tiles" / tiles_subdir / slug
    else:
        tiles_root = project_root / "02-tiles" / slug
    variant_dir = ""
    if args.variant:
        variant_dir = variant_cfg.get("region_kml_dir", args.variant)
    kml_base = project_root / "03-kml" / variant_dir if variant_dir else project_root / "03-kml"
    if args.tier == "overview":
        kml_path = kml_base / slug / "overview.kml"
    elif args.tier == "detail":
        kml_path = kml_base / slug / "detail.kml"
    else:
        kml_path = kml_base / slug / "doc.kml"

    if not input_dir.exists():
        raise SystemExit(f"Input folder not found: {input_dir}")

    print(f"Reading tiles from: {input_dir}")
    wmo_path = find_wmo_minimap(input_dir)
    single_map_path = find_single_map_png(input_dir, layer)
    discovered = discover_tiles(input_dir, required=False)
    if discovered:
        source_mode = "tiles"
        tiles, min_x, max_x, min_y, max_y = discovered
        width, height, cols, rows = grid_size(min_x, max_x, min_y, max_y)
        print(f"Found {len(tiles)} source tiles")
        print(f"World tile range: X {min_x}-{max_x}, Y {min_y}-{max_y} ({cols} x {rows})")
    elif (
        layer
        and args.tier == "overview"
        and resolve_overview_png_tiers(layer, globe_config)
        and (
            single_map_path
            or not layer_detail_pyramids_enabled(layer, globe_config)
        )
    ):
        source_mode = "png_only"
        min_x = max_x = min_y = max_y = 0
        cols = rows = 1
        if single_map_path:
            with Image.open(single_map_path) as img:
                width, height = img.size
            tiles = {(0, 0): single_map_path}
            print(
                f"Found single-map PNG: {single_map_path.name} "
                f"({width}x{height}px, overview tiers only)"
            )
        else:
            mosaic = mosaic_minimap(input_dir)
            if mosaic is None:
                raise SystemExit(
                    f"PNG-only overview for {slug}: no single_map_png or minimap tiles in {input_dir}"
                )
            width, height = mosaic.size
            tiles = {}
            print(
                f"Found minimap mosaic for overview tiers "
                f"({width}x{height}px, vignette + detail PNG)"
            )
    elif wmo_path and layer and layer.get("layer_type") == "subterranean":
        source_mode = "wmo"
        tiles, min_x, max_x, min_y, max_y, width, height = discover_wmo_source(wmo_path)
        cols, rows = 1, 1
        print(f"Found WMO minimap: {wmo_path.name} ({width}x{height}px, single overlay)")
    else:
        raise SystemExit(f"No map##_##.png or WMO minimap found under {input_dir}")

    if source_mode == "tiles" and layer:
        use_land_geo_grid = bool(layer.get("earth_placement"))
        ref_input = None
        if not use_land_geo_grid:
            if raw_root:
                ref_input = resolve_raw_input(project_root, layer.get("input", ""), None)
            else:
                ref_input = resolve_grid_reference_input(
                    project_root, layer.get("input", ""), globe_config
                )
            if ref_input and ref_input.exists() and ref_input != input_dir:
                _, ref_min_x, ref_max_x, ref_min_y, ref_max_y = discover_tiles(ref_input)
                width, height, cols, rows = grid_size(ref_min_x, ref_max_x, ref_min_y, ref_max_y)
                min_x, max_x, min_y, max_y = ref_min_x, ref_max_x, ref_min_y, ref_max_y
                print(
                    f"Grid anchored to reference export: X {min_x}-{max_x}, Y {min_y}-{max_y} "
                    f"({cols} x {rows}) — missing cells render as gaps"
                )
        else:
            print(
                "Geo grid: land tile extent from tile source "
                f"(X {min_x}-{max_x}, Y {min_y}-{max_y}) — matches earth_placement bounds"
            )

    if source_mode == "tiles":
        missing = cols * rows - len(tiles)
        if missing:
            print(f"Note: {missing} grid cells are empty (gaps are OK).")

    if args.full_globe:
        earth_bounds = (-180.0, -90.0, 180.0, 90.0)
        print("Georeferencing: full globe (legacy stretch)")
    elif layer and (layer.get("earth_placement") or layer.get("poster_placement")):
        globe_config = {**globe_config, "_poster_placed_layer": True}
        earth_bounds = layer_earth_bounds(layer, globe_config)
        if layer.get("poster_placement"):
            rect = layer["poster_placement"]["poster_rect"]
            print(f"Georeferencing: poster placement ({layer.get('id')})")
            print(f"  Poster rect: {rect}")
        else:
            print(f"Georeferencing: earth_placement ({layer.get('id')})")
        west, south, east, north = earth_bounds
        print(f"  Earth bounds: west={west:.2f} east={east:.2f} south={south:.2f} north={north:.2f}")
    else:
        earth_bounds = compute_earth_bounds(width, height, min_x, min_y, globe_config)
        anchor = globe_config.get("anchor", {})
        print("Georeferencing: anchored (config/globe.json)")
        print(
            f"  Maelstrom: wow tile ({anchor.get('wow_tile_x', 33)}, {anchor.get('wow_tile_y', 30)})"
            f" -> Earth ({anchor.get('earth_lat', 0)}, {anchor.get('earth_lon', -160)})"
        )
        west, south, east, north = earth_bounds
        print(f"  Mosaic spans: west={west:.2f} east={east:.2f} south={south:.2f} north={north:.2f}")

    if source_mode == "png_only":
        max_z = 0
        print("Skipping tile pyramid (PNG overview tiers only)")
    elif source_mode == "wmo":
        max_z = 0
        if args.kml_only:
            if not (tiles_root / "0" / "0" / "0.png").exists():
                raise SystemExit(f"--kml-only requested but WMO tile not found: {tiles_root}")
            print("Skipping pyramid build (--kml-only). Using WMO z0")
        else:
            max_z = build_wmo_pyramid(wmo_path, tiles_root)
    else:
        max_z = max_zoom(width, height)
        if args.kml_only:
            if not tiles_root.exists():
                raise SystemExit(f"--kml-only requested but tiles not found: {tiles_root}")
            print(f"Skipping pyramid build (--kml-only). Using zoom 0..{max_z}")
        else:
            max_z = build_pyramid(tiles, min_x, min_y, width, height, tiles_root, globe_config)

    print(f"Writing KML: {kml_path}")
    write_kml(
        kml_path,
        name,
        tiles_root,
        width,
        height,
        max_z,
        earth_bounds,
        globe_config,
        tier=args.tier,
        project_root=project_root,
        layer=layer,
    )

    print()
    print("=== Done ===")
    print(f"Tiles: {tiles_root}")
    print(f"KML:   {kml_path}")
    print()
    print("Open in Google Earth Pro:")
    print(f"  File -> Open -> {kml_path}")


if __name__ == "__main__":
    main()
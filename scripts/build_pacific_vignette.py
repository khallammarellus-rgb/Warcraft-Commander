#!/usr/bin/env python3
"""
Composite core-10 silhouette PNGs into a single Pacific-hemisphere vignette.

Usage:
    python3 scripts/build_pacific_vignette.py
    python3 scripts/build_pacific_vignette.py --variant wowcommanderalpha
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_kml_superoverlay import (
    KML_NS,
    handoff_pixels_for_bounds,
    png_tier_lod_band,
    write_overview_png_overlay,
)
from globe_placement import (
    layer_by_id,
    layer_earth_bounds,
    layer_overlay_rotation_deg,
    load_globe_config,
)

try:
    from PIL import Image, ImageFilter
except ImportError:
    print("ERROR: Pillow is required. Run: pip3 install Pillow")
    raise SystemExit(1) from None

Image.MAX_IMAGE_PIXELS = None

DEFAULT_CORE_10 = (
    "kalimdor",
    "eastern_kingdoms",
    "northrend",
    "pandaria",
    "broken_isles",
    "dragon_isles",
    "maelstrom",
    "kul_tiras",
    "zandalar",
    "khaz_algar",
)


def silhouette_source_for_layer(layer: dict) -> Path | None:
    tiers = layer.get("overview_png_tiers") or {}
    silhouette_cfg = tiers.get("silhouette") or {}
    rel = silhouette_cfg.get("file")
    if not rel:
        planet_file = (tiers.get("planet") or {}).get("file") or ""
        if planet_file:
            rel = (
                planet_file.replace("/Planet/", "/Silhouette/")
                .replace("_planet.png", "_silhouette.png")
            )
    return Path(rel) if rel else None


def envelope_bounds(
    layers: list[dict],
    config: dict,
    *,
    margin_deg: float = 2.0,
) -> tuple[float, float, float, float]:
    wests: list[float] = []
    souths: list[float] = []
    easts: list[float] = []
    norths: list[float] = []
    for layer in layers:
        w, s, e, n = layer_earth_bounds(layer, config)
        wests.append(w)
        souths.append(s)
        easts.append(e)
        norths.append(n)
    return (
        min(wests) - margin_deg,
        min(souths) - margin_deg,
        max(easts) + margin_deg,
        max(norths) + margin_deg,
    )


def lon_to_x(lon: float, west: float, east: float, width: int) -> float:
    span = east - west
    if span <= 0:
        return 0.0
    return (lon - west) / span * width


def lat_to_y(lat: float, south: float, north: float, height: int) -> float:
    span = north - south
    if span <= 0:
        return 0.0
    return (north - lat) / span * height


def build_composite(
    project_root: Path,
    config: dict,
    core_ids: tuple[str, ...],
    *,
    max_long_edge: int,
) -> tuple[Path, tuple[float, float, float, float]]:
    layers = []
    for layer_id in core_ids:
        layer = layer_by_id(config, layer_id)
        if layer and layer.get("enabled", True):
            layers.append(layer)
    if not layers:
        raise SystemExit("No enabled core regions found for vignette composite.")

    bounds = envelope_bounds(layers, config)
    west, south, east, north = bounds
    lon_span = east - west
    lat_span = north - south
    aspect = lon_span / max(lat_span, 1e-6)
    if aspect >= 1.0:
        width = max_long_edge
        height = max(1, int(round(max_long_edge / aspect)))
    else:
        height = max_long_edge
        width = max(1, int(round(max_long_edge * aspect)))

    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))

    for layer in layers:
        rel = silhouette_source_for_layer(layer)
        if not rel:
            print(f"  [!] skip {layer['id']}: no silhouette source")
            continue
        source = project_root / rel
        if not source.exists():
            print(f"  [!] skip {layer['id']}: missing {source}")
            continue

        w, s, e, n = layer_earth_bounds(layer, config)
        x0 = int(round(lon_to_x(w, west, east, width)))
        x1 = int(round(lon_to_x(e, west, east, width)))
        y0 = int(round(lat_to_y(n, south, north, height)))
        y1 = int(round(lat_to_y(s, south, north, height)))
        box_w = max(1, x1 - x0)
        box_h = max(1, y1 - y0)

        rotation = layer_overlay_rotation_deg(layer)
        with Image.open(source) as im:
            if im.mode != "RGBA":
                im = im.convert("RGBA")
            if rotation:
                im = im.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=False)
            resized = im.resize((box_w, box_h), Image.Resampling.LANCZOS)
            canvas.alpha_composite(resized, (x0, y0))
        print(f"  placed {layer['id']} at {box_w}x{box_h}px")

    # Soft vignette look — slight blur, preserve alpha
    canvas = canvas.filter(ImageFilter.GaussianBlur(radius=0.6))

    export_dir = (
        project_root
        / "01-raw-export/maps/azeroth/Continent PNGs/Vignette"
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / "pacific_vignette.png"

    tiles_dir = project_root / "02-tiles/_shared"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    tiles_path = tiles_dir / "pacific_vignette.png"

    compress = int(
        config.get("zoom_transition", {}).get("overview_png_compress_level", 9)
    )
    for path in (export_path, tiles_path):
        canvas.save(path, optimize=True, compress_level=max(1, min(9, compress)))

    print(f"Wrote {export_path} ({width}x{height})")
    print(f"Wrote {tiles_path}")
    return tiles_path, bounds


def write_vignette_kml(
    output_kml: Path,
    png_path: Path,
    earth_bounds: tuple[float, float, float, float],
    config: dict,
) -> None:
    zoom_cfg = config.get("zoom_transition", {})
    tiers = zoom_cfg.get("camera_tiers", {})
    from_miles = float(tiers.get("vignette_visible_from_miles", 40000))
    until_miles = float(tiers.get("vignette_overview_until_miles", 10000))

    handoff = handoff_pixels_for_bounds(earth_bounds, config)
    min_lod, max_lod = png_tier_lod_band(handoff, config, from_miles, until_miles)

    ET.register_namespace("", KML_NS)
    kml = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(kml, f"{{{KML_NS}}}Document")
    ET.SubElement(document, f"{{{KML_NS}}}name").text = "Azeroth Pacific vignette"

    write_overview_png_overlay(
        document,
        "Azeroth Pacific",
        output_kml,
        png_path,
        earth_bounds,
        min_lod,
        max_lod,
        draw=10,
        is_subterranean=False,
        sub_altitude=None,
        sub_draw_base=0,
        tier_label="vignette",
    )

    output_kml.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(kml).write(
        output_kml,
        encoding="utf-8",
        xml_declaration=True,
    )
    print(f"Wrote {output_kml} (LOD {min_lod}–{max_lod}px, {from_miles:.0f}–{until_miles:.0f} mi)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Pacific hemisphere vignette composite.")
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument("--margin-deg", type=float, default=2.0)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config = load_globe_config(project_root)
    geo = config.get("geographic_placement", {})
    core_ids = tuple(geo.get("core_10_regions", DEFAULT_CORE_10))
    max_edge = int(config.get("zoom_transition", {}).get("vignette_png_max_long_edge", 600))

    print(f"=== Pacific vignette ({len(core_ids)} regions) ===")
    png_path, bounds = build_composite(
        project_root,
        config,
        core_ids,
        max_long_edge=max_edge,
    )

    region_dir = (
        config.get("world_variants", {})
        .get(args.variant, {})
        .get("region_kml_dir", args.variant)
    )
    output_kml = project_root / "03-kml" / region_dir / "pacific_vignette.kml"
    write_vignette_kml(output_kml, png_path, bounds, config)


if __name__ == "__main__":
    main()
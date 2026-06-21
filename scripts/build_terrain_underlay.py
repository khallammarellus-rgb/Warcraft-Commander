#!/usr/bin/env python3
"""
Build a global terrain underlay: real-Earth land mask, transparent ocean.

Hides Google Earth terrain/satellite on continents while leaving GE ocean visible.
Color sampled from config color_reference (blue underlay template tile.png).

Usage:
    python3 scripts/build_terrain_underlay.py
    python3 scripts/build_terrain_underlay.py --variant wowcommanderalpha
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    import shapefile
except ImportError:
    print("ERROR: pyshp required. Run: pip3 install pyshp")
    sys.exit(1)

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("ERROR: Pillow required. Run: pip3 install Pillow")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_kml_superoverlay import GE_MAX_TEXTURE_PX, merge_variant_config
from globe_placement import load_globe_config

KML_NS = "http://www.opengis.net/kml/2.2"
DEFAULT_LAND_URL = "https://naciscdn.org/naturalearth/110m/physical/ne_110m_land.zip"
DEFAULT_COLOR_REF = "04-edited-exports/Underlay/blue underlay template tile.png"
GLOBAL_BOUNDS = (-180.0, -90.0, 180.0, 90.0)


def underlay_config(config: dict) -> dict:
    return config.get("terrain_underlay") or {}


def sample_underlay_color(project_root: Path, cfg: dict) -> tuple[int, int, int, int]:
    rel = cfg.get("color_reference", DEFAULT_COLOR_REF)
    path = project_root / rel
    if not path.exists():
        raise FileNotFoundError(f"Underlay color reference not found: {path}")
    with Image.open(path) as im:
        rgba = im.convert("RGBA").getpixel((0, 0))
    if len(rgba) == 4:
        return rgba
    return (*rgba[:3], 255)


def ensure_land_shapes(project_root: Path, cfg: dict) -> Path:
    cache_dir = project_root / "01-raw-export" / "_earth_reference" / "ne_110m_land"
    shp_path = cache_dir / "ne_110m_land.shp"
    if shp_path.exists():
        return shp_path

    url = cfg.get("land_shape_url", DEFAULT_LAND_URL)
    cache_dir.mkdir(parents=True, exist_ok=True)
    zip_path = cache_dir / "ne_110m_land.zip"
    print(f"Downloading Natural Earth land shapes: {url}")
    result = subprocess.run(
        ["curl", "-fsSL", "-o", str(zip_path), url],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"Download failed: {result.stderr.strip() or result.stdout.strip()}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(cache_dir)
    if not shp_path.exists():
        raise SystemExit(f"Expected shapefile missing after extract: {shp_path}")
    return shp_path


def lonlat_to_pixel(
    lon: float,
    lat: float,
    width: int,
    height: int,
) -> tuple[float, float]:
    x = (lon + 180.0) / 360.0 * width
    y = (90.0 - lat) / 180.0 * height
    return x, y


def rasterize_land_mask(
    shp_path: Path,
    width: int,
    height: int,
    fill: tuple[int, int, int, int],
) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image, "RGBA")
    reader = shapefile.Reader(str(shp_path))

    polygon_types = {shapefile.POLYGON, 3, 5, 15, 18, 31}
    for shape_rec in reader.shapeRecords():
        shape = shape_rec.shape
        if shape.shapeType not in polygon_types:
            continue
        points = shape.points
        parts = list(shape.parts) + [len(points)]
        for idx in range(len(parts) - 1):
            ring = points[parts[idx] : parts[idx + 1]]
            if len(ring) < 3:
                continue
            pixels = [lonlat_to_pixel(lon, lat, width, height) for lon, lat in ring]
            draw.polygon(pixels, fill=fill)

    return image


def fit_texture_size(width: int, height: int) -> tuple[int, int]:
    scale = min(1.0, GE_MAX_TEXTURE_PX / max(width, height))
    if scale >= 1.0:
        return width, height
    return max(1, int(width * scale)), max(1, int(height * scale))


def write_underlay_kml(
    kml_path: Path,
    png_path: Path,
    *,
    draw_order: int,
) -> None:
    west, south, east, north = GLOBAL_BOUNDS
    href = Path(os.path.relpath(png_path.resolve(), kml_path.parent.resolve())).as_posix()

    ET.register_namespace("", KML_NS)
    doc_root = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(doc_root, f"{{{KML_NS}}}Document")
    ET.SubElement(document, f"{{{KML_NS}}}name").text = "Terrain underlay (Earth land mask)"

    overlay = ET.SubElement(document, f"{{{KML_NS}}}GroundOverlay")
    ET.SubElement(overlay, f"{{{KML_NS}}}name").text = "Hide GE terrain on land"
    ET.SubElement(overlay, f"{{{KML_NS}}}drawOrder").text = str(draw_order)
    ET.SubElement(overlay, f"{{{KML_NS}}}color").text = "ffffffff"

    icon = ET.SubElement(overlay, f"{{{KML_NS}}}Icon")
    ET.SubElement(icon, f"{{{KML_NS}}}href").text = href

    latlon = ET.SubElement(overlay, f"{{{KML_NS}}}LatLonBox")
    ET.SubElement(latlon, f"{{{KML_NS}}}north").text = f"{north:.8f}"
    ET.SubElement(latlon, f"{{{KML_NS}}}south").text = f"{south:.8f}"
    ET.SubElement(latlon, f"{{{KML_NS}}}east").text = f"{east:.8f}"
    ET.SubElement(latlon, f"{{{KML_NS}}}west").text = f"{west:.8f}"

    tree = ET.ElementTree(doc_root)
    ET.indent(tree, space="  ")
    kml_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(kml_path, encoding="utf-8", xml_declaration=True)


def build_terrain_underlay(
    project_root: Path,
    config: dict,
    *,
    variant: str | None = None,
) -> Path | None:
    cfg = underlay_config(config)
    if not cfg.get("enabled", False):
        print("Terrain underlay disabled (terrain_underlay.enabled=false)")
        return None

    width = int(cfg.get("width", 8192))
    height = int(cfg.get("height", max(1, width // 2)))
    draw_order = int(cfg.get("draw_order", 0))
    fill = sample_underlay_color(project_root, cfg)
    print(f"Underlay color from template: RGBA{fill}")

    shp_path = ensure_land_shapes(project_root, cfg)
    print(f"Rasterizing land mask {width}x{height} ...")
    mask = rasterize_land_mask(shp_path, width, height, fill)

    out_w, out_h = fit_texture_size(*mask.size)
    if (out_w, out_h) != mask.size:
        print(f"Scaling underlay to {out_w}x{out_h} for Google Earth texture limit")
        mask = mask.resize((out_w, out_h), Image.Resampling.LANCZOS)

    tiles_root = project_root / "02-tiles" / "_shared"
    tiles_root.mkdir(parents=True, exist_ok=True)
    png_path = tiles_root / "terrain_underlay.png"
    mask.save(png_path, optimize=True)
    mb = png_path.stat().st_size / (1024 * 1024)
    print(f"Wrote {png_path} ({out_w}x{out_h}, {mb:.1f} MB)")

    variant_cfg = (config.get("world_variants") or {}).get(variant or "", {})
    region_dir = variant_cfg.get("region_kml_dir", variant or "wowcommanderalpha")
    kml_path = project_root / "03-kml" / region_dir / "terrain_underlay.kml"
    write_underlay_kml(kml_path, png_path, draw_order=draw_order)
    print(f"Wrote {kml_path}")
    return kml_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build real-Earth land terrain underlay for Google Earth")
    parser.add_argument("--variant", default="wowcommanderalpha")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config = merge_variant_config(load_globe_config(project_root), args.variant)
    build_terrain_underlay(project_root, config, variant=args.variant)


if __name__ == "__main__":
    main()
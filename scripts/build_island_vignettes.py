#!/usr/bin/env python3
"""
Build vignette-style overview PNGs for secondary and minor Pacific islands.

Mosaics minimap tiles (or single-map PNGs) into soft 600px PNGs for the mid-zoom
band (10k–2k mi). Islands are not composited into pacific_vignette.png.

Usage:
    python3 scripts/build_island_vignettes.py
    python3 scripts/build_island_vignettes.py --layer-id misc_crestfall
    python3 scripts/build_island_vignettes.py --list minor
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from globe_placement import layer_by_id, load_globe_config

try:
    from PIL import Image, ImageFilter
except ImportError:
    print("ERROR: Pillow is required. Run: pip3 install Pillow")
    raise SystemExit(1) from None

Image.MAX_IMAGE_PIXELS = None

TILE_PATTERN = re.compile(r"map(\d+)_(\d+)\.png$", re.IGNORECASE)
SOURCE_TILE_PX = 512


def vignette_output_path(layer: dict, project_root: Path) -> Path | None:
    tiers = layer.get("overview_png_tiers") or {}
    silhouette = tiers.get("silhouette")
    if silhouette is False or not isinstance(silhouette, dict):
        return None
    rel = silhouette.get("file")
    if not rel:
        return None
    return (project_root / rel).resolve()


def load_minimap_tiles(input_dir: Path) -> dict[tuple[int, int], Path]:
    tiles: dict[tuple[int, int], Path] = {}
    if not input_dir.exists():
        return tiles
    for path in input_dir.rglob("map*_*.png"):
        match = TILE_PATTERN.match(path.name)
        if match:
            tiles[(int(match.group(1)), int(match.group(2)))] = path
    return tiles


def mosaic_minimap(input_dir: Path) -> Image.Image | None:
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
            if tile.mode != "RGBA":
                tile = tile.convert("RGBA")
            px = (x - x_min) * SOURCE_TILE_PX
            py = (y - y_min) * SOURCE_TILE_PX
            canvas.alpha_composite(tile, (px, py))
    return canvas


def load_single_map_png(project_root: Path, layer: dict) -> Image.Image | None:
    rel_png = layer.get("single_map_png")
    if not rel_png:
        return None
    path = project_root / layer["input"] / rel_png
    if not path.exists():
        return None
    with Image.open(path) as img:
        return img.convert("RGBA")


def downscale_vignette(image: Image.Image, max_long_edge: int) -> Image.Image:
    width, height = image.size
    long_edge = max(width, height)
    if long_edge <= max_long_edge:
        return image.copy()
    scale = max_long_edge / long_edge
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))
    return image.resize((new_w, new_h), Image.Resampling.LANCZOS)


def build_island_vignette(
    project_root: Path,
    layer_id: str,
    layer: dict,
    *,
    max_long_edge: int,
    blur_radius: float,
) -> Path | None:
    export_path = vignette_output_path(layer, project_root)
    if not export_path:
        print(f"  [!] skip {layer_id}: no overview_png_tiers.silhouette.file")
        return None

    input_dir = project_root / layer["input"]
    mosaic = mosaic_minimap(input_dir)
    source_label = "minimap mosaic"
    if mosaic is None:
        mosaic = load_single_map_png(project_root, layer)
        source_label = "single PNG"
    if mosaic is None:
        print(f"  [!] skip {layer_id}: no tiles or single_map_png in {input_dir}")
        return None

    vignette = downscale_vignette(mosaic, max_long_edge)
    if blur_radius > 0:
        vignette = vignette.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    export_path.parent.mkdir(parents=True, exist_ok=True)
    vignette.save(export_path, optimize=True)
    print(
        f"  {layer_id}: {source_label} {mosaic.size[0]}x{mosaic.size[1]} "
        f"-> {vignette.size[0]}x{vignette.size[1]}  {export_path}"
    )
    return export_path


def default_island_ids(config: dict, list_name: str | None) -> list[str]:
    geo = config.get("geographic_placement", {})
    secondary = geo.get("silhouette_islands", [])
    minor = geo.get("minor_isles", [])
    if list_name == "secondary":
        return list(secondary)
    if list_name == "minor":
        return list(minor)
    return list(secondary) + list(minor)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build vignette PNGs for secondary and minor Pacific islands."
    )
    parser.add_argument("--layer-id", action="append", help="Build one island (repeatable).")
    parser.add_argument(
        "--list",
        choices=("secondary", "minor", "all"),
        default="all",
        help="Which island list to build when --layer-id is not set (default: all).",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config = load_globe_config(project_root)
    list_arg = None if args.list == "all" else args.list
    island_ids = args.layer_id or default_island_ids(config, list_arg)
    if not island_ids:
        raise SystemExit("No island ids in config and no --layer-id given.")

    zoom_cfg = config.get("zoom_transition", {})
    max_long_edge = int(zoom_cfg.get("vignette_png_max_long_edge", 600))

    print(f"=== Island vignettes ({len(island_ids)} regions, max edge {max_long_edge}px) ===")
    built = 0
    for layer_id in island_ids:
        layer = layer_by_id(config, layer_id)
        if not layer:
            print(f"  [!] skip {layer_id}: unknown layer")
            continue
        if build_island_vignette(
            project_root,
            layer_id,
            layer,
            max_long_edge=max_long_edge,
            blur_radius=0.6,
        ):
            built += 1

    print(f"\nBuilt {built}/{len(island_ids)} island vignette PNG(s)")


if __name__ == "__main__":
    main()
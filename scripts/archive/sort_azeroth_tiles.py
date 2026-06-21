#!/usr/bin/env python3
"""
Sort map##_##_ tiles from the azeroth inbox into region folders.

Workflow:
  1. In wow.export, select tiles on the 'azeroth' map (MINIMAP format).
  2. Export — files land in maps/azeroth/_inbox/  (copy them there if wow.export
     used maps/azeroth/minimap instead).
  3. Run: python3 scripts/sort_azeroth_tiles.py

Tiles are copied into kalimdor/, eastern_kingdoms/, maelstrom/, etc. based on
tile coordinate ranges in config/globe.json (edit those if a tile lands wrong).

Usage:
    python3 scripts/sort_azeroth_tiles.py
    python3 scripts/sort_azeroth_tiles.py --source 01-raw-export/maps/azeroth/_inbox
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

TILE_PATTERN = re.compile(r"map(\d+)_(\d+)\.png$", re.IGNORECASE)


def load_config(project_root: Path) -> dict:
    path = project_root / "config" / "globe.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def region_for_tile(x: int, y: int, bounds: dict) -> str | None:
    matches = []
    for name, box in bounds.items():
        if box["x_min"] <= x <= box["x_max"] and box["y_min"] <= y <= box["y_max"]:
            matches.append(name)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Overlapping bounds: prefer smallest area box
    def area(name: str) -> int:
        b = bounds[name]
        return (b["x_max"] - b["x_min"] + 1) * (b["y_max"] - b["y_min"] + 1)

    return min(matches, key=area)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sort azeroth MINIMAP tiles into region folders")
    parser.add_argument("--source", type=Path, default=None, help="Folder with map##_##_ PNGs")
    parser.add_argument("--move", action="store_true", help="Move instead of copy")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config = load_config(project_root)
    regions_cfg = config.get("azeroth_regions", {})
    bounds = regions_cfg.get("tile_bounds", {})
    default_source = project_root / regions_cfg.get("inbox", "01-raw-export/maps/azeroth/_inbox")
    source = args.source or default_source

    if not source.exists():
        raise SystemExit(f"Source folder not found: {source}\nExport tiles to this folder first.")

    maps_root = project_root / "01-raw-export" / "maps"
    copied = {name: 0 for name in bounds}
    unknown = 0

    for path in sorted(source.glob("map*_*.png")):
        match = TILE_PATTERN.match(path.name)
        if not match:
            continue
        x, y = int(match.group(1)), int(match.group(2))
        region = region_for_tile(x, y, bounds)
        if not region:
            dest_dir = maps_root / "azeroth" / "_unsorted"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / path.name
            if args.move:
                shutil.move(path, dest)
            else:
                shutil.copy2(path, dest)
            unknown += 1
            continue

        dest_dir = maps_root / region / "minimap"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / path.name
        if args.move:
            shutil.move(path, dest)
        else:
            shutil.copy2(path, dest)
        copied[region] += 1

    print("Sorted azeroth tiles:")
    for name, count in copied.items():
        if count:
            print(f"  {name}: {count} tiles -> maps/{name}/minimap/")
    if unknown:
        print(f"  unassigned: {unknown} (edit tile_bounds in config/globe.json)")
    if not any(copied.values()) and not unknown:
        print("  No map##_##_ PNG files found in source folder.")


if __name__ == "__main__":
    main()
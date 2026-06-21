#!/usr/bin/env python3
"""
Copy wow.export tiles from nested maps/<mapid>/minimap/ into canonical <zone>/minimap/.

wow.export often writes:
  01-raw-export/maps/draenor/maps/draenor/minimap/map32_16.png

This script flattens to:
  01-raw-export/maps/draenor/minimap/map32_16.png
  rawfilenoocean/maps/draenor/minimap/map32_16.png  (optional mirror)

Usage:
    python3 scripts/flatten_wow_exports.py
    python3 scripts/flatten_wow_exports.py --zones draenor outland
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

TILE_PATTERN = re.compile(r"map(\d+)_(\d+)\.png$", re.IGNORECASE)
WMO_PATTERN = re.compile(r".*_wmo_minimap\.png$", re.IGNORECASE)


def copy_tiles(src_root: Path, dest_minimap: Path) -> int:
    """Copy map##_#.png and *_wmo_minimap.png into dest_minimap."""
    dest_minimap.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in src_root.rglob("*.png"):
        if TILE_PATTERN.match(path.name) or WMO_PATTERN.match(path.name):
            dest = dest_minimap / path.name
            if dest.exists() and dest.stat().st_size == path.stat().st_size:
                continue
            shutil.copy2(path, dest)
            count += 1
    return count


def zone_roots(project_root: Path, zone_ids: list[str]) -> list[tuple[str, Path]]:
    pairs: list[tuple[str, Path]] = []
    config = json.loads((project_root / "config" / "globe.json").read_text(encoding="utf-8"))
    opposite = set(config.get("geographic_placement", {}).get("opposite_hemisphere", {}).get("ids", []))

    for zone_id in zone_ids:
        if zone_id in opposite:
            pairs.append((zone_id, project_root / "01-raw-export" / "maps" / zone_id))
        else:
            pairs.append((zone_id, project_root / "01-raw-export" / "maps" / "subterranean" / zone_id.split("/", 1)[0] / zone_id.split("/")[-1] if "/" in zone_id else project_root / "01-raw-export" / "maps" / "subterranean" / zone_id))

    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Flatten nested wow.export paths to zone/minimap/")
    parser.add_argument("--zones", nargs="*", help="Zone ids (default: opposite_hemisphere list)")
    parser.add_argument("--no-noocean", action="store_true", help="Skip rawfilenoocean mirror")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config = json.loads((project_root / "config" / "globe.json").read_text(encoding="utf-8"))
    zone_ids = args.zones or config.get("geographic_placement", {}).get("opposite_hemisphere", {}).get("ids", [])

    raw_export = project_root / "01-raw-export" / "maps"
    noocean = project_root / "rawfilenoocean" / "maps"

    total = 0
    for zone_id in zone_ids:
        src_zone = raw_export / zone_id
        if not src_zone.exists():
            print(f"  skip {zone_id}: folder missing")
            continue
        dest = src_zone / "minimap"
        n = copy_tiles(src_zone, dest)
        print(f"  {zone_id}: {n} file(s) -> {dest.relative_to(project_root)}")
        total += n

        if not args.no_noocean:
            dest_no = noocean / zone_id / "minimap"
            n2 = copy_tiles(src_zone, dest_no)
            if n2:
                print(f"         {n2} file(s) -> {dest_no.relative_to(project_root)}")

    # Subterranean WMO-only zones: copy wmo png into zone/minimap for discover
    sub_cfg = json.loads((project_root / "config" / "subterranean.json").read_text(encoding="utf-8"))
    for parent, zones in sub_cfg.get("zones", {}).items():
        for zone in zones:
            zone_id = zone["id"]
            src = raw_export / "subterranean" / parent / zone_id
            if not src.exists():
                continue
            dest = src / "minimap"
            n = copy_tiles(src, dest)
            if n:
                print(f"  sub/{parent}/{zone_id}: {n} file(s) -> .../minimap/")
                total += n

    print(f"\nFlattened {total} file(s)")


if __name__ == "__main__":
    main()
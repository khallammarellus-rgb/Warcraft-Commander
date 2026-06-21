#!/usr/bin/env python3
"""
Delete uniform blue ocean tiles from a raw export tree (default: rawfilenoocean).

Usage:
  python3 scripts/remove_ocean_tiles.py --dry-run
  python3 scripts/remove_ocean_tiles.py --apply
  python3 scripts/remove_ocean_tiles.py --apply --region kalimdor
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from globe_placement import load_globe_config
from tile_filters import is_empty_ocean_tile

try:
    from PIL import Image
except ImportError:
    print("ERROR: pip3 install Pillow")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove uniform ocean tiles from raw export copy")
    parser.add_argument(
        "--raw-root",
        default=None,
        help="Raw folder (default: config raw_export_noocean or rawfilenoocean)",
    )
    parser.add_argument("--region", default=None, help="Only process one region folder name")
    parser.add_argument("--dry-run", action="store_true", help="List files only, do not delete")
    parser.add_argument("--apply", action="store_true", help="Actually delete matching tiles")
    args = parser.parse_args()

    if not args.dry_run and not args.apply:
        parser.error("Use --dry-run or --apply")

    project_root = Path(__file__).resolve().parent.parent
    config = load_globe_config(project_root)
    raw_root = args.raw_root or config.get("raw_export_noocean", "rawfilenoocean")
    maps_dir = project_root / raw_root / "maps"
    if not maps_dir.exists():
        raise SystemExit(f"Not found: {maps_dir}")

    regions = [args.region] if args.region else sorted(
        p.name for p in maps_dir.iterdir() if p.is_dir() and (p / "minimap").exists()
    )

    total_remove = 0
    total_keep = 0
    for region in regions:
        minimap = maps_dir / region / "minimap"
        if not minimap.exists():
            continue
        remove = 0
        keep = 0
        for path in sorted(minimap.rglob("map*.png")):
            with Image.open(path) as img:
                if is_empty_ocean_tile(img):
                    remove += 1
                    if args.apply:
                        path.unlink()
                    elif args.dry_run and remove <= 3:
                        print(f"  would remove {path.relative_to(project_root)}")
                else:
                    keep += 1
        if remove:
            verb = "removed" if args.apply else "would remove"
            print(f"{region}: {verb} {remove}, keep {keep}")
        total_remove += remove
        total_keep += keep

    label = "Would remove" if args.dry_run else "Removed"
    print(f"\n{label} {total_remove} uniform ocean tiles ({total_keep} kept)")
    if args.dry_run:
        print("Run with --apply to delete.")


if __name__ == "__main__":
    main()
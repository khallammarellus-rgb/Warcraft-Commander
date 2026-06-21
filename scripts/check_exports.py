#!/usr/bin/env python3
"""
Report export status for every layer in config/globe.json.

Usage:
    python3 scripts/check_exports.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TILE_PATTERN = re.compile(r"map(\d+)_(\d+)\.png$", re.IGNORECASE)


def scan_minimap(folder: Path) -> dict:
    if not folder.exists():
        return {"status": "missing", "tiles": 0}

    tiles = []
    seen: set[tuple[int, int]] = set()
    for path in folder.rglob("map*_*.png"):
        match = TILE_PATTERN.match(path.name)
        if match:
            coord = (int(match.group(1)), int(match.group(2)))
            if coord in seen:
                continue
            seen.add(coord)
            tiles.append(coord)

    if not tiles:
        return {"status": "empty", "tiles": 0}

    xs = [x for x, _ in tiles]
    ys = [y for _, y in tiles]
    cols = max(xs) - min(xs) + 1
    rows = max(ys) - min(ys) + 1
    return {
        "status": "ready",
        "tiles": len(tiles),
        "x_range": f"{min(xs)}-{max(xs)}",
        "y_range": f"{min(ys)}-{max(ys)}",
        "grid": f"{cols} x {rows}",
        "gaps": cols * rows - len(tiles),
    }


def scan_poster(folder: Path, poster_file: str) -> dict:
    if not folder.exists():
        return {"status": "missing"}
    target = folder / poster_file
    if target.exists():
        mb = target.stat().st_size / (1024 * 1024)
        return {"status": "ready", "file": poster_file, "size_mb": round(mb, 2)}
    pngs = list(folder.glob("*.png"))
    if pngs:
        return {"status": "ready", "file": pngs[0].name, "size_mb": round(pngs[0].stat().st_size / (1024 * 1024), 2)}
    return {"status": "empty"}


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "globe.json"

    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)

    layers = config.get("layers", [])
    inbox = project_root / config.get("azeroth_regions", {}).get("inbox", "01-raw-export/maps/azeroth/_inbox")

    print("WoW export status")
    print("=" * 64)
    print("\nExport directory (wow.export Settings):")
    print(f"  {project_root / '01-raw-export'}")
    print("\nYou only need MAX-DETAIL MINIMAP tiles per region.")
    print("Zoom levels are built automatically by build_kml_superoverlay.py")
    print("Exception: azeroth/poster/ = master reference image for zoomed-out view.\n")

    if inbox.exists() and list(inbox.glob("map*_*.png")):
        n = len(list(inbox.glob("map*_*.png")))
        print(f"[!] {n} tiles waiting in azeroth/_inbox — run: python3 scripts/sort_azeroth_tiles.py\n")

    for layer in layers:
        layer_id = layer.get("id", "?")
        label = layer.get("label", layer_id)
        layer_type = layer.get("layer_type", "minimap")
        rel_input = layer.get("input", "")
        folder = project_root / rel_input
        enabled = layer.get("enabled", False)
        flag = "ON " if enabled else "off"

        print(f"[{flag}] {label}")
        print(f"     id: {layer_id}  type: {layer_type}")
        print(f"     wow.export map: {layer.get('wow_map', '?')}")
        print(f"     folder: {rel_input}")

        if layer_type == "poster":
            info = scan_poster(folder, layer.get("poster_file", "world.png"))
            if info["status"] == "missing":
                print("     status: folder missing")
            elif info["status"] == "empty":
                print("     status: waiting for world.png (single overview image)")
            else:
                print(f"     status: ready — {info['file']} ({info['size_mb']} MB)")
        else:
            info = scan_minimap(folder)
            if info["status"] == "missing":
                print("     status: folder missing")
            elif info["status"] == "empty":
                print("     status: waiting for MINIMAP export")
            else:
                print(f"     status: {info['tiles']} tiles, grid {info['grid']}")
                print(f"     range: X {info['x_range']}, Y {info['y_range']}")
                if info["gaps"]:
                    print(f"     gaps: {info['gaps']} empty cells in bounding box")

        if layer.get("notes"):
            print(f"     note: {layer['notes']}")

    print("\n" + "=" * 64)


if __name__ == "__main__":
    main()
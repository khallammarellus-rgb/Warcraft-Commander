#!/usr/bin/env python3
"""
Register misc islands and subterranean zones as globe.json layers.

Reads config/misc_islands.json and config/subterranean.json, adds/updates layers
with exports, removes the misc_islands placeholder.

Usage:
    python3 scripts/sync_extra_layers.py
    python3 scripts/apply_geographic_placements.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

TILE_PATTERN = re.compile(r"map(\d+)_(\d+)\.png$", re.IGNORECASE)
WMO_PATTERN = re.compile(r".*_wmo_minimap\.png$", re.IGNORECASE)


def has_export(root: Path) -> bool:
    if not root.exists():
        return False
    for path in root.rglob("*.png"):
        if TILE_PATTERN.match(path.name) or WMO_PATTERN.match(path.name):
            return True
    return False


def tile_count(root: Path) -> int:
    if not root.exists():
        return 0
    seen: set[tuple[int, int]] = set()
    for path in root.rglob("map*_*.png"):
        match = TILE_PATTERN.match(path.name)
        if match:
            seen.add((int(match.group(1)), int(match.group(2))))
    return len(seen)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def misc_layer_entry(island: dict, defaults: dict) -> dict:
    folder = island["folder"]
    return {
        "id": island["id"],
        "label": island["label"],
        "layer_type": defaults.get("layer_type", "minimap"),
        "wow_map": island.get("wow_map", folder),
        "input": f"01-raw-export/maps/misc_islands/maps/{folder}",
        "enabled": island.get("enabled", defaults.get("enabled", True)),
        "parent_region": island["parent_region"],
        "offset_deg": island["offset_deg"],
        "size_scale": island.get("size_scale", defaults.get("size_scale", 0.06)),
        "notes": island.get("notes", "Misc island — parent-relative placement"),
    }


def sub_layer_entry(parent: str, zone: dict, defaults: dict) -> dict:
    zone_id = zone["id"]
    return {
        "id": zone_id,
        "label": zone["label"],
        "layer_type": "subterranean",
        "wow_map": zone.get("wow_map", zone_id),
        "input": f"01-raw-export/maps/subterranean/{parent}/{zone_id}/minimap",
        "enabled": zone.get("enabled", defaults.get("enabled", False)),
        "parent_region": parent,
        "offset_deg": zone.get("offset_deg", defaults.get("offset_deg", [0.0, 0.0])),
        "size_scale": zone.get("size_scale", defaults.get("size_scale", 0.08)),
        "subterranean": {
            "depth_m": zone.get("depth_m", defaults.get("depth_m", -1500)),
            "default_visible": zone.get("default_visible", defaults.get("default_visible", False)),
        },
        "notes": zone.get("notes", f"Subterranean under {parent}"),
    }


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "globe.json"
    config = load_json(config_path)

    misc_cfg = load_json(project_root / "config" / "misc_islands.json")
    sub_cfg = load_json(project_root / "config" / "subterranean.json")

    layers = [layer for layer in config.get("layers", []) if layer.get("id") != "misc_islands"]
    existing = {layer["id"]: i for i, layer in enumerate(layers)}

    added_misc = 0
    skipped_misc = 0
    for island in misc_cfg.get("islands", []):
        entry = misc_layer_entry(island, misc_cfg.get("defaults", {}))
        root = project_root / entry["input"]
        if not has_export(root):
            skipped_misc += 1
            print(f"  skip misc (no tiles): {island['id']}")
            continue
        if entry["id"] in existing:
            layers[existing[entry["id"]]] = entry
        else:
            layers.append(entry)
            existing[entry["id"]] = len(layers) - 1
        added_misc += 1
        print(f"  misc: {entry['id']} ({tile_count(root)} tiles)")

    sub_defaults = sub_cfg.get("defaults", {})
    added_sub = 0
    skipped_sub = 0
    for parent, zones in sub_cfg.get("zones", {}).items():
        for zone in zones:
            entry = sub_layer_entry(parent, zone, sub_defaults)
            zone_root = project_root / "01-raw-export" / "maps" / "subterranean" / parent / zone["id"]
            if not has_export(zone_root):
                skipped_sub += 1
                print(f"  skip sub (no tiles): {entry['id']}")
                continue
            entry["enabled"] = True
            if entry["id"] in existing:
                layers[existing[entry["id"]]] = entry
            else:
                layers.append(entry)
                existing[entry["id"]] = len(layers) - 1
            added_sub += 1
            wmo = "wmo" if not tile_count(zone_root) else f"{tile_count(zone_root)} tiles"
            print(f"  sub:  {entry['id']} ({wmo})")

    config["layers"] = layers
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    print(f"\nSynced {added_misc} misc + {added_sub} subterranean layer(s)")
    if skipped_misc or skipped_sub:
        print(f"Skipped {skipped_misc} misc + {skipped_sub} sub (no export tiles)")
    print(f"Updated {config_path}")
    print("Next: python3 scripts/apply_geographic_placements.py")


if __name__ == "__main__":
    main()
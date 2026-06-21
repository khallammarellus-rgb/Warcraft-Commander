#!/usr/bin/env python3
"""
List Quick View bookmarks from config/globe.json.

Planet and strategic bookmarks are built from viewpoints.view_distance_defaults.
Rebuild after config edits: python3 scripts/build_world_globe.py --kml-only
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

MILES_TO_METERS = 1609.344


def main() -> None:
    parser = argparse.ArgumentParser(description="List Quick View bookmark config")
    parser.add_argument("--list", action="store_true", help="List configured tiers (default)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "globe.json"

    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)

    vdd = config.get("viewpoints", {}).get("view_distance_defaults")
    if not vdd:
        print("No view_distance_defaults in config/globe.json")
        return

    print(vdd.get("folder_label", "Quick View"))
    tiers = vdd.get("tiers", {})
    planet = tiers.get("planet", {})
    if planet:
        miles = planet.get("range_miles", 60000)
        print(f"  planet: {planet.get('placemark_name', 'Planet')} @ Maelstrom — {miles:,.0f} mi")
    strategic = tiers.get("strategic", {})
    if strategic:
        miles = strategic.get("range_miles", 3000)
        regions = strategic.get("regions", [])
        print(f"  strategic: {len(regions)} continents @ {miles:,.0f} mi")
        for region_id in regions:
            print(f"    - {region_id}")
    print("\nRebuild: python3 scripts/build_world_globe.py --kml-only")


if __name__ == "__main__":
    main()
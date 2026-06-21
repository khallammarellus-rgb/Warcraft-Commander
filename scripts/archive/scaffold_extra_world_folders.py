#!/usr/bin/env python3
"""
Create 01-raw-export/maps/<world>/minimap/ folders for opposite-hemisphere zones.

Reads geographic_placement.opposite_hemisphere.ids from config/globe.json.

Usage:
    python3 scripts/scaffold_extra_world_folders.py
"""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config = json.loads((project_root / "config" / "globe.json").read_text(encoding="utf-8"))
    geo = config.get("geographic_placement", {})
    world_ids = geo.get("opposite_hemisphere", {}).get("ids", [])

    if not world_ids:
        print("No opposite_hemisphere.ids in config/globe.json")
        return

    maps_root = project_root / "01-raw-export" / "maps"
    for world_id in world_ids:
        minimap_dir = maps_root / world_id / "minimap"
        minimap_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = minimap_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()
        print(f"  {minimap_dir.relative_to(project_root)}")

    print(f"\nReady: {len(world_ids)} extra-world export folder(s)")


if __name__ == "__main__":
    main()
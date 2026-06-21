#!/usr/bin/env python3
"""
Create 01-raw-export/maps/subterranean/<parent>/<zone>/minimap/ folders from config.

Usage:
    python3 scripts/scaffold_subterranean_folders.py
"""

from __future__ import annotations

import json
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "subterranean.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    base = project_root / "01-raw-export" / "maps" / "subterranean"
    created = 0

    for parent_id, zones in config.get("zones", {}).items():
        for zone in zones:
            zone_id = zone["id"]
            minimap_dir = base / parent_id / zone_id / "minimap"
            minimap_dir.mkdir(parents=True, exist_ok=True)
            gitkeep = minimap_dir / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.touch()
            created += 1
            print(f"  {minimap_dir.relative_to(project_root)}")

    print(f"\nReady: {created} subterranean export folder(s) under 01-raw-export/maps/subterranean/")


if __name__ == "__main__":
    main()
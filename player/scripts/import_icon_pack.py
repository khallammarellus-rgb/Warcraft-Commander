#!/usr/bin/env python3
"""
Import a shared icon pack into assets/player_custom_icons/.

  python3 scripts/import_icon_pack.py --zip icon-pack-blue.zip
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from package_icon_pack import icons_dir


def import_icon_pack(project_root: Path, zip_path: Path, *, overwrite: bool = True) -> dict:
    dest = icons_dir(project_root)
    dest.mkdir(parents=True, exist_ok=True)
    imported: list[str] = []
    skipped: list[str] = []

    with zipfile.ZipFile(zip_path) as zf:
        manifest = {}
        if "manifest.json" in zf.namelist():
            manifest = json.loads(zf.read("manifest.json"))
        for name in zf.namelist():
            if not name.startswith("icons/") or not name.lower().endswith(".png"):
                continue
            filename = Path(name).name
            target = dest / filename
            if target.exists() and not overwrite:
                skipped.append(filename)
                continue
            target.write_bytes(zf.read(name))
            imported.append(filename)

    return {"dest": dest, "imported": imported, "skipped": skipped, "manifest": manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description="Import shared icon pack")
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--no-overwrite", action="store_true")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    if not args.zip.is_file():
        raise SystemExit(f"Missing {args.zip}")

    result = import_icon_pack(project_root, args.zip, overwrite=not args.no_overwrite)
    print(f"Imported {len(result['imported'])} icon(s) → {result['dest']}")
    if result["skipped"]:
        print(f"  Skipped {len(result['skipped'])} existing file(s) (--no-overwrite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
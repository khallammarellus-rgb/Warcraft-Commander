#!/usr/bin/env python3
"""
Extract embedded images from wargaming-and-briefing-graphics.pptx for manual curation.

  python3 scripts/extract_pptx_icons.py
  python3 scripts/extract_pptx_icons.py --pptx ~/Downloads/icons/wargaming-and-briefing-graphics.pptx

Writes:
  assets/icon_library/source/pptx_raw/<basename>.png
  assets/icon_library/source/pptx_catalog.json  (review before adding to config/icon_builder_allowlist.json)
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from PIL import Image

DEFAULT_PPTX = Path.home() / "Downloads" / "icons" / "wargaming-and-briefing-graphics.pptx"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract pptx embedded images for icon builder curation")
    parser.add_argument("--pptx", type=Path, default=DEFAULT_PPTX)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Default: assets/icon_library/source/pptx_raw under project root",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_dir = args.out_dir or (project_root / "assets" / "icon_library" / "source" / "pptx_raw")
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.pptx.is_file():
        print(f"PPTX not found: {args.pptx}")
        return 1

    catalog: list[dict] = []
    with zipfile.ZipFile(args.pptx) as zf:
        for name in sorted(zf.namelist()):
            if not name.startswith("ppt/media/"):
                continue
            suffix = Path(name).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".emf", ".wmf"}:
                continue
            data = zf.read(name)
            base = Path(name).name
            dest = out_dir / base
            dest.write_bytes(data)
            entry: dict = {"file": base, "zip_path": name, "bytes": len(data)}
            if suffix in {".png", ".jpg", ".jpeg", ".gif"}:
                try:
                    with Image.open(dest) as im:
                        entry["width"] = im.width
                        entry["height"] = im.height
                except OSError:
                    entry["error"] = "unreadable"
            catalog.append(entry)

    catalog_path = out_dir.parent / "pptx_catalog.json"
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"Extracted {len(catalog)} file(s) → {out_dir}")
    print(f"Catalog: {catalog_path}")
    print("Add keepers to config/icon_builder_allowlist.json under \"include\" (basename list).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
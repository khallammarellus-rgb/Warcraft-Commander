#!/usr/bin/env python3
"""
Package custom unit icons referenced in campaign KML for sharing with opponents.

  python3 scripts/package_icon_pack.py
  python3 scripts/package_icon_pack.py --out exports/icon-pack-blue.zip
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_icons import ICON_HREF_RE, icons_dir
from package_wargame_client import campaign_dir_for_variant

KML_NS = "http://www.opengis.net/kml/2.2"
DEFAULT_VARIANT = "wowcommanderalpha"


def collect_icon_hrefs(project_root: Path, variant: str) -> set[str]:
    names: set[str] = set()
    campaign_dir = campaign_dir_for_variant(project_root, variant)
    live = project_root / "03-kml" / variant / "campaign_live.kml"
    paths = list(campaign_dir.glob("*.kml")) if campaign_dir.is_dir() else []
    if live.is_file():
        paths.append(live)
    player_live = project_root / "player" / "kml" / "campaign_live.kml"
    if player_live.is_file():
        paths.append(player_live)

    for kml_path in paths:
        try:
            text = kml_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in ICON_HREF_RE.finditer(text):
            names.add(match.group(1).strip())
        root = ET.parse(kml_path).getroot()
        for href_el in root.findall(f".//{{{KML_NS}}}href"):
            if href_el.text:
                for match in ICON_HREF_RE.finditer(href_el.text):
                    names.add(match.group(1).strip())
    return names


def package_icon_pack(project_root: Path, *, variant: str, out: Path, cell: str = "") -> dict:
    icons_root = icons_dir(project_root)
    names = sorted(collect_icon_hrefs(project_root, variant))
    included: list[str] = []
    missing: list[str] = []

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            src = icons_root / name
            if not src.is_file():
                missing.append(name)
                continue
            zf.write(src, f"icons/{name}")
            included.append(name)
        manifest = {
            "type": "wow_commander_icon_pack",
            "version": 1,
            "created": date.today().isoformat(),
            "cell": cell or None,
            "icons": included,
            "missing_hrefs": missing,
            "install_path": "assets/player_custom_icons/",
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        zf.writestr(
            "README.txt",
            "WoW Commander icon pack\n\n"
            "Import with: python3 scripts/import_icon_pack.py --zip this-file.zip\n"
            "Or use the Install Wizard → Import icon pack.\n",
        )

    return {
        "out": out,
        "included": len(included),
        "missing": len(missing),
        "names": included,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Package custom icons for opponent sharing")
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--cell", default="", help="Label for manifest (red-cell, blue-cell)")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out = args.out or (
        project_root / "exports" / f"icon-pack-{args.cell or 'shared'}-{date.today().isoformat()}.zip"
    )
    result = package_icon_pack(project_root, variant=args.variant, out=out, cell=args.cell)
    print(f"Packaged {result['included']} icon(s) → {result['out']}")
    if result["missing"]:
        print(f"  {result['missing']} href(s) in KML but PNG missing locally")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
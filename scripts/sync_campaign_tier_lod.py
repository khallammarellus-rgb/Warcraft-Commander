#!/usr/bin/env python3
"""
Make campaign tier folders editable in Google Earth Pro and apply LOD to placemarks.

Google Earth greys out folders that carry Region/Lod, so tier folders are plain
containers. Zoom-tier visibility lives on each placemark instead.

Usage:
    python3 scripts/sync_campaign_tier_lod.py
    python3 scripts/sync_campaign_tier_lod.py --file campaign/kalimdor.kml
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_tier_lod import (
    KML_NS,
    inject_placemark_tier_regions,
    migrate_to_campaign_package,
    strip_tier_folder_regions,
    write_campaign_package_template,
)

ET.register_namespace("", KML_NS)
from package_wargame_client import campaign_dir_for_variant, list_campaign_files


def sync_campaign_file(path: Path, *, dry_run: bool = False, rewrite: bool = False) -> dict:
    root = ET.parse(path).getroot()
    migrated = migrate_to_campaign_package(root)
    stripped = strip_tier_folder_regions(root)
    injected = inject_placemark_tier_regions(root)
    if migrated or stripped or injected or rewrite:
        if not dry_run:
            tree = ET.ElementTree(root)
            ET.indent(tree, space="  ")
            tree.write(path, encoding="utf-8", xml_declaration=True)
    return {
        "migrated": migrated,
        "stripped": stripped,
        "injected": injected,
        "rewrote": bool(migrated or stripped or injected or rewrite),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix campaign tier folders for GEP editing and placemark LOD"
    )
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument("--file", type=Path, help="Single campaign .kml (relative to project root)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--rewrite-all",
        action="store_true",
        help="Rewrite files even when already migrated (fixes namespace prefixes)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    if args.file:
        paths = [project_root / args.file]
    else:
        paths = list_campaign_files(project_root, args.variant)
        doc = campaign_dir_for_variant(project_root, args.variant) / "doc.kml"
        if doc.exists() and doc not in paths:
            paths.insert(0, doc)

    if not paths:
        raise SystemExit("No campaign files found.")

    total_migrated = 0
    total_stripped = 0
    total_injected = 0
    for path in paths:
        if not path.exists():
            print(f"skip (missing): {path}")
            continue
        result = sync_campaign_file(
            path, dry_run=args.dry_run, rewrite=args.rewrite_all
        )
        total_migrated += result["migrated"]
        total_stripped += result["stripped"]
        total_injected += result["injected"]
        if result["rewrote"]:
            action = "would update" if args.dry_run else "updated"
            print(
                f"{action}: {path.name} "
                f"(package migrated: {result['migrated']}, "
                f"folder Regions removed: {result['stripped']}, "
                f"placemark LOD added: {result['injected']})"
            )

    template_dir = campaign_dir_for_variant(project_root, args.variant)
    template_path = template_dir / "Campaign Package" / "campaign_package.kml"
    if not args.dry_run:
        write_campaign_package_template(template_path)
        print(f"template: {template_path}")

    print(
        f"Done — {len(paths)} file(s); "
        f"package migrated: {total_migrated}; "
        f"folder Regions removed: {total_stripped}; "
        f"placemark LOD added: {total_injected}"
    )


if __name__ == "__main__":
    main()
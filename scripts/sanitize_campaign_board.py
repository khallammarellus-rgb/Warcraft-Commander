#!/usr/bin/env python3
"""
Reset campaign boards to a clean, reusable state.

Removes player placemarkers, wizard HQ injection, session/blind state, turn-export
artifacts, and Google Earth saved copies — then rebuilds campaign_live.kml from
empty theater shells.

Does NOT touch map tiles, doc.kml / doc_player.kml, region overviews, or the
faction library (assets/faction_library/).

  python3 scripts/sanitize_campaign_board.py
  python3 scripts/sanitize_campaign_board.py --yes
  python3 scripts/sanitize_campaign_board.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_campaign_live import build_campaign_live_kml
from build_kml_superoverlay import merge_variant_config
from build_world_globe import resolve_campaign_region_ids
from campaign_tier_lod import CAMPAIGN_PACKAGE_NAME, KML_NS, append_campaign_package_folder, strip_tier_folder_regions
from campaign_visibility import DEFAULT_META, meta_path, reveal_state_path
from campaign_session import SESSION_FILENAME
from globe_placement import layer_by_id, load_globe_config
from package_wargame_client import campaign_dir_for_variant

ET.register_namespace("", KML_NS)

SESSION_ARTIFACT = SESSION_FILENAME
BRIEFING_ARTIFACT = "briefing.txt"
EXPORT_GLOB = "wowcommander_turn*.kmz"
LIVE_KMZ_NAMES = ("campaign_live.kmz",)


def _kml(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def _collapse_folder_tree(element: ET.Element) -> None:
    if element.tag == _kml("Folder"):
        open_el = element.find(_kml("open"))
        if open_el is None:
            open_el = ET.SubElement(element, _kml("open"))
        open_el.text = "0"
    for child in element:
        _collapse_folder_tree(child)


def write_clean_theater_kml(
    path: Path,
    *,
    label: str,
) -> None:
    """Overwrite a theater campaign file with an empty Campaign Package shell."""
    kml = ET.Element(_kml("kml"))
    document = ET.SubElement(kml, _kml("Document"))
    ET.SubElement(document, _kml("name")).text = f"{label} campaign"
    ET.SubElement(document, _kml("description")).text = (
        f"Turn state for {label}. Use Campaign Package → red-cell or blue-cell → "
        "one tier per marker (Strategic / Operational / Tactical)."
    )
    package = append_campaign_package_folder(document)
    _collapse_folder_tree(package)

    strip_tier_folder_regions(kml)
    tree = ET.ElementTree(kml)
    ET.indent(tree, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def write_clean_campaign_doc(path: Path) -> None:
    """Reset campaign/doc.kml to an empty global Campaign Package (no placemarks)."""
    kml = ET.Element(_kml("kml"))
    document = ET.SubElement(kml, _kml("Document"))
    ET.SubElement(document, _kml("name")).text = "WOWCommanderAlpha Campaign"
    ET.SubElement(document, _kml("description")).text = (
        "Turn state: placemarks, paths, polygons, and folders. "
        "Per-theater files live alongside this doc as <region>.kml."
    )
    package = append_campaign_package_folder(document)
    _collapse_folder_tree(package)
    strip_tier_folder_regions(kml)
    tree = ET.ElementTree(kml)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _count_placemarks(path: Path) -> int:
    if not path.exists():
        return 0
    root = ET.parse(path).getroot()
    return len(root.findall(f".//{_kml('Placemark')}"))


def _plan_sanitize(project_root: Path, *, variant: str) -> dict:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, variant)
    variant_cfg = (base.get("world_variants", {}) or {}).get(variant, {})
    campaign_dir = campaign_dir_for_variant(project_root, variant)
    world_parent = project_root / Path(
        variant_cfg.get("output", "03-kml/wowcommanderalpha/doc.kml")
    ).parent
    exports_dir = project_root / "exports"

    theater_resets: list[tuple[str, Path, int]] = []
    for region_id in resolve_campaign_region_ids(config, variant_cfg):
        path = campaign_dir / f"{region_id}.kml"
        if not path.exists():
            continue
        layer = layer_by_id(config, region_id)
        label = layer.get("label", region_id) if layer else region_id
        pm_count = _count_placemarks(path)
        theater_resets.append((label, path, pm_count))

    deletes: list[Path] = []
    for name in (SESSION_ARTIFACT, BRIEFING_ARTIFACT):
        p = campaign_dir / name
        if p.exists():
            deletes.append(p)

    reveal = reveal_state_path(campaign_dir)
    if reveal.exists():
        deletes.append(reveal)

    for kmz_name in LIVE_KMZ_NAMES:
        p = world_parent / kmz_name
        if p.exists():
            deletes.append(p)

    if exports_dir.is_dir():
        for p in sorted(exports_dir.glob(EXPORT_GLOB)):
            deletes.append(p)

    doc_campaign = campaign_dir / "doc.kml"
    doc_pm = _count_placemarks(doc_campaign) if doc_campaign.exists() else 0

    return {
        "campaign_dir": campaign_dir,
        "world_parent": world_parent,
        "theater_resets": theater_resets,
        "doc_campaign": doc_campaign,
        "doc_placemarks": doc_pm,
        "deletes": deletes,
        "reset_meta": meta_path(campaign_dir),
    }


def sanitize_campaign_board(
    project_root: Path,
    *,
    variant: str = "wowcommanderalpha",
    dry_run: bool = False,
) -> dict:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, variant)
    variant_cfg = (base.get("world_variants", {}) or {}).get(variant, {})
    plan = _plan_sanitize(project_root, variant=variant)
    campaign_dir = plan["campaign_dir"]

    stats = {
        "theaters_reset": 0,
        "placemarks_removed": 0,
        "files_deleted": 0,
        "campaign_live_rebuilt": False,
    }

    for label, path, pm_count in plan["theater_resets"]:
        stats["placemarks_removed"] += pm_count
        if dry_run:
            print(f"  reset: {path.name} ({label}) — {pm_count} placemark(s)")
        else:
            write_clean_theater_kml(path, label=label)
            stats["theaters_reset"] += 1
            print(f"  reset: {path.name} ({label})")

    if plan["doc_campaign"].exists():
        if dry_run:
            print(
                f"  reset: {plan['doc_campaign'].name} — "
                f"{plan['doc_placemarks']} placemark(s)"
            )
        else:
            write_clean_campaign_doc(plan["doc_campaign"])
            stats["placemarks_removed"] += plan["doc_placemarks"]
            print(f"  reset: {plan['doc_campaign'].name}")

    if not dry_run:
        meta_path(campaign_dir).write_text(
            json.dumps(DEFAULT_META, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  reset: campaign_meta.json → {DEFAULT_META['game_format']}")

    for path in plan["deletes"]:
        if dry_run:
            print(f"  delete: {path.relative_to(project_root)}")
        else:
            path.unlink()
            stats["files_deleted"] += 1
            print(f"  deleted: {path.relative_to(project_root)}")

    if dry_run:
        print("  rebuild: campaign_live.kml (from clean theater files)")
        return stats

    build_campaign_live_kml(project_root, variant=variant)
    stats["campaign_live_rebuilt"] = True
    print(f"  rebuilt: campaign_live.kml")

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset campaign boards — empty shells, no player/wizard state"
    )
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    plan = _plan_sanitize(project_root, variant=args.variant)

    total_pm = sum(pm for _l, _p, pm in plan["theater_resets"]) + plan["doc_placemarks"]

    print("Sanitize campaign board")
    print("=" * 50)
    print(f"  Theaters to reset:     {len(plan['theater_resets'])}")
    print(f"  Placemarks to remove:  {total_pm}")
    print(f"  Session/artifact files:{len(plan['deletes'])}")
    print()
    print("Keeps: map tiles, doc.kml, region overviews, faction library")
    print("Removes: placemarkers, HQ, Unit palettes, game_session, reveal state,")
    print("         turn-export KMZs, campaign_live.kmz")
    print()

    if args.dry_run:
        print("Dry run — no changes written:")
        sanitize_campaign_board(project_root, variant=args.variant, dry_run=True)
        return 0

    if not args.yes:
        answer = input("Proceed? This cannot be undone. (yes/no): ").strip().lower()
        if answer not in ("yes", "y"):
            print("Cancelled.")
            return 0

    print()
    stats = sanitize_campaign_board(project_root, variant=args.variant)
    print()
    print("Done — board is clean and ready for a new campaign.")
    print(f"  {stats['theaters_reset']} theater(s) reset, "
          f"{stats['files_deleted']} file(s) removed")
    print("  Run Setup Campaign.command to start a new game.")
    print("  Close and reopen Google Earth Pro if it still shows old markers.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""
Sync campaign_live.kml ↔ campaign/*.kml theater files.

After editing placemarks in campaign_live.kml (File → Save in Google Earth Pro):
    python3 scripts/sync_campaign_live.py --push

Rebuild live file from disk (overwrites GEP edits in campaign_live.kml):
    python3 scripts/sync_campaign_live.py --pull
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_campaign_live import LIVE_DOC_NAME, build_campaign_live_kml
from build_world_globe import resolve_campaign_region_ids
from build_kml_superoverlay import merge_variant_config
from campaign_tier_lod import (
    CAMPAIGN_PACKAGE_NAME,
    KML_NS,
    append_campaign_package_folder,
    migrate_to_campaign_package,
    strip_tier_folder_regions,
)
from globe_placement import layer_by_id, layer_earth_bounds, load_globe_config
from campaign_live_io import parse_campaign_live_root, resolve_campaign_live_path
from faction_library import UNIT_PALETTES_FOLDER
from package_wargame_client import campaign_dir_for_variant

ET.register_namespace("", KML_NS)


def _kml(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def _label_to_region_id(config: dict, variant_cfg: dict, label: str) -> str | None:
    needle = label.strip().lower()
    for region_id in resolve_campaign_region_ids(config, variant_cfg):
        layer = layer_by_id(config, region_id)
        layer_label = (layer.get("label", region_id) if layer else region_id).lower()
        if needle == layer_label or needle == region_id.lower():
            return region_id
    return None


def _is_editable_theater_folder(
    folder: ET.Element,
    config: dict,
    variant_cfg: dict,
) -> bool:
    """True when folder name is a theater and it directly holds Campaign Package."""
    name_el = folder.find(_kml("name"))
    label = (name_el.text or "") if name_el is not None else ""
    if _label_to_region_id(config, variant_cfg, label) is None:
        return False
    for child in folder.findall(_kml("Folder")):
        child_name = child.find(_kml("name"))
        if child_name is not None and (child_name.text or "") == CAMPAIGN_PACKAGE_NAME:
            return True
    return False


def _iter_theater_folders(
    folder: ET.Element,
    config: dict,
    variant_cfg: dict,
):
    """Yield editable theater folders at any depth (continent + nested island theaters)."""
    for child in folder.findall(_kml("Folder")):
        if _is_editable_theater_folder(child, config, variant_cfg):
            yield child
        yield from _iter_theater_folders(child, config, variant_cfg)


def _write_theater_file(
    path: Path,
    *,
    label: str,
    bounds: tuple[float, float, float, float],
    payload_children: list[ET.Element],
) -> None:
    west, south, east, north = bounds
    kml = ET.Element(_kml("kml"))
    document = ET.SubElement(kml, _kml("Document"))
    ET.SubElement(document, _kml("name")).text = f"{label} campaign"
    ET.SubElement(document, _kml("description")).text = (
        f"Turn state for {label}. Use Campaign Package → red-cell or blue-cell → "
        "one tier per marker (Strategic / Operational / Tactical)."
    )
    for child in payload_children:
        document.append(copy.deepcopy(child))
    if not any(
        child.tag == _kml("Folder")
        and child.find(_kml("name")) is not None
        and (child.find(_kml("name")).text or "") == CAMPAIGN_PACKAGE_NAME
        for child in document
    ):
        append_campaign_package_folder(document)

    migrate_to_campaign_package(ET.ElementTree(kml).getroot())
    strip_tier_folder_regions(kml)
    tree = ET.ElementTree(kml)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def push_live_to_theaters(project_root: Path, *, variant: str) -> int:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, variant)
    variant_cfg = (base.get("world_variants", {}) or {}).get(variant, {})
    campaign_dir = campaign_dir_for_variant(project_root, variant)
    live_dir = project_root / Path(variant_cfg.get("output", "03-kml/wowcommanderalpha/doc.kml")).parent
    live_path = resolve_campaign_live_path(live_dir)
    if live_path is None:
        raise SystemExit(
            f"Missing campaign_live.kml or campaign_live.kmz in {live_dir} — "
            "run build_world_globe.py --kml-only"
        )

    root = parse_campaign_live_root(live_path)
    document = root.find(_kml("Document"))
    if document is None:
        raise SystemExit("campaign_live.kml has no Document")

    live_board = None
    for child in document.findall(_kml("Folder")):
        name_el = child.find(_kml("name"))
        if name_el is None:
            continue
        label = name_el.text or ""
        if label == UNIT_PALETTES_FOLDER:
            continue
        if "Campaign Package" in label:
            live_board = child
            break
    if live_board is None:
        live_board = document

    written = 0
    for theater in _iter_theater_folders(live_board, config, variant_cfg):
        name_el = theater.find(_kml("name"))
        if name_el is None:
            continue
        label = name_el.text or ""
        region_id = _label_to_region_id(config, variant_cfg, label)
        if region_id is None:
            print(f"skip (unknown theater): {label}")
            continue
        layer = layer_by_id(config, region_id)
        bounds = layer_earth_bounds(layer, config) if layer else (0, 0, 0, 0)
        payloads = [
            copy.deepcopy(child)
            for child in theater
            if child.tag in {_kml("Folder"), _kml("Placemark")}
        ]
        out = campaign_dir / f"{region_id}.kml"
        _write_theater_file(out, label=label, bounds=bounds, payload_children=payloads)
        written += 1
        print(f"pushed: {label} → {out.name}")

    return written


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Sync campaign_live.kml with campaign/*.kml")
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument("--push", action="store_true", help="campaign_live.kml → campaign/*.kml")
    parser.add_argument("--pull", action="store_true", help="campaign/*.kml → rebuild campaign_live.kml")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent

    if args.push:
        n = push_live_to_theaters(project_root, variant=args.variant)
        print(f"Done — pushed {n} theater file(s). Refresh Campaign Board links in doc.kml.")
        return
    if args.pull:
        build_campaign_live_kml(project_root, variant=args.variant)
        print("Done — rebuilt campaign_live.kml from campaign/*.kml")
        return
    parser.error("Specify --push or --pull")


if __name__ == "__main__":
    main()
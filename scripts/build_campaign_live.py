#!/usr/bin/env python3
"""
Build campaign_live.kml — editable inline campaign layers for Google Earth Pro.

NetworkLink content is read-only in GEP. campaign_live.kml uses inline Folders with
the same Region/Lod bands as doc.kml NetworkLinks (lazy load) but remains editable.

Sync edits back to campaign/*.kml with: python3 scripts/sync_campaign_live.py --push
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_world_globe import resolve_campaign_region_ids
from build_kml_superoverlay import handoff_pixels_for_bounds, merge_variant_config, overview_link_lod_band
from campaign_tier_lod import CAMPAIGN_PACKAGE_NAME, KML_NS, migrate_to_campaign_package
from globe_placement import layer_by_id, layer_earth_bounds, load_globe_config
from package_wargame_client import campaign_dir_for_variant
from places_hierarchy import (
    MAJOR_ISLANDS_FOLDER,
    MINOR_ISLES_FOLDER,
    bucket_regions_by_parent,
    core_parent_ids,
    make_folder,
    parent_label,
    places_hierarchy_enabled,
)
from campaign_session import append_unit_palettes_folder, load_session
from quick_view import append_document_planet_look_at, append_quick_view_bookmarks

ET.register_namespace("", KML_NS)

LIVE_DOC_NAME = "Campaign Live (EDIT HERE)"


def _kml(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def _append_region(parent: ET.Element, bounds: tuple[float, float, float, float], min_lod: int) -> None:
    west, south, east, north = bounds
    region = ET.SubElement(parent, _kml("Region"))
    box = ET.SubElement(region, _kml("LatLonAltBox"))
    ET.SubElement(box, _kml("north")).text = f"{north:.8f}"
    ET.SubElement(box, _kml("south")).text = f"{south:.8f}"
    ET.SubElement(box, _kml("east")).text = f"{east:.8f}"
    ET.SubElement(box, _kml("west")).text = f"{west:.8f}"
    lod = ET.SubElement(region, _kml("Lod"))
    ET.SubElement(lod, _kml("minLodPixels")).text = str(min_lod)


def _collapse_folder_tree(element: ET.Element) -> None:
    if element.tag == _kml("Folder"):
        open_el = element.find(_kml("open"))
        if open_el is None:
            open_el = ET.SubElement(element, _kml("open"))
        open_el.text = "0"
    for child in element:
        _collapse_folder_tree(child)


def _theater_payload_from_file(path: Path) -> list[ET.Element]:
    root = ET.parse(path).getroot()
    migrate_to_campaign_package(root)
    document = root.find(_kml("Document"))
    if document is None:
        return []
    package = None
    for child in document:
        if child.tag == _kml("Folder"):
            name_el = child.find(_kml("name"))
            if name_el is not None and (name_el.text or "") == CAMPAIGN_PACKAGE_NAME:
                package = child
                break
    if package is None:
        return [copy.deepcopy(child) for child in document if child.tag in {_kml("Folder"), _kml("Placemark")}]
    return [copy.deepcopy(package)]


def _append_theater_folder(
    parent: ET.Element,
    *,
    region_id: str,
    label: str,
    bounds: tuple[float, float, float, float],
    link_min: int,
    campaign_dir: Path,
) -> bool:
    path = campaign_dir / f"{region_id}.kml"
    if not path.exists():
        return False
    theater = ET.SubElement(parent, _kml("Folder"))
    ET.SubElement(theater, _kml("name")).text = label
    ET.SubElement(theater, _kml("description")).text = (
        f"Editable theater — syncs to campaign/{region_id}.kml"
    )
    ET.SubElement(theater, _kml("open")).text = "0"
    _append_region(theater, bounds, link_min)
    for payload in _theater_payload_from_file(path):
        _collapse_folder_tree(payload)
        theater.append(payload)
    return True


def build_campaign_live_kml(
    project_root: Path,
    *,
    variant: str = "wowcommanderalpha",
    output: Path | None = None,
) -> Path:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, variant)
    variant_cfg = (base.get("world_variants", {}) or {}).get(variant, {})
    campaign_dir = campaign_dir_for_variant(project_root, variant)
    world_parent = project_root / Path(variant_cfg.get("output", "03-kml/wowcommanderalpha/doc.kml")).parent
    out = output or (world_parent / "campaign_live.kml")

    kml = ET.Element(_kml("kml"))
    document = ET.SubElement(kml, _kml("Document"))
    ET.SubElement(document, _kml("name")).text = LIVE_DOC_NAME
    append_document_planet_look_at(document, config)
    ET.SubElement(document, _kml("description")).text = (
        "Editable campaign markers for Google Earth Pro. Add placemarks here — not under "
        "Campaign Board NetworkLinks in doc.kml (those are read-only). After editing: "
        "File → Save, then python3 scripts/sync_campaign_live.py --push and refresh "
        "Campaign Board links in doc.kml."
    )
    ET.SubElement(document, _kml("open")).text = "0"

    live_board = make_folder(document, "Campaign Package (live)", open_default=0)
    region_ids = resolve_campaign_region_ids(config, variant_cfg)
    count = 0

    if places_hierarchy_enabled(config):
        buckets = bucket_regions_by_parent(region_ids, config)
        for parent_id in core_parent_ids(config):
            continent_folder = make_folder(
                live_board,
                parent_label(config, parent_id),
                open_default=0,
            )
            for region_id in buckets[parent_id]["continent"]:
                layer = layer_by_id(config, region_id)
                if not layer:
                    continue
                label = layer.get("label", region_id)
                bounds = layer_earth_bounds(layer, config)
                handoff = handoff_pixels_for_bounds(bounds, config)
                link_min, _ = overview_link_lod_band(layer, handoff, config)
                if _append_theater_folder(
                    continent_folder,
                    region_id=region_id,
                    label=label,
                    bounds=bounds,
                    link_min=link_min,
                    campaign_dir=campaign_dir,
                ):
                    count += 1
            major_folder = make_folder(
                continent_folder,
                MAJOR_ISLANDS_FOLDER,
                open_default=0,
            )
            for region_id in buckets[parent_id]["major"]:
                layer = layer_by_id(config, region_id)
                if not layer:
                    continue
                label = layer.get("label", region_id)
                bounds = layer_earth_bounds(layer, config)
                handoff = handoff_pixels_for_bounds(bounds, config)
                link_min, _ = overview_link_lod_band(layer, handoff, config)
                if _append_theater_folder(
                    major_folder,
                    region_id=region_id,
                    label=label,
                    bounds=bounds,
                    link_min=link_min,
                    campaign_dir=campaign_dir,
                ):
                    count += 1
            minor_folder = make_folder(
                continent_folder,
                MINOR_ISLES_FOLDER,
                open_default=0,
            )
            for region_id in buckets[parent_id]["minor"]:
                layer = layer_by_id(config, region_id)
                if not layer:
                    continue
                label = layer.get("label", region_id)
                bounds = layer_earth_bounds(layer, config)
                handoff = handoff_pixels_for_bounds(bounds, config)
                link_min, _ = overview_link_lod_band(layer, handoff, config)
                if _append_theater_folder(
                    minor_folder,
                    region_id=region_id,
                    label=label,
                    bounds=bounds,
                    link_min=link_min,
                    campaign_dir=campaign_dir,
                ):
                    count += 1
    else:
        for region_id in region_ids:
            layer = layer_by_id(config, region_id)
            if not layer:
                continue
            label = layer.get("label", region_id)
            bounds = layer_earth_bounds(layer, config)
            handoff = handoff_pixels_for_bounds(bounds, config)
            link_min, _ = overview_link_lod_band(layer, handoff, config)
            if _append_theater_folder(
                live_board,
                region_id=region_id,
                label=label,
                bounds=bounds,
                link_min=link_min,
                campaign_dir=campaign_dir,
            ):
                count += 1

    append_quick_view_bookmarks(document, config)

    session = load_session(project_root, variant=variant)
    if session:
        append_unit_palettes_folder(document, project_root, session)

    tree = ET.ElementTree(kml)
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    print(f"  campaign_live.kml: {count} theaters → {out}")
    return out


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build editable campaign_live.kml")
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    build_campaign_live_kml(project_root, variant=args.variant, output=args.output)


if __name__ == "__main__":
    main()
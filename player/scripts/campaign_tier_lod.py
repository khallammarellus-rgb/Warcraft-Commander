"""Campaign tier LOD helpers — editable folders, Region on placemarks."""

from __future__ import annotations

import copy
from pathlib import Path
from xml.etree import ElementTree as ET

KML_NS = "http://www.opengis.net/kml/2.2"
ET.register_namespace("", KML_NS)

CAMPAIGN_PACKAGE_NAME = "Campaign Package"
CAMPAIGN_TIER_NAMES = frozenset({"Strategic", "Operational", "Tactical"})
FACTION_FOLDER_NAMES = frozenset({"red-cell", "blue-cell", "white-cell"})
DISCOVERED_FOLDER_NAMES = frozenset({"redcell-discovered", "bluecell-discovered"})

# (name, description, minLodPixels, maxLodPixels)
CAMPAIGN_TIER_SPECS: tuple[tuple[str, str, int, int], ...] = (
    (
        "Strategic",
        "HQ, regiment, division, army — visible at planet scale (~6000–3000 mi eye altitude).",
        0,
        700,
    ),
    (
        "Operational",
        "Platoon through battalion — visible at continent scale (~2000–1000 mi).",
        500,
        3000,
    ),
    (
        "Tactical",
        "Squad and below — visible below ~500 mi eye altitude.",
        6000,
        -1,
    ),
)


def _kml(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def tier_lod_for_name(name: str) -> tuple[int, int] | None:
    for tier_name, _, min_lod, max_lod in CAMPAIGN_TIER_SPECS:
        if tier_name == name:
            return min_lod, max_lod
    return None


def _append_named_folder(
    parent: ET.Element,
    name: str,
    description: str,
    *,
    open_folder: bool = True,
) -> ET.Element:
    folder = ET.SubElement(parent, _kml("Folder"))
    ET.SubElement(folder, _kml("name")).text = name
    ET.SubElement(folder, _kml("description")).text = description
    if open_folder:
        ET.SubElement(folder, _kml("open")).text = "1"
    return folder


def append_campaign_tier_folders(parent: ET.Element) -> None:
    """Plain editable tier folders — no Region (GEP greys out Region-gated folders)."""
    for name, description, _min_lod, _max_lod in CAMPAIGN_TIER_SPECS:
        _append_named_folder(parent, name, description)


def append_campaign_package_folder(document: ET.Element) -> ET.Element:
    """
    Campaign Package — copy into any theater campaign file.

    red-cell / blue-cell / white-cell each carry Strategic / Operational / Tactical.
    white-cell also has redcell-discovered and bluecell-discovered for manual reveal.
    """
    package = _append_named_folder(
        document,
        CAMPAIGN_PACKAGE_NAME,
        "Faction and tier folders for this theater. Place each unit in one tier folder "
        "under red-cell or blue-cell. White-cell uses discovered folders for manual reveal.",
    )
    factions = (
        ("red-cell", "Red force — place friendly units and graphics here."),
        ("blue-cell", "Blue force — place friendly units and graphics here."),
        ("white-cell", "White cell / referee — adjudication markers and discovered enemy."),
    )
    discovered = (
        ("redcell-discovered", "Enemy markers red-cell is allowed to see (referee reveal)."),
        ("bluecell-discovered", "Enemy markers blue-cell is allowed to see (referee reveal)."),
    )
    for faction_name, faction_desc in factions:
        faction = _append_named_folder(package, faction_name, faction_desc)
        append_campaign_tier_folders(faction)
        if faction_name == "white-cell":
            for disc_name, disc_desc in discovered:
                _append_named_folder(faction, disc_name, disc_desc)
    return package


def _folder_named(parent: ET.Element, name: str) -> ET.Element | None:
    for child in parent:
        if child.tag != _kml("Folder"):
            continue
        name_el = child.find(_kml("name"))
        if name_el is not None and (name_el.text or "") == name:
            return child
    return None


def migrate_to_campaign_package(root: ET.Element) -> int:
    """Replace legacy top-level tier folders with Campaign Package tree."""
    document = root.find(_kml("Document"))
    if document is None:
        return 0
    if _folder_named(document, CAMPAIGN_PACKAGE_NAME) is not None:
        return 0
    for folder in document.findall(f".//{_kml('Folder')}"):
        name_el = folder.find(_kml("name"))
        if name_el is not None and (name_el.text or "") == CAMPAIGN_PACKAGE_NAME:
            return 0

    preserved: list[tuple[str, ET.Element]] = []
    remove: list[ET.Element] = []
    for child in list(document):
        if child.tag != _kml("Folder"):
            continue
        name_el = child.find(_kml("name"))
        if name_el is None or (name_el.text or "") not in CAMPAIGN_TIER_NAMES:
            continue
        tier = name_el.text or ""
        for placemark in child.findall(_kml("Placemark")):
            preserved.append((tier, copy.deepcopy(placemark)))
        remove.append(child)
    for child in remove:
        document.remove(child)

    name_el = document.find(_kml("name"))
    label = (name_el.text or "Theater").replace(" campaign", "")
    desc_el = document.find(_kml("description"))
    if desc_el is not None:
        desc_el.text = (
            f"Turn state for {label}. Use Campaign Package → red-cell or blue-cell → "
            "one tier per marker (Strategic / Operational / Tactical)."
        )

    package = append_campaign_package_folder(document)
    red_cell = _folder_named(package, "red-cell")
    if red_cell is not None:
        for tier, placemark in preserved:
            tier_folder = _folder_named(red_cell, tier)
            if tier_folder is not None:
                tier_folder.append(placemark)
    return 1


def strip_tier_folder_regions(root: ET.Element) -> int:
    """Remove Region from Strategic/Operational/Tactical folders; return change count."""
    changed = 0
    for folder in root.iter(_kml("Folder")):
        name_el = folder.find(_kml("name"))
        if name_el is None or (name_el.text or "") not in CAMPAIGN_TIER_NAMES:
            continue
        region = folder.find(_kml("Region"))
        if region is not None:
            folder.remove(region)
            changed += 1
        open_el = folder.find(_kml("open"))
        if open_el is None:
            ET.SubElement(folder, _kml("open")).text = "1"
            changed += 1
        elif open_el.text != "1":
            open_el.text = "1"
            changed += 1
    return changed


def _append_region_lod(parent: ET.Element, min_lod: int, max_lod: int) -> None:
    region = ET.SubElement(parent, _kml("Region"))
    lod = ET.SubElement(region, _kml("Lod"))
    ET.SubElement(lod, _kml("minLodPixels")).text = str(min_lod)
    ET.SubElement(lod, _kml("maxLodPixels")).text = str(max_lod)


def inject_placemark_tier_regions(root: ET.Element) -> int:
    """Add Region/Lod to placemarks under tier folders that lack one."""
    changed = 0

    def walk(element: ET.Element, active_tier: str | None) -> None:
        nonlocal changed
        tag = element.tag
        if tag == _kml("Folder"):
            name_el = element.find(_kml("name"))
            name = (name_el.text or "") if name_el is not None else ""
            tier = name if name in CAMPAIGN_TIER_NAMES else active_tier
            for child in element:
                walk(child, tier)
            return
        if tag == _kml("Placemark") and active_tier:
            if element.find(_kml("Region")) is None:
                lod = tier_lod_for_name(active_tier)
                if lod is not None:
                    _append_region_lod(element, lod[0], lod[1])
                    changed += 1
            return
        for child in element:
            walk(child, active_tier)

    for child in root:
        walk(child, None)
    return changed


def write_campaign_package_template(out_path: Path) -> Path:
    """Write standalone Campaign Package template for copy-into-theater use."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kml = ET.Element(_kml("kml"))
    document = ET.SubElement(kml, _kml("Document"))
    ET.SubElement(document, _kml("name")).text = "Campaign Package (template)"
    ET.SubElement(document, _kml("description")).text = (
        "Copy the Campaign Package folder into a theater campaign file "
        "(e.g. kalimdor.kml), or run python3 scripts/sync_campaign_tier_lod.py "
        "to migrate all theater shells automatically."
    )
    append_campaign_package_folder(document)
    tree = ET.ElementTree(kml)
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


def prepare_campaign_kml_xml(path) -> str:
    """Read campaign KML, migrate package layout, strip folder Regions, inject LOD."""
    root = ET.parse(path).getroot()
    migrate_to_campaign_package(root)
    strip_tier_folder_regions(root)
    inject_placemark_tier_regions(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    )
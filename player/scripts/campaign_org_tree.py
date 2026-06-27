"""Org-folder scaffolds and order placemarks for campaign setup."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from campaign_hq import FORCE_SPECS, hq_name
from campaign_tier_lod import CAMPAIGN_TIER_NAMES, KML_NS

SCAFFOLD_MARKER = "WOW-SETUP-SCAFFOLD"
ORDERS_FOLDER = "Orders"
CASUAL_UNITS_FOLDER = "Units"
CASUAL_GRAPHICS_FOLDER = "Operational Graphics"
TACTICIAN_GRAPHICS_FOLDER = "Operational Graphics"

COMPANY_LABELS = ("A Co", "B Co", "C Co", "D Co")
PLATOON_LABELS = ("1st Plt", "2nd Plt", "3rd Plt")
SQUAD_LABELS = ("1st Sqd", "2nd Sqd", "3rd Sqd")
BATTALION_LABELS = ("1st Bn", "2nd Bn", "3rd Bn")
BRIGADE_LABELS = ("1st Bde", "2nd Bde", "3rd Bde")
DIVISION_LABELS = ("1st Div", "2nd Div", "3rd Div")


def _kml(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def _scaffold_description(purpose: str) -> str:
    return f"{SCAFFOLD_MARKER} — {purpose}"


def _folder(name: str, description: str, *, open_folder: bool = True) -> ET.Element:
    folder = ET.Element(_kml("Folder"))
    ET.SubElement(folder, _kml("name")).text = name
    ET.SubElement(folder, _kml("description")).text = _scaffold_description(description)
    if open_folder:
        ET.SubElement(folder, _kml("open")).text = "1"
    return folder


def _append_children(parent: ET.Element, names: tuple[str, ...], purpose: str) -> None:
    for name in names:
        parent.append(_folder(name, purpose))


def _org_root_name(force_size: str, force_name: str) -> str:
    if force_size == "army" and force_name.strip():
        return force_name.strip()
    spec = FORCE_SPECS.get(force_size, FORCE_SPECS["battalion"])
    prefix = spec["hq_prefix"]
    abbrev = spec["abbrev"]
    if force_size == "company":
        return f"{prefix} {abbrev}"
    return f"{prefix}{abbrev}"


def casual_tier_scaffold(tier_name: str) -> ET.Element:
    """Units + Operational Graphics under one tier folder (Casual)."""
    root = ET.Element(_kml("Folder"))
    ET.SubElement(root, _kml("name")).text = tier_name
    ET.SubElement(root, _kml("description")).text = _scaffold_description(
        f"Casual laydown folders for {tier_name} tier."
    )
    ET.SubElement(root, _kml("open")).text = "1"
    root.append(
        _folder(
            CASUAL_UNITS_FOLDER,
            f"Place {tier_name.lower()}-tier unit placemarks here.",
        )
    )
    root.append(
        _folder(
            CASUAL_GRAPHICS_FOLDER,
            f"Boundaries, axes, phase lines, and other graphics ({tier_name}).",
        )
    )
    return root


def tactician_org_scaffold(force_size: str, *, force_name: str) -> ET.Element:
    """Echelon folder tree rooted at the commander's level (Tactician)."""
    root_name = _org_root_name(force_size, force_name)
    root = _folder(
        root_name,
        f"Command echelon root for {force_size}. Place HQ here; subordinates in child folders.",
    )

    if force_size == "platoon":
        _append_children(root, SQUAD_LABELS, "Squad-level markers (tactical).")
    elif force_size == "company":
        _append_children(root, PLATOON_LABELS, "Platoon markers under this company.")
    elif force_size == "battalion":
        _append_children(root, COMPANY_LABELS, "Company markers under this battalion.")
    elif force_size == "regiment":
        for bn in BATTALION_LABELS:
            bn_folder = _folder(bn, f"{bn} — place companies inside.")
            _append_children(bn_folder, COMPANY_LABELS, f"Companies under {bn}.")
            root.append(bn_folder)
    elif force_size == "division":
        for bde in BRIGADE_LABELS:
            bde_folder = _folder(bde, f"{bde} — battalions and companies inside.")
            for bn in BATTALION_LABELS:
                bn_folder = _folder(bn, f"{bn} under {bde}.")
                _append_children(bn_folder, COMPANY_LABELS, f"Companies under {bn}.")
                bde_folder.append(bn_folder)
            root.append(bde_folder)
    elif force_size == "army":
        for div in DIVISION_LABELS:
            div_folder = _folder(div, f"{div} — brigades and battalions inside.")
            for bde in BRIGADE_LABELS:
                bde_folder = _folder(bde, f"{bde} under {div}.")
                for bn in BATTALION_LABELS:
                    bde_folder.append(_folder(bn, f"{bn} under {bde}."))
                div_folder.append(bde_folder)
            root.append(div_folder)

    root.append(
        _folder(
            TACTICIAN_GRAPHICS_FOLDER,
            "Boundaries, axes, phase lines, and other operational graphics.",
        )
    )
    return root


def is_scaffold_folder(folder: ET.Element) -> bool:
    if folder.tag != _kml("Folder"):
        return False
    desc_el = folder.find(_kml("description"))
    text = (desc_el.text or "") if desc_el is not None else ""
    return text.startswith(SCAFFOLD_MARKER)


def remove_scaffold_folders(parent: ET.Element) -> None:
    """Drop wizard-injected org scaffolds; preserve player folders and markers."""
    for child in list(parent):
        if child.tag != _kml("Folder"):
            continue
        if is_scaffold_folder(child):
            parent.remove(child)
            continue
        remove_scaffold_folders(child)


def inject_org_tree(
    cell_folder: ET.Element,
    *,
    knowledge_level: str,
    force_size: str,
    force_name: str,
    hq_tier_name: str,
) -> ET.Element:
    """
    Replace setup scaffolds under the player cell and return the HQ parent folder.

    Casual: Units/ + Operational Graphics/ in every tier.
    Tactician: echelon tree in the HQ tier only.
    """
    remove_scaffold_folders(cell_folder)

    hq_parent: ET.Element | None = None

    if knowledge_level == "casual":
        for tier_name in CAMPAIGN_TIER_NAMES:
            tier_folder = _folder_named(cell_folder, tier_name)
            if tier_folder is None:
                continue
            scaffold = casual_tier_scaffold(tier_name)
            for child in list(scaffold):
                if child.tag == _kml("Folder"):
                    tier_folder.append(child)
            if tier_name == hq_tier_name:
                units = _folder_named(tier_folder, CASUAL_UNITS_FOLDER)
                hq_parent = units if units is not None else tier_folder
    else:
        tier_folder = _folder_named(cell_folder, hq_tier_name)
        if tier_folder is not None:
            org = tactician_org_scaffold(force_size, force_name=force_name)
            tier_folder.append(org)
            hq_parent = org

    return hq_parent or _folder_named(cell_folder, hq_tier_name) or cell_folder


def _folder_named(parent: ET.Element, name: str) -> ET.Element | None:
    for child in parent:
        if child.tag != _kml("Folder"):
            continue
        name_el = child.find(_kml("name"))
        if name_el is not None and (name_el.text or "") == name:
            return child
    return None


def _offset_coords(coords: tuple[float, float], *, lon_delta: float = 0.0, lat_delta: float = 0.0) -> tuple[float, float]:
    lon, lat = coords
    return lon + lon_delta, lat + lat_delta


def build_order_placemark(
    *,
    name: str,
    body: str,
    coords: tuple[float, float],
    style_id: str = "wow-order-doc",
) -> ET.Element:
    pm = ET.Element(_kml("Placemark"))
    ET.SubElement(pm, _kml("name")).text = name
    ET.SubElement(pm, _kml("description")).text = body.strip()
    ET.SubElement(pm, _kml("styleUrl")).text = f"#{style_id}"
    point = ET.SubElement(pm, _kml("Point"))
    lon, lat = coords
    ET.SubElement(point, _kml("coordinates")).text = f"{lon:.6f},{lat:.6f},0"
    return pm


def build_order_document_style() -> ET.Element:
    style = ET.Element(_kml("Style"))
    style.set("id", "wow-order-doc")
    icon_style = ET.SubElement(style, _kml("IconStyle"))
    ET.SubElement(icon_style, _kml("scale")).text = "1.1"
    icon = ET.SubElement(icon_style, _kml("Icon"))
    ET.SubElement(icon, _kml("href")).text = (
        "http://maps.google.com/mapfiles/kml/paddle/wht-stars.png"
    )
    label = ET.SubElement(style, _kml("LabelStyle"))
    ET.SubElement(label, _kml("scale")).text = "0.9"
    return style


def build_orders_folder(
    *,
    commander_name: str,
    force_name: str,
    force_size: str,
    coords: tuple[float, float],
    warn_o: str | None,
    operation_order: str | None,
) -> ET.Element | None:
    if not (warn_o or operation_order):
        return None

    folder = _folder(
        ORDERS_FOLDER,
        "Warning Order and Operation Order — open placemark description in Google Earth.",
        open_folder=True,
    )
    hq_label = hq_name(force_size, force_name=force_name)
    base_lon, base_lat = coords

    if warn_o and warn_o.strip():
        warn_coords = _offset_coords((base_lon, base_lat), lon_delta=-0.08, lat_delta=0.04)
        folder.append(
            build_order_placemark(
                name="Warn O",
                body=(
                    f"Warning Order — Commander {commander_name}, {force_name} ({hq_label})\n\n"
                    f"{warn_o.strip()}"
                ),
                coords=warn_coords,
            )
        )

    if operation_order and operation_order.strip():
        opord_coords = _offset_coords((base_lon, base_lat), lon_delta=0.08, lat_delta=-0.04)
        folder.append(
            build_order_placemark(
                name="OPORD",
                body=(
                    f"Operation Order — Commander {commander_name}, {force_name} ({hq_label})\n\n"
                    f"{operation_order.strip()}"
                ),
                coords=opord_coords,
            )
        )

    return folder


def remove_orders_folder(cell_folder: ET.Element) -> None:
    for child in list(cell_folder):
        if child.tag != _kml("Folder"):
            continue
        name_el = child.find(_kml("name"))
        if name_el is not None and (name_el.text or "") == ORDERS_FOLDER:
            cell_folder.remove(child)
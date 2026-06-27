"""game_session.json I/O and KML injection for campaign setup."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from build_kml_superoverlay import merge_variant_config
from campaign_hq import build_hq_placemark, build_hq_style, hq_tier, theater_center
from campaign_org_tree import (
    build_order_document_style,
    build_orders_folder,
    inject_org_tree,
    remove_orders_folder,
)
from campaign_tier_lod import CAMPAIGN_PACKAGE_NAME, KML_NS, append_campaign_package_folder, migrate_to_campaign_package
from faction_library import UNIT_PALETTES_FOLDER, build_palette_folder, faction_by_id
from globe_placement import layer_by_id, load_globe_config
from package_wargame_client import campaign_dir_for_variant

SESSION_FILENAME = "game_session.json"


def _kml(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def session_path(project_root: Path, *, variant: str = "wowcommanderalpha") -> Path:
    return campaign_dir_for_variant(project_root, variant) / SESSION_FILENAME


def load_session(project_root: Path, *, variant: str = "wowcommanderalpha") -> dict | None:
    path = session_path(project_root, variant=variant)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(project_root: Path, session: dict, *, variant: str = "wowcommanderalpha") -> Path:
    path = session_path(project_root, variant=variant)
    path.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return path


def _folder_named(parent: ET.Element, name: str) -> ET.Element | None:
    for child in parent:
        if child.tag != _kml("Folder"):
            continue
        name_el = child.find(_kml("name"))
        if name_el is not None and (name_el.text or "") == name:
            return child
    return None


def _remove_hq_placemarks(folder: ET.Element) -> None:
    for child in list(folder):
        if child.tag == _kml("Placemark"):
            name_el = child.find(_kml("name"))
            if name_el is not None and " HQ " in (name_el.text or ""):
                folder.remove(child)
        elif child.tag == _kml("Folder"):
            _remove_hq_placemarks(child)


def _ensure_order_style(package: ET.Element) -> None:
    style_id = "wow-order-doc"
    for old in list(package.findall(_kml("Style"))):
        if old.get("id") == style_id:
            package.remove(old)
    package.insert(0, build_order_document_style())


def inject_hq_into_theater_kml(project_root: Path, session: dict, *, variant: str = "wowcommanderalpha") -> Path:
    """Write HQ, org scaffold, orders, and styles into campaign/<theater>.kml."""
    theater_id = session["theater"]
    campaign_dir = campaign_dir_for_variant(project_root, variant)
    path = campaign_dir / f"{theater_id}.kml"

    if path.exists():
        root = ET.parse(path).getroot()
    else:
        base = load_globe_config(project_root)
        config = merge_variant_config(base, variant)
        layer = layer_by_id(config, theater_id)
        label = layer.get("label", theater_id) if layer else theater_id
        root = ET.Element(_kml("kml"))
        document = ET.SubElement(root, _kml("Document"))
        ET.SubElement(document, _kml("name")).text = f"{label} campaign"
        append_campaign_package_folder(document)

    migrate_to_campaign_package(root)
    document = root.find(_kml("Document"))
    if document is None:
        raise ValueError(f"Invalid campaign file: {path}")

    package = _folder_named(document, CAMPAIGN_PACKAGE_NAME)
    if package is None:
        package = append_campaign_package_folder(document)

    cell = session["player_cell"]
    cell_folder = _folder_named(package, cell)
    if cell_folder is None:
        raise ValueError(f"Missing {cell} in Campaign Package")

    tier_name = hq_tier(session["force_size"])
    tier_folder = _folder_named(cell_folder, tier_name)
    if tier_folder is None:
        raise ValueError(f"Missing tier {tier_name} under {cell}")

    _remove_hq_placemarks(cell_folder)
    remove_orders_folder(cell_folder)

    primary_id = session["primary_faction"]
    primary = faction_by_id(project_root, primary_id)
    primary_label = primary["label"] if primary else primary_id
    coords = tuple(session.get("hq_coords") or theater_center(project_root, theater_id))

    for old_style in list(package.findall(_kml("Style"))):
        style_id = old_style.get("id", "")
        if style_id.startswith("faction-") or style_id == "wow-order-doc":
            package.remove(old_style)
    for old_style in list(document.findall(_kml("Style"))):
        style_id = old_style.get("id", "")
        if style_id.startswith("faction-") or style_id == "wow-order-doc":
            document.remove(old_style)

    style = build_hq_style(project_root, primary_id)
    if style is not None:
        package.insert(0, style)

    knowledge_level = session.get("knowledge_level", "casual")
    hq_parent = inject_org_tree(
        cell_folder,
        knowledge_level=knowledge_level,
        force_size=session["force_size"],
        force_name=session["force_name"],
        hq_tier_name=tier_name,
    )

    orders = build_orders_folder(
        commander_name=session["commander_name"],
        force_name=session["force_name"],
        force_size=session["force_size"],
        coords=coords,
        warn_o=session.get("warn_o"),
        operation_order=session.get("operation_order"),
    )
    if orders is not None:
        _ensure_order_style(package)
        cell_folder.insert(0, orders)

    pm = build_hq_placemark(
        project_root,
        commander_name=session["commander_name"],
        force_name=session["force_name"],
        force_size=session["force_size"],
        primary_faction_id=primary_id,
        primary_faction_label=primary_label,
        coords=coords,
    )
    hq_parent.append(pm)

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return path


def append_unit_palettes_folder(document: ET.Element, project_root: Path, session: dict) -> None:
    """Inject or replace Unit palettes/ at Document level in campaign_live."""
    for child in list(document):
        if child.tag != _kml("Folder"):
            continue
        name_el = child.find(_kml("name"))
        if name_el is not None and (name_el.text or "") == UNIT_PALETTES_FOLDER:
            document.remove(child)

    palettes = ET.SubElement(document, _kml("Folder"))
    ET.SubElement(palettes, _kml("name")).text = UNIT_PALETTES_FOLDER
    ET.SubElement(palettes, _kml("description")).text = (
        "Editor-only faction icon styles. Not synced to campaign files or turn exports. "
        "Copy placemark styles when adding units under your cell folder."
    )
    ET.SubElement(palettes, _kml("open")).text = "0"

    for faction_id in session.get("factions", []):
        folder = build_palette_folder(project_root, faction_id)
        if folder is not None:
            palettes.append(copy.deepcopy(folder))


def finalize_session(project_root: Path, session: dict, *, variant: str = "wowcommanderalpha") -> None:
    """Persist session, inject HQ into theater file, rebuild campaign_live."""
    from build_campaign_live import build_campaign_live_kml

    save_session(project_root, session, variant=variant)
    inject_hq_into_theater_kml(project_root, session, variant=variant)
    build_campaign_live_kml(project_root, variant=variant)
"""
Fog-of-war and blind-mode filtering for campaign turn exports.

Google Earth Pro cannot hide folders at runtime — each player receives a filtered
KMZ built from the shared master campaign/*.kml on disk.

Revealed enemy intel is copied into white-cell discovered folders (auto/ for
proximity/scout, root for manual referee injects). Blind players never see live
opponent positions — only merged discovered copies.
"""

from __future__ import annotations

import copy
import json
import math
import re
from pathlib import Path
from xml.etree import ElementTree as ET

from campaign_tier_lod import (
    CAMPAIGN_PACKAGE_NAME,
    DISCOVERED_AUTO_FOLDER_NAME,
    DISCOVERED_FOLDER_NAMES,
    FACTION_FOLDER_NAMES,
    KML_NS,
    ensure_discovered_auto_folders,
)

GAME_FORMATS = frozenset({"no-blind", "single-blind", "double-blind"})
VIEWER_ROLES = frozenset({"red-cell", "blue-cell", "white-cell"})
OPPONENT = {"red-cell": "blue-cell", "blue-cell": "red-cell"}

DEFAULT_SCOUT_KEYWORDS = (
    "scout",
    "recon",
    "reconnaissance",
    "pathfinder",
    "sniper",
    "spy",
)

DEFAULT_META = {
    "game_format": "no-blind",
    "reveal_radius_km": 5.0,
    "scout_radius_km": 10.0,
    "scout_keywords": list(DEFAULT_SCOUT_KEYWORDS),
    "reveal_persistent": True,
}

SOURCE_KEY_PREFIX = "wowcmd:source_key="


def _kml(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def meta_path(campaign_dir: Path) -> Path:
    return campaign_dir / "campaign_meta.json"


def reveal_state_path(campaign_dir: Path) -> Path:
    return campaign_dir / "reveal_state.json"


def load_campaign_meta(campaign_dir: Path) -> dict:
    path = meta_path(campaign_dir)
    if not path.exists():
        return dict(DEFAULT_META)
    data = json.loads(path.read_text(encoding="utf-8"))
    merged = dict(DEFAULT_META)
    merged.update(data)
    if not merged.get("scout_keywords"):
        merged["scout_keywords"] = list(DEFAULT_SCOUT_KEYWORDS)
    return merged


def load_reveal_state(campaign_dir: Path) -> dict:
    path = reveal_state_path(campaign_dir)
    if not path.exists():
        return {"turn": 0, "positions": {}, "reveals": {"red_sees_blue": [], "blue_sees_red": []}}
    return json.loads(path.read_text(encoding="utf-8"))


def save_reveal_state(campaign_dir: Path, state: dict) -> None:
    reveal_state_path(campaign_dir).write_text(
        json.dumps(state, indent=2) + "\n", encoding="utf-8"
    )


def placemark_path_key(parts: list[str]) -> str:
    return "/".join(parts)


def placemark_coords(placemark: ET.Element) -> tuple[float, float] | None:
    coords_el = placemark.find(f".//{_kml('coordinates')}")
    if coords_el is None or not (coords_el.text or "").strip():
        return None
    first = (coords_el.text or "").strip().split()[0]
    bits = first.split(",")
    if len(bits) < 2:
        return None
    try:
        return float(bits[0]), float(bits[1])
    except ValueError:
        return None


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _folder_named(parent: ET.Element, name: str) -> ET.Element | None:
    for child in parent:
        if child.tag != _kml("Folder"):
            continue
        name_el = child.find(_kml("name"))
        if name_el is not None and (name_el.text or "") == name:
            return child
    return None


def _campaign_package(document: ET.Element) -> ET.Element | None:
    return _folder_named(document, CAMPAIGN_PACKAGE_NAME)


def _placemark_id(placemark: ET.Element) -> str:
    name_el = placemark.find(_kml("name"))
    if name_el is not None and (name_el.text or "").strip():
        return (name_el.text or "").strip()
    coords = placemark_coords(placemark)
    if coords is not None:
        return f"@{coords[0]:.5f},{coords[1]:.5f}"
    return "placemark"


def _placemark_label_text(placemark: ET.Element) -> str:
    parts: list[str] = []
    for tag in ("name", "description"):
        el = placemark.find(_kml(tag))
        if el is not None and (el.text or "").strip():
            parts.append(el.text or "")
    return " ".join(parts)


def _is_scout_unit(placemark: ET.Element, keywords: list[str]) -> bool:
    text = _placemark_label_text(placemark).lower()
    for keyword in keywords:
        if re.search(rf"\b{re.escape(keyword.lower())}\b", text):
            return True
    return False


def _iter_faction_placemarks(
    package: ET.Element,
    faction: str,
) -> list[tuple[str, ET.Element, tuple[float, float] | None]]:
    """All placemarks under a faction cell (any tier), with path keys."""
    faction_folder = _folder_named(package, faction)
    if faction_folder is None:
        return []
    results: list[tuple[str, ET.Element, tuple[float, float] | None]] = []

    def walk(folder: ET.Element, parts: list[str]) -> None:
        for child in folder:
            if child.tag == _kml("Folder"):
                name_el = child.find(_kml("name"))
                sub = (name_el.text or "") if name_el is not None else "folder"
                if sub in DISCOVERED_FOLDER_NAMES and faction == "white-cell":
                    walk(child, parts + [sub])
                elif sub not in DISCOVERED_FOLDER_NAMES or faction != "white-cell":
                    walk(child, parts + [sub])
            elif child.tag == _kml("Placemark"):
                key = placemark_path_key(parts + [_placemark_id(child)])
                results.append((key, child, placemark_coords(child)))

    walk(faction_folder, [faction])
    return results


def _proximity_mutual_reveals(
    red_units: list[tuple[str, ET.Element, tuple[float, float] | None]],
    blue_units: list[tuple[str, ET.Element, tuple[float, float] | None]],
    radius_km: float,
) -> tuple[set[str], set[str]]:
    red_sees_blue: set[str] = set()
    blue_sees_red: set[str] = set()
    for r_key, _r_pm, r_coords in red_units:
        if r_coords is None:
            continue
        for b_key, _b_pm, b_coords in blue_units:
            if b_coords is None:
                continue
            if haversine_km(r_coords[0], r_coords[1], b_coords[0], b_coords[1]) <= radius_km:
                red_sees_blue.add(b_key)
                blue_sees_red.add(r_key)
    return red_sees_blue, blue_sees_red


def _scout_one_way_reveals(
    scout_units: list[tuple[str, ET.Element, tuple[float, float] | None]],
    enemy_units: list[tuple[str, ET.Element, tuple[float, float] | None]],
    radius_km: float,
) -> set[str]:
    revealed: set[str] = set()
    for _s_key, _s_pm, s_coords in scout_units:
        if s_coords is None:
            continue
        for e_key, _e_pm, e_coords in enemy_units:
            if e_coords is None:
                continue
            if haversine_km(s_coords[0], s_coords[1], e_coords[0], e_coords[1]) <= radius_km:
                revealed.add(e_key)
    return revealed


def compute_reveals(
    red_units: list[tuple[str, ET.Element, tuple[float, float] | None]],
    blue_units: list[tuple[str, ET.Element, tuple[float, float] | None]],
    *,
    radius_km: float,
    scout_radius_km: float,
    scout_keywords: list[str],
) -> tuple[set[str], set[str]]:
    red_sees_blue, blue_sees_red = _proximity_mutual_reveals(red_units, blue_units, radius_km)

    red_scouts = [(k, pm, c) for k, pm, c in red_units if _is_scout_unit(pm, scout_keywords)]
    blue_scouts = [(k, pm, c) for k, pm, c in blue_units if _is_scout_unit(pm, scout_keywords)]

    red_sees_blue |= _scout_one_way_reveals(red_scouts, blue_units, scout_radius_km)
    blue_sees_red |= _scout_one_way_reveals(blue_scouts, red_units, scout_radius_km)
    return red_sees_blue, blue_sees_red


def _set_source_key(placemark: ET.Element, source_key: str) -> None:
    desc_el = placemark.find(_kml("description"))
    if desc_el is None:
        desc_el = ET.SubElement(placemark, _kml("description"))
    lines = [
        line
        for line in (desc_el.text or "").splitlines()
        if not line.strip().startswith(SOURCE_KEY_PREFIX)
    ]
    lines.append(f"{SOURCE_KEY_PREFIX}{source_key}")
    desc_el.text = "\n".join(lines).strip()


def _clear_auto_discovered_folder(discovered: ET.Element) -> None:
    auto = _folder_named(discovered, DISCOVERED_AUTO_FOLDER_NAME)
    if auto is None:
        return
    for child in list(auto):
        if child.tag == _kml("Placemark"):
            auto.remove(child)


def sync_discovered_copies(
    root: ET.Element,
    *,
    red_sees_blue: set[str],
    blue_sees_red: set[str],
) -> int:
    """
    Refresh auto/ copies under white-cell discovered folders.
    Manual placemarks at discovered-folder root are never touched.
    """
    document = root.find(_kml("Document"))
    package = _campaign_package(document) if document is not None else None
    if package is None:
        return 0

    ensure_discovered_auto_folders(root)
    white = _folder_named(package, "white-cell")
    if white is None:
        return 0

    red_units = _iter_faction_placemarks(package, "red-cell")
    blue_units = _iter_faction_placemarks(package, "blue-cell")
    red_by_key = {key: pm for key, pm, _ in red_units}
    blue_by_key = {key: pm for key, pm, _ in blue_units}

    changed = 0
    pairs = (
        ("redcell-discovered", red_sees_blue, blue_by_key),
        ("bluecell-discovered", blue_sees_red, red_by_key),
    )
    for discovered_name, reveal_keys, enemy_by_key in pairs:
        discovered = _folder_named(white, discovered_name)
        if discovered is None:
            continue
        auto = _folder_named(discovered, DISCOVERED_AUTO_FOLDER_NAME)
        if auto is None:
            continue
        _clear_auto_discovered_folder(discovered)
        for key in sorted(reveal_keys):
            source = enemy_by_key.get(key)
            if source is None:
                continue
            copied = copy.deepcopy(source)
            _set_source_key(copied, key)
            auto.append(copied)
            changed += 1
    return changed


def update_reveal_state_for_document(
    root: ET.Element,
    *,
    campaign_dir: Path,
    turn: int,
    radius_km: float,
    scout_radius_km: float,
    scout_keywords: list[str],
) -> dict:
    document = root.find(_kml("Document"))
    package = _campaign_package(document) if document is not None else None
    state = load_reveal_state(campaign_dir)
    if package is None:
        return state

    ensure_discovered_auto_folders(root)
    red_units = _iter_faction_placemarks(package, "red-cell")
    blue_units = _iter_faction_placemarks(package, "blue-cell")

    red_revealed, blue_revealed = compute_reveals(
        red_units,
        blue_units,
        radius_km=radius_km,
        scout_radius_km=scout_radius_km,
        scout_keywords=scout_keywords,
    )

    sync_discovered_copies(
        root,
        red_sees_blue=red_revealed,
        blue_sees_red=blue_revealed,
    )

    positions: dict[str, list[float]] = {}
    for key, _pm, coords in red_units + blue_units:
        if coords is not None:
            positions[key] = [coords[0], coords[1]]

    state["turn"] = turn
    state["positions"] = positions
    state["reveals"] = {
        "red_sees_blue": sorted(red_revealed),
        "blue_sees_red": sorted(blue_revealed),
    }
    save_reveal_state(campaign_dir, state)
    return state


def refresh_reveals_for_document(
    root: ET.Element,
    *,
    campaign_dir: Path,
    turn: int,
    meta: dict | None = None,
) -> dict:
    """Compute range-bound reveals, sync discovered auto copies, persist reveal_state."""
    cfg = meta or load_campaign_meta(campaign_dir)
    return update_reveal_state_for_document(
        root,
        campaign_dir=campaign_dir,
        turn=turn,
        radius_km=float(cfg.get("reveal_radius_km", 5.0)),
        scout_radius_km=float(cfg.get("scout_radius_km", 10.0)),
        scout_keywords=list(cfg.get("scout_keywords") or DEFAULT_SCOUT_KEYWORDS),
    )


def write_kml_root(path: Path, root: ET.Element) -> None:
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def apply_reveal_sync_to_theater(
    path: Path,
    *,
    campaign_dir: Path,
    turn: int | None = None,
) -> dict:
    """Recompute reveals on a theater master KML and save discovered auto copies."""
    from campaign_tier_lod import (
        inject_placemark_tier_regions,
        migrate_to_campaign_package,
        strip_tier_folder_regions,
    )

    meta = load_campaign_meta(campaign_dir)
    root = ET.parse(path).getroot()
    migrate_to_campaign_package(root)
    strip_tier_folder_regions(root)
    inject_placemark_tier_regions(root)

    state = load_reveal_state(campaign_dir)
    effective_turn = turn if turn is not None else int(state.get("turn", 0)) + 1
    state = refresh_reveals_for_document(
        root,
        campaign_dir=campaign_dir,
        turn=effective_turn,
        meta=meta,
    )
    write_kml_root(path, root)
    return state


def effective_format(game_format: str, viewer: str | None) -> str:
    if viewer is None:
        return "no-blind"
    return game_format


def viewer_sees_everything(game_format: str, viewer: str) -> bool:
    if viewer == "white-cell":
        return True
    if game_format == "no-blind":
        return True
    if game_format == "single-blind" and viewer == "red-cell":
        return True
    return False


def _remove_all_placemarks(folder: ET.Element) -> None:
    for child in list(folder):
        if child.tag == _kml("Placemark"):
            folder.remove(child)
        elif child.tag == _kml("Folder"):
            _remove_all_placemarks(child)


def _strip_faction(package: ET.Element, faction: str) -> None:
    target = _folder_named(package, faction)
    if target is not None:
        package.remove(target)


def _strip_live_opponent_placemarks(package: ET.Element, opponent: str) -> None:
    folder = _folder_named(package, opponent)
    if folder is None:
        return
    _remove_all_placemarks(folder)


def _filter_white_cell_for_viewer(package: ET.Element, viewer: str) -> None:
    white = _folder_named(package, "white-cell")
    if white is None:
        return
    keep_discovered = "redcell-discovered" if viewer == "red-cell" else "bluecell-discovered"
    for child in list(white):
        if child.tag == _kml("Placemark"):
            white.remove(child)
            continue
        if child.tag != _kml("Folder"):
            continue
        name_el = child.find(_kml("name"))
        name = (name_el.text or "") if name_el is not None else ""
        if name != keep_discovered:
            white.remove(child)


def filter_campaign_root(
    root: ET.Element,
    *,
    viewer: str | None,
    game_format: str,
    state: dict,
) -> ET.Element:
    """Return a copy of root filtered for viewer role and blind format."""
    del state  # reveals materialize as discovered copies; live opponent markers are stripped
    if viewer is None or viewer_sees_everything(game_format, viewer):
        return root

    filtered = copy.deepcopy(root)
    document = filtered.find(_kml("Document"))
    package = _campaign_package(document) if document is not None else None
    if package is None:
        return filtered

    if viewer == "red-cell":
        _strip_live_opponent_placemarks(package, "blue-cell")
        _filter_white_cell_for_viewer(package, "red-cell")
    elif viewer == "blue-cell":
        _strip_live_opponent_placemarks(package, "red-cell")
        _filter_white_cell_for_viewer(package, "blue-cell")

    return filtered


def _discovered_placemarks(package: ET.Element, folder_name: str) -> list[ET.Element]:
    white = _folder_named(package, "white-cell")
    if white is None:
        return []
    discovered = _folder_named(white, folder_name)
    if discovered is None:
        return []

    results: list[ET.Element] = []

    def collect(folder: ET.Element) -> None:
        for child in folder:
            if child.tag == _kml("Placemark"):
                results.append(child)
            elif child.tag == _kml("Folder"):
                collect(child)

    collect(discovered)
    return results


def merge_discovered_into_opponent_view(root: ET.Element, viewer: str) -> None:
    """
    Copy white-cell discovered placemarks (manual + auto/) into opponent faction folder.
    """
    document = root.find(_kml("Document"))
    package = _campaign_package(document) if document is not None else None
    if package is None:
        return

    if viewer == "red-cell":
        discovered_name, target_faction = "redcell-discovered", "blue-cell"
    elif viewer == "blue-cell":
        discovered_name, target_faction = "bluecell-discovered", "red-cell"
    else:
        return

    manual = _discovered_placemarks(package, discovered_name)
    if not manual:
        return

    target = _folder_named(package, target_faction)
    if target is None:
        return

    tactical = _folder_named(target, "Tactical")
    if tactical is None:
        tactical = target
    for pm in manual:
        tactical.append(copy.deepcopy(pm))


def prepare_view_kml_xml(
    path: Path,
    *,
    campaign_dir: Path,
    turn: int,
    viewer: str | None,
    game_format: str | None,
    radius_km: float | None,
    scout_radius_km: float | None,
    scout_keywords: list[str] | None,
    persistent: bool | None,
    save_master: bool = True,
) -> str:
    """Full pipeline: migrate, LOD, reveal state, blind filter."""
    from campaign_tier_lod import (
        inject_placemark_tier_regions,
        migrate_to_campaign_package,
        strip_tier_folder_regions,
    )

    meta = load_campaign_meta(campaign_dir)
    fmt = game_format or meta.get("game_format", "no-blind")
    if fmt not in GAME_FORMATS:
        fmt = "no-blind"
    radius = radius_km if radius_km is not None else float(meta.get("reveal_radius_km", 5.0))
    scout_radius = (
        scout_radius_km if scout_radius_km is not None else float(meta.get("scout_radius_km", 10.0))
    )
    keywords = scout_keywords or list(meta.get("scout_keywords") or DEFAULT_SCOUT_KEYWORDS)
    del persistent  # manual copies persist in discovered root; auto copies are range-bound

    root = ET.parse(path).getroot()
    migrate_to_campaign_package(root)
    strip_tier_folder_regions(root)
    inject_placemark_tier_regions(root)

    state = update_reveal_state_for_document(
        root,
        campaign_dir=campaign_dir,
        turn=turn,
        radius_km=radius,
        scout_radius_km=scout_radius,
        scout_keywords=keywords,
    )

    if save_master:
        write_kml_root(path, root)

    fmt = effective_format(fmt, viewer)
    filtered = filter_campaign_root(root, viewer=viewer, game_format=fmt, state=state)
    if viewer in VIEWER_ROLES and not viewer_sees_everything(fmt, viewer):
        merge_discovered_into_opponent_view(filtered, viewer)

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        filtered, encoding="unicode"
    )
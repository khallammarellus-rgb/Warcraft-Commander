"""
Fog-of-war and blind-mode filtering for campaign turn exports.

Google Earth Pro cannot hide folders at runtime — each player receives a filtered
KMZ built from the shared master campaign/*.kml on disk.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET

from campaign_tier_lod import (
    CAMPAIGN_PACKAGE_NAME,
    DISCOVERED_FOLDER_NAMES,
    FACTION_FOLDER_NAMES,
    KML_NS,
)

GAME_FORMATS = frozenset({"no-blind", "single-blind", "double-blind"})
VIEWER_ROLES = frozenset({"red-cell", "blue-cell", "white-cell"})
OPPONENT = {"red-cell": "blue-cell", "blue-cell": "red-cell"}

DEFAULT_META = {
    "game_format": "no-blind",
    "reveal_radius_km": 1.0,
    "reveal_persistent": True,
}


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


def _placemark_id(placemark: ET.Element) -> str:
    name_el = placemark.find(_kml("name"))
    if name_el is not None and (name_el.text or "").strip():
        return (name_el.text or "").strip()
    coords = placemark_coords(placemark)
    if coords is not None:
        return f"@{coords[0]:.5f},{coords[1]:.5f}"
    return "placemark"


def _discovered_placemarks(package: ET.Element, folder_name: str) -> list[ET.Element]:
    white = _folder_named(package, "white-cell")
    if white is None:
        return []
    discovered = _folder_named(white, folder_name)
    if discovered is None:
        return []
    return list(discovered.findall(_kml("Placemark")))


def _proximity_reveals(
    *,
    viewer_faction: str,
    own_units: list[tuple[str, ET.Element, tuple[float, float] | None]],
    enemy_units: list[tuple[str, ET.Element, tuple[float, float] | None]],
    state: dict,
    radius_km: float,
    persistent: bool,
) -> set[str]:
    opponent = OPPONENT[viewer_faction]
    reveal_key = "red_sees_blue" if viewer_faction == "red-cell" else "blue_sees_red"
    prev_positions: dict = state.get("positions", {})
    revealed: set[str] = set(state.get("reveals", {}).get(reveal_key, [])) if persistent else set()

    triggers: list[tuple[float, float]] = []
    for key, _pm, coords in own_units:
        if coords is None:
            continue
        prev = prev_positions.get(key)
        if prev is None or prev != [coords[0], coords[1]]:
            triggers.append(coords)

    for _key, _pm, enemy_coords in enemy_units:
        if enemy_coords is None:
            continue
        enemy_id = _key
        for tlon, tlat in triggers:
            if haversine_km(tlon, tlat, enemy_coords[0], enemy_coords[1]) <= radius_km:
                revealed.add(enemy_id)
                break

    return revealed


def update_reveal_state_for_document(
    root: ET.Element,
    *,
    campaign_dir: Path,
    turn: int,
    radius_km: float,
    persistent: bool,
) -> dict:
    document = root.find(_kml("Document"))
    package = _campaign_package(document) if document is not None else None
    state = load_reveal_state(campaign_dir)
    if package is None:
        return state

    red_units = _iter_faction_placemarks(package, "red-cell")
    blue_units = _iter_faction_placemarks(package, "blue-cell")

    red_revealed = _proximity_reveals(
        viewer_faction="red-cell",
        own_units=red_units,
        enemy_units=blue_units,
        state=state,
        radius_km=radius_km,
        persistent=persistent,
    )
    blue_revealed = _proximity_reveals(
        viewer_faction="blue-cell",
        own_units=blue_units,
        enemy_units=red_units,
        state=state,
        radius_km=radius_km,
        persistent=persistent,
    )

    positions: dict[str, list[float]] = {}
    for key, _pm, coords in red_units + blue_units:
        if coords is not None:
            positions[key] = [coords[0], coords[1]]

    state["turn"] = turn
    state["positions"] = positions
    state["reveals"] = {"red_sees_blue": sorted(red_revealed), "blue_sees_red": sorted(blue_revealed)}
    save_reveal_state(campaign_dir, state)
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


def _remove_placemarks_not_in(folder: ET.Element, keep_ids: set[str], path_prefix: list[str]) -> None:
    for child in list(folder):
        if child.tag == _kml("Placemark"):
            key = placemark_path_key(path_prefix + [_placemark_id(child)])
            if key not in keep_ids:
                folder.remove(child)
        elif child.tag == _kml("Folder"):
            name_el = child.find(_kml("name"))
            sub = (name_el.text or "") if name_el is not None else "folder"
            _remove_placemarks_not_in(child, keep_ids, path_prefix + [sub])


def _strip_faction(package: ET.Element, faction: str) -> None:
    target = _folder_named(package, faction)
    if target is not None:
        package.remove(target)


def _filter_opponent_folder(
    package: ET.Element,
    opponent: str,
    keep_ids: set[str],
) -> None:
    folder = _folder_named(package, opponent)
    if folder is None:
        return
    _remove_placemarks_not_in(folder, keep_ids, [opponent])


def _filter_white_cell_for_viewer(package: ET.Element, viewer: str) -> None:
    white = _folder_named(package, "white-cell")
    if white is None:
        return
    keep_discovered = "redcell-discovered" if viewer == "red-cell" else "bluecell-discovered"
    for child in list(white):
        if child.tag != _kml("Folder"):
            white.remove(child)
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
    if viewer is None or viewer_sees_everything(game_format, viewer):
        return root

    filtered = copy.deepcopy(root)
    document = filtered.find(_kml("Document"))
    package = _campaign_package(document) if document is not None else None
    if package is None:
        return filtered

    reveals = state.get("reveals", {})
    if viewer == "red-cell":
        keep = set(reveals.get("red_sees_blue", []))
        _filter_opponent_folder(package, "blue-cell", keep)
        _filter_white_cell_for_viewer(package, "red-cell")
    elif viewer == "blue-cell":
        keep = set(reveals.get("blue_sees_red", []))
        _filter_opponent_folder(package, "red-cell", keep)
        _filter_white_cell_for_viewer(package, "blue-cell")

    return filtered


def merge_discovered_into_opponent_view(root: ET.Element, viewer: str) -> None:
    """
    Copy white-cell discovered placemarks into opponent faction folder for visibility.
    Manual referee markers in redcell-discovered become visible to red without path-key matching.
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

    tactical = _folder_named(target, "Tactical") or target
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
    persistent: bool | None,
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
    radius = radius_km if radius_km is not None else float(meta.get("reveal_radius_km", 1.0))
    persist = persistent if persistent is not None else bool(meta.get("reveal_persistent", True))

    root = ET.parse(path).getroot()
    migrate_to_campaign_package(root)
    strip_tier_folder_regions(root)
    inject_placemark_tier_regions(root)

    state = update_reveal_state_for_document(
        root,
        campaign_dir=campaign_dir,
        turn=turn,
        radius_km=radius,
        persistent=persist,
    )

    fmt = effective_format(fmt, viewer)
    filtered = filter_campaign_root(root, viewer=viewer, game_format=fmt, state=state)
    if viewer in VIEWER_ROLES and not viewer_sees_everything(fmt, viewer):
        merge_discovered_into_opponent_view(filtered, viewer)

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        filtered, encoding="unicode"
    )
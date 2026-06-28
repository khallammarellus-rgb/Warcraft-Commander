#!/usr/bin/env python3
"""Parent continent grouping for GEP Places tree (Continents → Major Islands / Minor Isles)."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from build_pacific_vignette import DEFAULT_CORE_10
from globe_placement import layer_by_id, layer_earth_bounds

KML_NS = "http://www.opengis.net/kml/2.2"

MAJOR_ISLANDS_FOLDER = "Major Islands"
MINOR_ISLES_FOLDER = "Minor Isles"
MAP_LAYERS_FOLDER = "Map layers"
CONTINENTS_FOLDER = "Continents"
OTHER_WORLDS_FOLDER = "Other Worlds"
SUBTERRANEAN_FOLDER = "Subterranean"
PLAYER_MAP_LINK_NAME = "Azeroth maps (auto — leave on)"


def core_parent_ids(config: dict) -> list[str]:
    geo = config.get("geographic_placement", {})
    return list(geo.get("core_10_regions", DEFAULT_CORE_10))


def parent_label(config: dict, parent_id: str) -> str:
    hierarchy = config.get("geographic_placement", {}).get("places_hierarchy", {})
    labels = hierarchy.get("parent_labels", {})
    if parent_id in labels:
        return labels[parent_id]
    layer = layer_by_id(config, parent_id)
    return layer.get("label", parent_id) if layer else parent_id


def _layer_center(layer: dict, config: dict) -> tuple[float, float]:
    west, south, east, north = layer_earth_bounds(layer, config)
    return (west + east) / 2.0, (south + north) / 2.0


def resolve_places_parent(layer_id: str, config: dict) -> str:
    """Nearest core-10 parent for a theater or island layer."""
    core_ids = set(core_parent_ids(config))
    if layer_id in core_ids:
        return layer_id

    geo = config.get("geographic_placement", {})
    hierarchy = geo.get("places_hierarchy", {})
    overrides = hierarchy.get("parent_overrides", {})

    layer = layer_by_id(config, layer_id)
    if layer and layer.get("parent_region") in core_ids:
        return str(layer["parent_region"])
    if layer_id in overrides:
        return overrides[layer_id]

    default = hierarchy.get("default_parent_for_orphans", "maelstrom")
    if not layer:
        return default

    cx, cy = _layer_center(layer, config)
    best_id = default
    best_dist = float("inf")
    for parent_id in core_parent_ids(config):
        parent_layer = layer_by_id(config, parent_id)
        if not parent_layer:
            continue
        px, py = _layer_center(parent_layer, config)
        dist = (cx - px) ** 2 + (cy - py) ** 2
        if dist < best_dist:
            best_dist = dist
            best_id = parent_id
    return best_id


def region_tier(layer_id: str, config: dict) -> str:
    """continent | major | minor"""
    geo = config.get("geographic_placement", {})
    if layer_id in geo.get("core_10_regions", DEFAULT_CORE_10):
        return "continent"
    if layer_id in geo.get("silhouette_islands", []):
        return "major"
    if layer_id in geo.get("minor_isles", []):
        return "minor"
    return "major"


def bucket_regions_by_parent(
    region_ids: list[str],
    config: dict,
) -> dict[str, dict[str, list[str]]]:
    """
    Group region ids under core-10 parents.

    Returns {parent_id: {"continent": [id]|[], "major": [...], "minor": [...]}}
    """
    core = core_parent_ids(config)
    buckets: dict[str, dict[str, list[str]]] = {
        parent_id: {"continent": [], "major": [], "minor": []} for parent_id in core
    }
    for region_id in region_ids:
        parent_id = resolve_places_parent(region_id, config)
        if parent_id not in buckets:
            parent_id = core_parent_ids(config)[0]
        tier = region_tier(region_id, config)
        buckets[parent_id][tier].append(region_id)
    return buckets


def places_hierarchy_enabled(config: dict) -> bool:
    return bool(
        config.get("geographic_placement", {}).get("places_hierarchy", {}).get("enabled", True)
    )


def opposite_hemisphere_ids(config: dict) -> frozenset[str]:
    geo = config.get("geographic_placement", {})
    return frozenset(geo.get("opposite_hemisphere", {}).get("ids", []))


def other_worlds_region_ids(config: dict, *, built_only: bool = False) -> list[str]:
    """Opposite-hemisphere layers for the Other Worlds Places folder."""
    opposite = opposite_hemisphere_ids(config)
    ids: list[str] = []
    for layer in config.get("layers", []):
        layer_id = layer.get("id")
        if not layer_id or layer_id not in opposite:
            continue
        if layer.get("layer_type") != "minimap":
            continue
        if built_only and not layer.get("earth_placement"):
            continue
        ids.append(layer_id)
    return ids


def split_pacific_and_opposite(
    region_ids: list[str],
    config: dict,
) -> tuple[list[str], list[str]]:
    """Split enabled regions into Pacific theater vs opposite-hemisphere extra worlds."""
    opposite = opposite_hemisphere_ids(config)
    pacific = [rid for rid in region_ids if rid not in opposite]
    other = [rid for rid in region_ids if rid in opposite]
    return pacific, other


def subterranean_region_ids(config: dict, *, built_only: bool = False) -> list[str]:
    """All subterranean layer ids (optionally only those with earth_placement)."""
    ids: list[str] = []
    for layer in config.get("layers", []):
        if layer.get("layer_type") != "subterranean":
            continue
        layer_id = layer.get("id")
        if not layer_id:
            continue
        if built_only and not layer.get("earth_placement"):
            continue
        ids.append(layer_id)
    return ids


def bucket_subterranean_by_parent(
    subterranean_ids: list[str],
    config: dict,
) -> dict[str, list[str]]:
    """Group subterranean zones under their parent continent (one handoff per parent)."""
    buckets: dict[str, list[str]] = {parent_id: [] for parent_id in core_parent_ids(config)}
    for layer_id in subterranean_ids:
        layer = layer_by_id(config, layer_id)
        if not layer:
            continue
        parent_id = layer.get("parent_region") or resolve_places_parent(layer_id, config)
        if parent_id not in buckets:
            parent_id = core_parent_ids(config)[0]
        buckets[parent_id].append(layer_id)
    return {pid: zones for pid, zones in buckets.items() if zones}


def make_folder(
    parent: ET.Element,
    name: str,
    *,
    open_default: int = 0,
    description: str | None = None,
) -> ET.Element:
    folder = ET.SubElement(parent, f"{{{KML_NS}}}Folder")
    ET.SubElement(folder, f"{{{KML_NS}}}name").text = name
    ET.SubElement(folder, f"{{{KML_NS}}}open").text = str(open_default)
    if description:
        ET.SubElement(folder, f"{{{KML_NS}}}description").text = description
    return folder
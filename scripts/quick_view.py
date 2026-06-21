#!/usr/bin/env python3
"""Quick View camera bookmarks — flat LookAt placemarks for GEP Places."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from globe_placement import layer_by_id
from places_hierarchy import make_folder

KML_NS = "http://www.opengis.net/kml/2.2"
MILES_TO_METERS = 1609.344


def _kml(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def miles_to_range_m(miles: float) -> float:
    return miles * MILES_TO_METERS


def planet_look_at_values(config: dict) -> tuple[float, float, float]:
    """Maelstrom center + planet tier range (meters) for Document initial view."""
    viewpoints = config.get("viewpoints", {})
    vdd = viewpoints.get("view_distance_defaults") or viewpoints.get("quick_view") or {}
    tiers = vdd.get("tiers", {})
    planet_cfg = tiers.get("planet", {})
    anchor = config.get("anchor", {})
    lon = float(anchor.get("earth_lon", -175.0784))
    lat = float(anchor.get("earth_lat", 21.1559))
    miles = float(planet_cfg.get("range_miles", 30000))
    return lon, lat, miles_to_range_m(miles)


def append_document_planet_look_at(document: ET.Element, config: dict) -> None:
    """Initial camera when a KML document is opened in Google Earth Pro."""
    lon, lat, range_m = planet_look_at_values(config)
    look_at = ET.SubElement(document, _kml("LookAt"))
    ET.SubElement(look_at, _kml("longitude")).text = f"{lon:.6f}"
    ET.SubElement(look_at, _kml("latitude")).text = f"{lat:.6f}"
    ET.SubElement(look_at, _kml("altitude")).text = "0"
    ET.SubElement(look_at, _kml("range")).text = f"{range_m:.0f}"
    ET.SubElement(look_at, _kml("tilt")).text = "0"
    ET.SubElement(look_at, _kml("heading")).text = "0"


def layer_center_lon_lat(layer: dict) -> tuple[float, float]:
    placement = layer.get("earth_placement") or {}
    if "center_lon" in placement and "center_lat" in placement:
        return float(placement["center_lon"]), float(placement["center_lat"])
    if all(key in placement for key in ("west", "east", "south", "north")):
        return (
            (float(placement["west"]) + float(placement["east"])) / 2.0,
            (float(placement["south"]) + float(placement["north"])) / 2.0,
        )
    raise ValueError(f"Layer {layer.get('id')} has no center in earth_placement")


def append_lookat_placemark(
    parent: ET.Element,
    name: str,
    lon: float,
    lat: float,
    range_m: float,
    *,
    tier: str,
    range_miles: float,
) -> None:
    placemark = ET.SubElement(parent, _kml("Placemark"))
    ET.SubElement(placemark, _kml("name")).text = name
    description = ET.SubElement(placemark, _kml("description"))
    description.text = (
        f"Double-click to fly. tier={tier} "
        f"range={range_miles:,.0f} mi ({range_m:,.0f} m)"
    )
    look_at = ET.SubElement(placemark, _kml("LookAt"))
    ET.SubElement(look_at, _kml("longitude")).text = f"{lon:.6f}"
    ET.SubElement(look_at, _kml("latitude")).text = f"{lat:.6f}"
    ET.SubElement(look_at, _kml("altitude")).text = "0"
    ET.SubElement(look_at, _kml("range")).text = f"{range_m:.0f}"
    ET.SubElement(look_at, _kml("tilt")).text = "0"
    ET.SubElement(look_at, _kml("heading")).text = "0"


def append_quick_view_bookmarks(parent: ET.Element, config: dict) -> bool:
    """
    Append a flat Quick View folder (no subfolders) to parent.

    Returns True if bookmarks were added.
    """
    viewpoints = config.get("viewpoints", {})
    vdd = viewpoints.get("view_distance_defaults") or viewpoints.get("quick_view")
    if not vdd:
        return False

    root = make_folder(
        parent,
        vdd.get("folder_label", "Quick View"),
        open_default=0,
    )
    tiers = vdd.get("tiers", {})
    anchor = config.get("anchor", {})

    planet_cfg = tiers.get("planet", {})
    if planet_cfg:
        planet_miles = float(planet_cfg.get("range_miles", 30000))
        planet_range_m = miles_to_range_m(planet_miles)
        planet_name = planet_cfg.get("placemark_name", "Planet")
        planet_lon = float(anchor.get("earth_lon", -175.0784))
        planet_lat = float(anchor.get("earth_lat", 21.1559))
        append_lookat_placemark(
            root,
            planet_name,
            planet_lon,
            planet_lat,
            planet_range_m,
            tier="planet",
            range_miles=planet_miles,
        )

    strategic_cfg = tiers.get("strategic", {})
    if strategic_cfg:
        strategic_miles = float(strategic_cfg.get("range_miles", 3000))
        strategic_range_m = miles_to_range_m(strategic_miles)
        for region_id in strategic_cfg.get("regions", []):
            layer = layer_by_id(config, region_id)
            if not layer:
                continue
            lon, lat = layer_center_lon_lat(layer)
            label = layer.get("label", region_id)
            append_lookat_placemark(
                root,
                label,
                lon,
                lat,
                strategic_range_m,
                tier="strategic",
                range_miles=strategic_miles,
            )

    return True


def append_opposite_quick_view_bookmarks(
    parent: ET.Element,
    config: dict,
    region_ids: list[str],
) -> None:
    """Strategic fly-to bookmarks for opposite-hemisphere extra worlds."""
    if not region_ids:
        return
    viewpoints = config.get("viewpoints", {})
    vdd = viewpoints.get("view_distance_defaults") or viewpoints.get("quick_view") or {}
    tiers = vdd.get("tiers", {})
    strategic_cfg = tiers.get("strategic", {})
    strategic_miles = float(strategic_cfg.get("range_miles", 3000))
    strategic_range_m = miles_to_range_m(strategic_miles)

    folder = make_folder(
        parent,
        "Other worlds (Quick View)",
        open_default=0,
        description="Double-click to fly to extra-world zones on the far side of the globe.",
    )
    for region_id in region_ids:
        layer = layer_by_id(config, region_id)
        if not layer:
            continue
        lon, lat = layer_center_lon_lat(layer)
        label = layer.get("label", region_id)
        append_lookat_placemark(
            folder,
            label,
            lon,
            lat,
            strategic_range_m,
            tier="strategic",
            range_miles=strategic_miles,
        )
"""HQ placemark builder for campaign setup."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from campaign_tier_lod import KML_NS
from faction_library import executive_officer, palette_style_id
from globe_placement import layer_by_id, load_globe_config

FORCE_SIZES = ("platoon", "company", "battalion", "regiment", "division", "army")

FORCE_SPECS: dict[str, dict] = {
    "platoon": {"abbrev": "Plt", "strength": 40, "tier": "Operational", "hq_prefix": "1st"},
    "company": {"abbrev": "Co", "strength": 150, "tier": "Operational", "hq_prefix": "A"},
    "battalion": {"abbrev": "Bn", "strength": 1000, "tier": "Operational", "hq_prefix": "1st"},
    "regiment": {"abbrev": "Regt", "strength": 3000, "tier": "Strategic", "hq_prefix": "1st"},
    "division": {"abbrev": "Div", "strength": 9000, "tier": "Strategic", "hq_prefix": "1st"},
    "army": {"abbrev": "Army", "strength": 20000, "tier": "Strategic", "hq_prefix": ""},
}


def theater_center(project_root: Path, theater_id: str) -> tuple[float, float]:
    config = load_globe_config(project_root)
    layer = layer_by_id(config, theater_id)
    if layer is None:
        raise ValueError(f"Unknown theater: {theater_id}")
    placement = layer.get("earth_placement") or {}
    if "center_lon" in placement and "center_lat" in placement:
        return float(placement["center_lon"]), float(placement["center_lat"])
    from globe_placement import layer_earth_bounds

    west, south, east, north = layer_earth_bounds(layer, config)
    return (west + east) / 2, (south + north) / 2


def hq_name(
    force_size: str,
    *,
    force_name: str | None = None,
) -> str:
    spec = FORCE_SPECS.get(force_size, FORCE_SPECS["battalion"])
    strength = spec["strength"]
    if force_size == "army" and force_name:
        return f"{force_name} HQ {strength}/{strength}"
    prefix = spec["hq_prefix"]
    abbrev = spec["abbrev"]
    if force_size == "company":
        return f"{prefix} {abbrev} HQ {strength}/{strength}"
    return f"{prefix}{abbrev} HQ {strength}/{strength}"


def hq_tier(force_size: str) -> str:
    return FORCE_SPECS.get(force_size, FORCE_SPECS["battalion"])["tier"]


def force_size_preview(force_size: str, *, force_name: str | None = None) -> str:
    """One-line HQ example for setup wizard (updates as player highlights each size)."""
    name = (force_name or "").strip() or None
    if force_size == "army" and not name:
        name = "Your Force"
    hq = hq_name(force_size, force_name=name)
    tier = hq_tier(force_size)
    return f"{force_size.title()} → {hq} ({tier} tier)"


def hq_description(
    *,
    commander_name: str,
    force_name: str,
    executive_officer: str,
    primary_faction_label: str,
) -> str:
    return (
        f"Commander {commander_name}, {force_name}. {executive_officer}.\n\n"
        f"To add subordinate units: right-click your cell folder → Add → Placemark. "
        f"Copy icon style from Unit palettes → {primary_faction_label}. "
        "Track strength in the placemark name (e.g. 2nd Sqd 30/30). "
        "Delete the marker when destroyed."
    )


def build_hq_placemark(
    project_root: Path,
    *,
    commander_name: str,
    force_name: str,
    force_size: str,
    primary_faction_id: str,
    primary_faction_label: str,
    coords: tuple[float, float],
) -> ET.Element:
    lon, lat = coords
    name = hq_name(force_size, force_name=force_name)
    eo = executive_officer(project_root, primary_faction_id)
    style_id = palette_style_id(project_root, primary_faction_id)

    pm = ET.Element(f"{{{KML_NS}}}Placemark")
    ET.SubElement(pm, f"{{{KML_NS}}}name").text = name
    ET.SubElement(pm, f"{{{KML_NS}}}description").text = hq_description(
        commander_name=commander_name,
        force_name=force_name,
        executive_officer=eo,
        primary_faction_label=primary_faction_label,
    )
    ET.SubElement(pm, f"{{{KML_NS}}}styleUrl").text = f"#{style_id}"
    point = ET.SubElement(pm, f"{{{KML_NS}}}Point")
    ET.SubElement(point, f"{{{KML_NS}}}coordinates").text = f"{lon:.6f},{lat:.6f},0"
    return pm


def build_hq_style(project_root: Path, primary_faction_id: str) -> ET.Element | None:
    from faction_library import load_palette_document

    doc = load_palette_document(project_root, primary_faction_id)
    if doc is None:
        return None
    style_id = palette_style_id(project_root, primary_faction_id)
    for style in doc.findall(f"{{{KML_NS}}}Style"):
        src_id = style.get("id", "faction-icon")
        if src_id != "faction-icon":
            continue
        style_copy = ET.Element(f"{{{KML_NS}}}Style")
        style_copy.set("id", style_id)
        import copy

        for child in style:
            style_copy.append(copy.deepcopy(child))
        return style_copy
    return None
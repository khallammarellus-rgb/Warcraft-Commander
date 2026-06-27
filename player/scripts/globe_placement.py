#!/usr/bin/env python3
"""Convert layer placement to Earth bounds for globe KML."""

from __future__ import annotations

import json
import math
from pathlib import Path


def load_globe_config(project_root: Path) -> dict:
    config_path = project_root / "config" / "globe.json"
    with config_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def resolve_raw_input(project_root: Path, rel_input: str, raw_root: str | None = None) -> Path:
    """
    Resolve a layer input path, optionally swapping 01-raw-export for an alternate raw tree.

    Example: resolve_raw_input(root, "01-raw-export/maps/kalimdor/minimap", "rawfilenoocean")
    -> <project>/rawfilenoocean/maps/kalimdor/minimap
    """
    default_root = "01-raw-export"
    if raw_root and rel_input.startswith(f"{default_root}/"):
        return project_root / raw_root / rel_input[len(f"{default_root}/") :]
    return project_root / rel_input


def resolve_grid_reference_input(
    project_root: Path,
    rel_input: str,
    globe_config: dict | None,
) -> Path | None:
    """
    Map tile source path to grid-reference path for full-export anchoring.

    Example: 04-edited-exports/maps/kalimdor/minimap -> 01-raw-export/maps/kalimdor/minimap
    """
    if not rel_input or not globe_config:
        return None
    grid_root = globe_config.get("grid_reference_root")
    if not grid_root:
        return None
    tile_root = globe_config.get("tile_source_root")
    if tile_root and rel_input.startswith(f"{tile_root}/"):
        return project_root / grid_root / rel_input[len(f"{tile_root}/") :]
    if rel_input.startswith("04-edited-exports/"):
        return project_root / grid_root / rel_input[len("04-edited-exports/") :]
    return None


def poster_config(globe_config: dict) -> dict:
    return globe_config.get("world_poster", {})


def span_lon_corrected(span_lat: float, aspect: float, center_lat: float) -> float:
    """Adjust longitude span for latitude so map scale looks correct on the globe."""
    cos_lat = max(0.15, abs(math.cos(math.radians(center_lat))))
    return span_lat * aspect / cos_lat


def poster_rect_to_earth_bounds(poster_rect: list[float], globe_config: dict) -> tuple[float, float, float, float]:
    """
    Map a rectangle on the master poster [x0, y0, x1, y1] to KML bounds.
    Returns (west, south, east, north).
    """
    wp = poster_config(globe_config)
    pw = float(wp.get("width", 786))
    ph = float(wp.get("height", 786))
    anchor = wp.get("anchor_pixel", [400, 334])
    anchor_lon = float(wp.get("anchor_earth_lon", globe_config.get("anchor", {}).get("earth_lon", -160.0)))
    anchor_lat = float(wp.get("anchor_earth_lat", globe_config.get("anchor", {}).get("earth_lat", 0.0)))
    span_lon = float(wp.get("span_lon_degrees", globe_config.get("coverage", {}).get("span_lon_degrees", 150.0)))
    span_lat = float(wp.get("span_lat_degrees", globe_config.get("coverage", {}).get("span_lat_degrees", 85.0)))

    ax, ay = float(anchor[0]), float(anchor[1])
    x0, y0, x1, y1 = poster_rect

    west = anchor_lon + (x0 - ax) / pw * span_lon
    east = anchor_lon + (x1 - ax) / pw * span_lon
    north = anchor_lat - (y0 - ay) / ph * span_lat
    south = anchor_lat - (y1 - ay) / ph * span_lat
    return west, south, east, north


def poster_full_earth_bounds(globe_config: dict) -> tuple[float, float, float, float]:
    wp = poster_config(globe_config)
    pw = float(wp.get("width", 786))
    ph = float(wp.get("height", 786))
    return poster_rect_to_earth_bounds([0, 0, pw, ph], globe_config)


def earth_bounds_from_center(
    center_lon: float,
    center_lat: float,
    span_lon: float,
    span_lat: float,
) -> tuple[float, float, float, float]:
    half_lon = span_lon / 2
    half_lat = span_lat / 2
    return (
        center_lon - half_lon,
        center_lat - half_lat,
        center_lon + half_lon,
        center_lat + half_lat,
    )


def earth_bounds_from_edges(
    center_lon: float,
    north_lat: float,
    south_lat: float,
    aspect: float,
    *,
    latitude_correct: bool = True,
) -> tuple[float, float, float, float]:
    span_lat = north_lat - south_lat
    center_lat = (north_lat + south_lat) / 2
    if latitude_correct:
        span_lon = span_lon_corrected(span_lat, aspect, center_lat)
    else:
        span_lon = span_lat * aspect
    return earth_bounds_from_center(center_lon, center_lat, span_lon, span_lat)


def layer_earth_bounds(layer: dict, globe_config: dict) -> tuple[float, float, float, float]:
    placement = layer.get("earth_placement")
    if placement:
        if all(key in placement for key in ("west", "south", "east", "north")):
            return (
                float(placement["west"]),
                float(placement["south"]),
                float(placement["east"]),
                float(placement["north"]),
            )
        if "center_lon" in placement and "center_lat" in placement:
            return earth_bounds_from_center(
                float(placement["center_lon"]),
                float(placement["center_lat"]),
                float(placement["span_lon"]),
                float(placement["span_lat"]),
            )

    poster = layer.get("poster_placement")
    if poster and "poster_rect" in poster:
        return poster_rect_to_earth_bounds(poster["poster_rect"], globe_config)

    raise ValueError(f"Layer {layer.get('id')} has no earth_placement or poster_placement")


def layer_by_id(globe_config: dict, layer_id: str) -> dict | None:
    for layer in globe_config.get("layers", []):
        if layer.get("id") == layer_id:
            return layer
    return None


def layer_overlay_rotation_deg(layer: dict | None) -> float:
    """KML LatLonBox rotation (degrees counter-clockwise from north)."""
    if not layer:
        return 0.0
    placement = layer.get("earth_placement") or {}
    return float(placement.get("rotation_deg", 0.0))
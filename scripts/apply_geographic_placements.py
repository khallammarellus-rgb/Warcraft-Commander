#!/usr/bin/env python3
"""
Apply geographic placement to config/globe.json.

Modes (geographic_placement):
  mgrs_centers — center each region on an MGRS grid coordinate
  pacific_theater — legacy poster → Pacific cluster mapping
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from globe_placement import earth_bounds_from_center, layer_by_id, span_lon_corrected
from mgrs_utils import mgrs_to_latlon

TILE_PATTERN = re.compile(r"map(\d+)_(\d+)\.png$", re.IGNORECASE)
SOURCE_TILE_PX = 512

INPUT_ALIASES = {"kul_tiras": "kultiras"}

SIZE_SCALE = {
    "kalimdor": 1.0,
    "eastern_kingdoms": 1.0,
    "northrend": 0.9,
    "pandaria": 0.9,
    "dragon_isles": 0.9 * 0.75,
    "broken_isles": 0.9 * 0.75,
    "kul_tiras": 0.9 * 0.7,
    "zandalar": 0.9 * 0.7,
    "khaz_algar": 0.9 * 0.7,
    "wandering_isle": 0.9 * 0.1,
    "founders_point": 1.0 * 0.1,
    "razorwind_shores": 1.0 * 0.1,
    "tol_barad": 1.0 * 0.05,
    "siren_isle": 0.9 * 0.7 * 0.2,
    "kezan": 0.9 * 0.7 * 0.2,
    "nazjatar": 0.9 * 0.1,
    "mechagon": 0.9 * 0.7 * 0.2,
    "maelstrom": 0.9 * 0.7 * 0.2,
    "outland": 0.9,
    "draenor": 0.9,
    "shadowlands": 0.9,
    "emerald_dream": 0.75,
    "zereth_mortis": 0.7,
    "mardum": 0.4,
    "karesh": 0.7,
    "voidstorm": 0.7,
}

MGRS_MAJORS = (
    "northrend",
    "dragon_isles",
    "eastern_kingdoms",
    "broken_isles",
    "kul_tiras",
    "zandalar",
    "pandaria",
    "khaz_algar",
    "kalimdor",
    "outland",
    "draenor",
    "shadowlands",
    "emerald_dream",
    "zereth_mortis",
    "mardum",
    "karesh",
    "voidstorm",
)

PARENT_REGION = {
    "wandering_isle": "pandaria",
    "founders_point": "eastern_kingdoms",
    "razorwind_shores": "kalimdor",
    "tol_barad": "eastern_kingdoms",
    "siren_isle": "khaz_algar",
    "kezan": "maelstrom",
    "nazjatar": "maelstrom",
    "mechagon": "kul_tiras",
}


def mosaic_aspect(project_root: Path, layer_id: str, layer: dict | None = None) -> float:
    if layer and layer.get("input"):
        input_dir = project_root / layer["input"]
    else:
        folder = INPUT_ALIASES.get(layer_id, layer_id)
        input_dir = project_root / "01-raw-export" / "maps" / folder / "minimap"
    tiles: dict[tuple[int, int], Path] = {}
    for path in input_dir.rglob("map*_*.png"):
        match = TILE_PATTERN.match(path.name)
        if match:
            tiles[(int(match.group(1)), int(match.group(2)))] = path
    if not tiles:
        return 1.0
    xs = [x for x, _ in tiles]
    ys = [y for _, y in tiles]
    width = (max(xs) - min(xs) + 1) * SOURCE_TILE_PX
    height = (max(ys) - min(ys) + 1) * SOURCE_TILE_PX
    return width / max(height, 1)


def poster_center(layer: dict) -> tuple[float, float] | None:
    placement = layer.get("poster_placement") or {}
    center = placement.get("poster_center")
    if center:
        return float(center[0]), float(center[1])
    rect = placement.get("poster_rect")
    if rect:
        return (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
    return None


def placement_dict(
    center_lon: float,
    center_lat: float,
    span_lon: float,
    span_lat: float,
    *,
    source: str,
) -> dict:
    west, south, east, north = earth_bounds_from_center(center_lon, center_lat, span_lon, span_lat)
    return {
        "center_lon": round(center_lon, 4),
        "center_lat": round(center_lat, 4),
        "span_lon": round(span_lon, 4),
        "span_lat": round(span_lat, 4),
        "west": round(west, 6),
        "south": round(south, 6),
        "east": round(east, 6),
        "north": round(north, 6),
        "source": source,
    }


def base_spans(project_root: Path, geo: dict) -> tuple[float, float]:
    kal_aspect = mosaic_aspect(project_root, "kalimdor")
    base_lat = float(geo.get("kal_base_span_lat", 27.0))
    base_lon = float(geo.get("kal_base_span_lon", 0))
    if base_lon <= 0:
        base_lon = span_lon_corrected(base_lat, kal_aspect, 15.0)
    return base_lon, base_lat


def placement_from_mgrs_edges(
    layer_id: str,
    center_lon: float,
    north_code: str,
    south_code: str,
    project_root: Path,
) -> dict:
    north_lat, _ = mgrs_to_latlon(north_code)
    south_lat, _ = mgrs_to_latlon(south_code)
    if north_lat < south_lat:
        north_lat, south_lat = south_lat, north_lat
    span_lat = north_lat - south_lat
    center_lat = (north_lat + south_lat) / 2
    aspect = mosaic_aspect(project_root, layer_id)
    span_lon = span_lon_corrected(span_lat, aspect, center_lat)
    return placement_dict(
        center_lon,
        center_lat,
        span_lon,
        span_lat,
        source=f"MGRS edges N={north_code} S={south_code}",
    )


def effective_scale(geo: dict, layer_id: str) -> float:
    scale = SIZE_SCALE.get(layer_id, 1.0)
    multipliers = geo.get("size_multipliers", {})
    if layer_id in multipliers:
        scale *= float(multipliers[layer_id])
    return scale


def frozen_center(config: dict, geo: dict, layer_id: str) -> tuple[float, float] | None:
    if layer_id not in geo.get("freeze_position", []):
        return None
    layer = layer_by_id(config, layer_id)
    if not layer:
        return None
    ep = layer.get("earth_placement") or {}
    if "center_lon" not in ep or "center_lat" not in ep:
        return None
    return float(ep["center_lon"]), float(ep["center_lat"])


def mgrs_placements(config: dict, project_root: Path, geo: dict) -> dict[str, dict]:
    centers = geo.get("mgrs_centers", {})
    edges = geo.get("mgrs_edges", {})
    base_lon, base_lat = base_spans(project_root, geo)
    placements: dict[str, dict] = {}

    for layer_id in MGRS_MAJORS:
        code = centers.get(layer_id)
        if not code:
            continue
        lat, lon = mgrs_to_latlon(code)
        frozen = frozen_center(config, geo, layer_id)
        if frozen:
            lon, lat = frozen
        edge = edges.get(layer_id, {})
        if edge.get("north") and edge.get("south"):
            placements[layer_id] = placement_from_mgrs_edges(
                layer_id,
                lon,
                edge["north"],
                edge["south"],
                project_root,
            )
            if frozen:
                p = placements[layer_id]
                scale = effective_scale(geo, layer_id)
                aspect = mosaic_aspect(project_root, layer_id)
                span_lat = p["span_lat"] * scale / SIZE_SCALE.get(layer_id, 1.0)
                span_lon = span_lon_corrected(span_lat, aspect, lat)
                placements[layer_id] = placement_dict(
                    lon,
                    lat,
                    span_lon,
                    span_lat,
                    source=f"MGRS {code} (position frozen)",
                )
            continue
        scale = effective_scale(geo, layer_id)
        aspect = mosaic_aspect(project_root, layer_id)
        span_lat = base_lat * scale
        span_lon = span_lon_corrected(span_lat, aspect, lat)
        source = f"MGRS {code}"
        if frozen:
            source += " (position frozen)"
        placements[layer_id] = placement_dict(
            lon,
            lat,
            span_lon,
            span_lat,
            source=source,
        )

    wp = config.get("world_poster", {})
    pw = float(wp.get("width", 3840))
    ph = float(wp.get("height", 2560))

    for layer in config.get("layers", []):
        layer_id = layer.get("id")
        if layer_id in placements or layer_id == "maelstrom":
            continue
        if not layer.get("enabled"):
            continue

        code = centers.get(layer_id)
        if not code and layer_id not in SIZE_SCALE:
            continue
        if code:
            lat, lon = mgrs_to_latlon(code)
            frozen = frozen_center(config, geo, layer_id)
            if frozen:
                lon, lat = frozen
            scale = effective_scale(geo, layer_id)
            aspect = mosaic_aspect(project_root, layer_id)
            span_lat = base_lat * scale
            span_lon = span_lon_corrected(span_lat, aspect, lat)
            source = f"MGRS {code}"
            if frozen:
                source += " (position frozen)"
            placements[layer_id] = placement_dict(
                lon,
                lat,
                span_lon,
                span_lat,
                source=source,
            )
            continue

        parent_id = PARENT_REGION.get(layer_id)
        parent = placements.get(parent_id) if parent_id else None
        child_center = poster_center(layer)
        parent_layer = layer_by_id(config, parent_id) if parent_id else None
        parent_center = poster_center(parent_layer) if parent_layer else None

        if parent and child_center and parent_center:
            du = (child_center[0] - parent_center[0]) / pw
            dv = (child_center[1] - parent_center[1]) / ph
            center_lon = parent["center_lon"] + du * parent["span_lon"]
            center_lat = parent["center_lat"] - dv * parent["span_lat"]
        elif parent:
            center_lon = parent["center_lon"]
            center_lat = parent["center_lat"]
        else:
            continue

        scale = effective_scale(geo, layer_id)
        aspect = mosaic_aspect(project_root, layer_id)
        span_lat = base_lat * scale
        span_lon = span_lon_corrected(span_lat, aspect, center_lat)
        placements[layer_id] = placement_dict(
            center_lon,
            center_lat,
            span_lon,
            span_lat,
            source=f"Poster-relative to {parent_id}",
        )

    return placements


def boxes_overlap(a: dict, b: dict, margin: float) -> bool:
    return not (
        a["east"] + margin <= b["west"]
        or b["east"] + margin <= a["west"]
        or a["north"] + margin <= b["south"]
        or b["north"] + margin <= a["south"]
    )


def count_overlaps(placements: dict[str, dict], margin: float) -> int:
    ids = list(placements.keys())
    count = 0
    for i, id_a in enumerate(ids):
        for id_b in ids[i + 1 :]:
            if boxes_overlap(placements[id_a], placements[id_b], margin):
                count += 1
    return count


def shrink_spans_to_separate(
    placements: dict[str, dict],
    margin: float,
    *,
    min_span_fraction: float = 0.55,
    min_span_deg: float = 1.0,
    max_passes: int = 80,
    shrink_exempt: set[str] | None = None,
) -> int:
    """
    Shrink span_lon/span_lat symmetrically around each fixed center until no boxes overlap.

    Centers (MGRS midpoints) never move — only the geographic extent tightens.
    Returns the number of regions whose spans were reduced.
    """
    exempt = shrink_exempt or set()
    ids = list(placements.keys())
    originals = {
        rid: (placements[rid]["span_lon"], placements[rid]["span_lat"]) for rid in ids
    }
    min_half = min_span_deg / 2
    shrunk_ids: set[str] = set()

    for _ in range(max_passes):
        any_overlap = False
        new_spans: dict[str, tuple[float, float]] = {}

        for rid in ids:
            p = placements[rid]
            if rid in exempt:
                new_spans[rid] = (p["span_lon"], p["span_lat"])
                continue
            half_lon = p["span_lon"] / 2
            half_lat = p["span_lat"] / 2
            orig_lon, orig_lat = originals[rid]
            floor_lon = max(min_half, orig_lon * min_span_fraction / 2)
            floor_lat = max(min_half, orig_lat * min_span_fraction / 2)

            for oid in ids:
                if oid == rid:
                    continue
                o = placements[oid]
                o_half_lon = o["span_lon"] / 2
                o_half_lat = o["span_lat"] / 2

                center_dlon = abs(p["center_lon"] - o["center_lon"])
                center_dlat = abs(p["center_lat"] - o["center_lat"])

                allowed_lon = center_dlon - o_half_lon - margin
                allowed_lat = center_dlat - o_half_lat - margin

                if allowed_lon < half_lon:
                    half_lon = max(floor_lon, allowed_lon)
                if allowed_lat < half_lat:
                    half_lat = max(floor_lat, allowed_lat)

            new_span_lon = 2 * half_lon
            new_span_lat = 2 * half_lat
            if new_span_lon < p["span_lon"] - 1e-6 or new_span_lat < p["span_lat"] - 1e-6:
                shrunk_ids.add(rid)
            new_spans[rid] = (new_span_lon, new_span_lat)

        for rid, (span_lon, span_lat) in new_spans.items():
            p = placements[rid]
            if abs(span_lon - p["span_lon"]) < 1e-6 and abs(span_lat - p["span_lat"]) < 1e-6:
                continue
            source = p["source"]
            if "span-shrunk" not in source:
                source += " (span-shrunk)"
            placements[rid] = placement_dict(
                p["center_lon"],
                p["center_lat"],
                span_lon,
                span_lat,
                source=source,
            )

        for i, id_a in enumerate(ids):
            for id_b in ids[i + 1 :]:
                if boxes_overlap(placements[id_a], placements[id_b], margin):
                    any_overlap = True
                    break
            if any_overlap:
                break

        if not any_overlap:
            break

    return len(shrunk_ids)


def nudge_apart(
    placements: dict[str, dict],
    margin: float,
    step: float,
    *,
    frozen: set[str] | None = None,
    passes: int = 8,
) -> None:
    frozen = frozen or set()
    ids = [rid for rid in placements if rid != "maelstrom"]
    for _ in range(passes):
        moved = False
        for i, id_a in enumerate(ids):
            for id_b in ids[i + 1 :]:
                a = placements[id_a]
                b = placements[id_b]
                if not boxes_overlap(a, b, margin):
                    continue
                dlon = a["center_lon"] - b["center_lon"]
                dlat = a["center_lat"] - b["center_lat"]
                if abs(dlon) < 1e-6 and abs(dlat) < 1e-6:
                    dlon, dlat = 1.0, 0.0
                length = (dlon**2 + dlat**2) ** 0.5
                push_lon = dlon / length * step
                push_lat = dlat / length * step
                for pid, sign in ((id_a, 1), (id_b, -1)):
                    if pid in frozen:
                        continue
                    p = placements[pid]
                    placements[pid] = placement_dict(
                        p["center_lon"] + sign * push_lon,
                        p["center_lat"] + sign * push_lat,
                        p["span_lon"],
                        p["span_lat"],
                        source=p["source"] + " (nudged)",
                    )
                    moved = True
        if not moved:
            break


def apply_maelstrom(config: dict, placements: dict[str, dict], geo: dict) -> None:
    kal = placements.get("kalimdor")
    ek = placements.get("eastern_kingdoms")
    if not kal or not ek:
        return
    centers = geo.get("mgrs_centers", {})
    mgrs_code = centers.get("maelstrom")
    if mgrs_code:
        center_lat, center_lon = mgrs_to_latlon(mgrs_code)
        source = f"MGRS {mgrs_code}"
    else:
        center_lon = (kal["center_lon"] + ek["center_lon"]) / 2
        center_lat = (kal["center_lat"] + ek["center_lat"]) / 2
        anchor = geo.get("maelstrom", {})
        if "center_lon" in anchor:
            center_lon = float(anchor["center_lon"])
        if "center_lat" in anchor:
            center_lat = float(anchor["center_lat"])
        source = "Between Kalimdor and Eastern Kingdoms"
    scale = effective_scale(geo, "maelstrom")
    placements["maelstrom"] = placement_dict(
        center_lon,
        center_lat,
        kal["span_lon"] * scale,
        kal["span_lat"] * scale,
        source=source,
    )
    config.setdefault("anchor", {})
    config["anchor"]["earth_lon"] = round(center_lon, 4)
    config["anchor"]["earth_lat"] = round(center_lat, 4)


def apply_maelstrom_satellites(
    config: dict,
    project_root: Path,
    geo: dict,
    placements: dict[str, dict],
) -> None:
    """Re-place poster-relative children whose parent is maelstrom (placed after first pass)."""
    parent = placements.get("maelstrom")
    if not parent:
        return
    centers = geo.get("mgrs_centers", {})
    base_lon, base_lat = base_spans(project_root, geo)
    wp = config.get("world_poster", {})
    pw = float(wp.get("width", 3840))
    ph = float(wp.get("height", 2560))
    parent_layer = layer_by_id(config, "maelstrom")
    parent_center = poster_center(parent_layer) if parent_layer else None
    if not parent_center:
        return
    for layer_id, parent_id in PARENT_REGION.items():
        if parent_id != "maelstrom":
            continue
        if layer_id in placements or centers.get(layer_id):
            continue
        layer = layer_by_id(config, layer_id)
        if not layer or not layer.get("enabled"):
            continue
        child_center = poster_center(layer)
        if not child_center:
            continue
        du = (child_center[0] - parent_center[0]) / pw
        dv = (child_center[1] - parent_center[1]) / ph
        center_lon = parent["center_lon"] + du * parent["span_lon"]
        center_lat = parent["center_lat"] - dv * parent["span_lat"]
        scale = effective_scale(geo, layer_id)
        aspect = mosaic_aspect(project_root, layer_id)
        span_lat = base_lat * scale
        span_lon = span_lon_corrected(span_lat, aspect, center_lat)
        placements[layer_id] = placement_dict(
            center_lon,
            center_lat,
            span_lon,
            span_lat,
            source="Poster-relative to maelstrom",
        )


def apply_parent_offset_placements(
    config: dict,
    project_root: Path,
    geo: dict,
    placements: dict[str, dict],
) -> None:
    """Place misc islands and subterranean zones relative to a parent region center."""
    _, base_lat = base_spans(project_root, geo)

    for layer in config.get("layers", []):
        layer_id = layer.get("id")
        if not layer_id or layer_id in placements:
            continue
        if not layer.get("enabled"):
            continue
        parent_id = layer.get("parent_region")
        offset = layer.get("offset_deg")
        if not parent_id or offset is None:
            continue
        parent = placements.get(parent_id)
        if not parent:
            continue

        center_lon = parent["center_lon"] + float(offset[0])
        center_lat = parent["center_lat"] + float(offset[1])
        if layer.get("size_scale") is not None:
            scale = float(layer["size_scale"])
        else:
            scale = effective_scale(geo, layer_id)
        aspect = mosaic_aspect(project_root, layer_id, layer)
        span_lat = base_lat * scale
        span_lon = span_lon_corrected(span_lat, aspect, center_lat)
        placements[layer_id] = placement_dict(
            center_lon,
            center_lat,
            span_lon,
            span_lat,
            source=f"Offset [{offset[0]:+.1f}, {offset[1]:+.1f}]° from {parent_id}",
        )


def apply_offsets(geo: dict, placements: dict[str, dict]) -> None:
    for layer_id, override in geo.get("offsets", {}).items():
        if layer_id not in placements:
            continue
        p = placements[layer_id]
        lon = float(override.get("center_lon", p["center_lon"]))
        lat = float(override.get("center_lat", p["center_lat"]))
        placements[layer_id] = placement_dict(
            lon,
            lat,
            p["span_lon"],
            p["span_lat"],
            source=p["source"] + " (offset)",
        )


def apply_target_footprints(
    project_root: Path,
    config: dict,
    geo: dict,
    placements: dict[str, dict],
) -> None:
    """Override core region spans to real-world reference footprints."""
    targets = geo.get("target_footprints", {})
    for layer_id, target in targets.items():
        if layer_id not in placements:
            continue
        p = placements[layer_id]
        layer = layer_by_id(config, layer_id)
        aspect = mosaic_aspect(project_root, layer_id, layer)
        center_lat = float(p["center_lat"])
        center_lon = float(p["center_lon"])

        if "span_lat_deg" in target:
            span_lat = float(target["span_lat_deg"])
            span_lon = span_lon_corrected(span_lat, aspect, center_lat)
        elif "max_span_deg" in target:
            max_span = float(target["max_span_deg"])
            cos_lat = max(0.15, abs(math.cos(math.radians(center_lat))))
            lon_per_lat = aspect / cos_lat
            if lon_per_lat >= 1.0:
                span_lon = max_span
                span_lat = max_span / lon_per_lat
            else:
                span_lat = max_span
                span_lon = span_lon_corrected(span_lat, aspect, center_lat)
        else:
            continue

        placements[layer_id] = placement_dict(
            center_lon,
            center_lat,
            span_lon,
            span_lat,
            source=p["source"] + " (target footprint)",
        )


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "globe.json"
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)

    geo = config.get("geographic_placement")
    if not geo:
        raise SystemExit("config/globe.json missing geographic_placement")

    if not geo.get("mgrs_centers"):
        raise SystemExit("geographic_placement.mgrs_centers required")

    config["placement_mode"] = "geographic"

    placements = mgrs_placements(config, project_root, geo)
    frozen_ids = set(geo.get("freeze_position", []))
    margin = float(geo.get("separation_margin_deg", 0.35))
    # Keep MGRS-pinned majors at their grid centers; only nudge unpinned layers.
    frozen_ids |= {lid for lid in geo.get("mgrs_centers", {}) if lid != "maelstrom"}
    nudge_apart(
        placements,
        margin=margin,
        step=float(geo.get("nudge_step_deg", 0.25)),
        frozen=frozen_ids,
    )
    apply_maelstrom(config, placements, geo)
    apply_maelstrom_satellites(config, project_root, geo, placements)
    apply_parent_offset_placements(config, project_root, geo, placements)
    apply_offsets(geo, placements)
    apply_target_footprints(project_root, config, geo, placements)

    if geo.get("shrink_spans_for_separation", True):
        before = count_overlaps(placements, margin)
        shrunk = shrink_spans_to_separate(
            placements,
            margin,
            min_span_fraction=float(geo.get("min_span_fraction", 0.55)),
            min_span_deg=float(geo.get("min_span_deg", 1.0)),
            shrink_exempt=set(geo.get("core_10_regions", []))
            | set(geo.get("silhouette_islands", []))
            | set(geo.get("minor_isles", [])),
        )
        after = count_overlaps(placements, margin)
        print(
            f"Span shrink (centers fixed): {before} overlapping pair(s) -> {after}; "
            f"{shrunk} region(s) tightened"
        )

    print("MGRS-centered placements:\n")
    for layer in config.get("layers", []):
        layer_id = layer.get("id")
        if layer_id not in placements:
            continue
        layer["earth_placement"] = dict(placements[layer_id])
        rotation = geo.get("overlay_rotations", {}).get(layer_id)
        if rotation is not None:
            layer["earth_placement"]["rotation_deg"] = float(rotation)
        p = layer["earth_placement"]
        mgrs_code = geo.get("mgrs_centers", {}).get(layer_id, "")
        tag = f" [{mgrs_code}]" if mgrs_code else ""
        print(
            f"  {layer_id:20} center=({p['center_lon']:8.2f}, {p['center_lat']:7.2f})  "
            f"span={p['span_lon']:.1f}x{p['span_lat']:.2f}°{tag}"
        )

    print(f"\nPacific anchor: ({config['anchor']['earth_lon']}, {config['anchor']['earth_lat']})")

    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")

    print(f"\nUpdated {config_path}")
    print("Rebuild: python3 scripts/build_world_globe.py --kml-only --skip-poster")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Build the merged Azeroth world globe:
  - Zoom-out poster layer from the master reference image
  - Per-region minimap layers positioned via poster_placement in globe.json

Usage:
    python3 scripts/derive_poster_placements.py   # refresh placements from poster
    python3 scripts/build_world_globe.py            # build everything
    python3 scripts/build_world_globe.py --kml-only # regenerate KML only
"""

from __future__ import annotations

import argparse
import copy
import math
import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Run: pip3 install Pillow")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from globe_placement import layer_by_id, layer_earth_bounds, load_globe_config, poster_full_earth_bounds, resolve_raw_input

from campaign_tier_lod import append_campaign_package_folder

try:
    from build_campaign_live import build_campaign_live_kml
except ImportError:
    build_campaign_live_kml = None
from build_kml_superoverlay import (
    detail_link_min_lod_pixels,
    detail_link_min_lod_pixels_for_layer,
    handoff_pixels_for_bounds,
    merge_variant_config,
    overview_link_lod_band,
    png_tier_lod_band,
    pixels_for_eye_altitude,
    resolve_overview_png_tiers,
)
from build_pacific_vignette import DEFAULT_CORE_10, envelope_bounds
from build_terrain_underlay import build_terrain_underlay
from explorer_release import explorer_document_description, load_explorer_release
from places_hierarchy import (
    CONTINENTS_FOLDER,
    MAJOR_ISLANDS_FOLDER,
    MINOR_ISLES_FOLDER,
    MAP_LAYERS_FOLDER,
    OTHER_WORLDS_FOLDER,
    PLAYER_MAP_LINK_NAME,
    bucket_regions_by_parent,
    core_parent_ids,
    make_folder,
    parent_label,
    places_hierarchy_enabled,
    split_pacific_and_opposite,
)
from quick_view import (
    append_document_planet_look_at,
    append_lookat_placemark,
    append_quick_view_bookmarks,
    miles_to_range_m,
)

KML_NS = "http://www.opengis.net/kml/2.2"
OUTPUT_TILE_PX = 256


def layer_detail_pyramids_enabled(layer: dict, config: dict) -> bool:
    if "detail_pyramids_enabled" in layer:
        return bool(layer["detail_pyramids_enabled"])
    return config.get("zoom_transition", {}).get("detail_pyramids_enabled", True)


def _network_link_refresh(
    config: dict,
    link_class: str,
) -> tuple[str | None, int | None]:
    """Per-link-class viewRefresh policy. mode=None → omit refresh (manual campaign)."""
    zoom_cfg = config.get("zoom_transition", {})
    class_cfg = (zoom_cfg.get("network_link_refresh") or {}).get(link_class, {})
    if class_cfg:
        mode = class_cfg.get("mode")
        if mode in (None, "manual"):
            return None, None
        time_val = class_cfg.get("time", zoom_cfg.get("network_link_view_refresh_time", 2))
        return str(mode), int(time_val)
    mode = str(zoom_cfg.get("network_link_view_refresh_mode", "onStop"))
    refresh_time = int(zoom_cfg.get("network_link_view_refresh_time", 2))
    return mode, refresh_time


def _detail_network_link_settings(config: dict) -> tuple[str | None, int | None, float]:
    zoom_cfg = config.get("zoom_transition", {})
    mode, refresh_time = _network_link_refresh(config, "detail")
    bound_scale = float(zoom_cfg.get("network_link_view_bound_scale", 1.0))
    return mode, refresh_time, bound_scale


def _append_detail_network_link(
    parent: ET.Element,
    layer: dict,
    layer_id: str,
    bounds: tuple[float, float, float, float],
    *,
    detail_href_prefix: str,
    config: dict,
) -> None:
    """Lazy detail NetworkLink — onStop refresh avoids onRegion reload flicker."""
    label = layer.get("label", layer_id)
    link_elem = ET.SubElement(parent, f"{{{KML_NS}}}NetworkLink")
    ET.SubElement(link_elem, f"{{{KML_NS}}}name").text = f"{label} (detail)"
    ET.SubElement(link_elem, f"{{{KML_NS}}}open").text = "0"
    region = ET.SubElement(link_elem, f"{{{KML_NS}}}Region")
    box = ET.SubElement(region, f"{{{KML_NS}}}LatLonAltBox")
    west, south, east, north = bounds
    for side, value in (
        ("north", north),
        ("south", south),
        ("east", east),
        ("west", west),
    ):
        ET.SubElement(box, f"{{{KML_NS}}}{side}").text = f"{value:.8f}"
    region_handoff = handoff_pixels_for_bounds(bounds, config)
    link_min_lod = detail_link_min_lod_pixels_for_layer(region_handoff, layer, config)
    lod = ET.SubElement(region, f"{{{KML_NS}}}Lod")
    ET.SubElement(lod, f"{{{KML_NS}}}minLodPixels").text = str(link_min_lod)
    refresh_mode, refresh_time, bound_scale = _detail_network_link_settings(config)
    link = ET.SubElement(link_elem, f"{{{KML_NS}}}Link")
    ET.SubElement(link, f"{{{KML_NS}}}href").text = (
        f"{detail_href_prefix}{layer_id}/detail.kml"
    )
    if refresh_mode:
        ET.SubElement(link, f"{{{KML_NS}}}viewRefreshMode").text = refresh_mode
        ET.SubElement(link, f"{{{KML_NS}}}viewRefreshTime").text = str(refresh_time)
    ET.SubElement(link, f"{{{KML_NS}}}viewBoundScale").text = str(bound_scale)
    print(f"  lazy detail: {layer_id} (preload {link_min_lod}px)")


def layer_build_tiers(layer: dict, config: dict, default_tiers: tuple[str, ...]) -> tuple[str, ...]:
    if "full" in default_tiers:
        return default_tiers
    if layer_detail_pyramids_enabled(layer, config):
        tiers = list(default_tiers)
        if "detail" not in tiers and "overview" in tiers:
            tiers.append("detail")
        return tuple(tiers)
    return tuple(tier for tier in default_tiers if tier != "detail")


def build_poster_layer(project_root: Path, kml_only: bool) -> Path:
    config = load_globe_config(project_root)
    wp = config.get("world_poster", {})
    poster_dir = project_root / "01-raw-export" / "maps" / "azeroth" / "poster"
    poster_file = wp.get("file", "Azeroth Master Reference.png")
    poster_path = poster_dir / poster_file
    if not poster_path.exists():
        candidates = []
        for suffix in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
            candidates.extend(p for p in sorted(poster_dir.glob(suffix)) if p.name != ".gitkeep")
        if not candidates:
            raise SystemExit(f"Poster not found in {poster_dir}")
        poster_path = candidates[0]

    slug = "world_poster"
    tiles_root = project_root / "02-tiles" / slug
    kml_path = project_root / "03-kml" / slug / "doc.kml"
    earth_bounds = poster_full_earth_bounds(config)
    west, south, east, north = earth_bounds
    anchor = config.get("anchor", {})

    if not kml_only:
        poster = Image.open(poster_path).convert("RGBA")
        width, height = poster.size
        max_z = max(
            math.ceil(math.log2(max(1, width / OUTPUT_TILE_PX))),
            math.ceil(math.log2(max(1, height / OUTPUT_TILE_PX))),
        )
        tiles_root.mkdir(parents=True, exist_ok=True)

        def tiles_at_zoom(zoom: int) -> tuple[int, int]:
            scale = 2 ** (max_z - zoom)
            nx = max(1, math.ceil(width / (OUTPUT_TILE_PX * scale)))
            ny = max(1, math.ceil(height / (OUTPUT_TILE_PX * scale)))
            return nx, ny

        print(f"Building poster pyramid from {poster_path.name} ({width}x{height}), zoom 0..{max_z}")
        for z in range(max_z, -1, -1):
            nx, ny = tiles_at_zoom(z)
            scale = 2 ** (max_z - z)
            for ty in range(ny):
                for tx in range(nx):
                    gx0 = tx * OUTPUT_TILE_PX * scale
                    gy0 = ty * OUTPUT_TILE_PX * scale
                    gx1 = min(width, gx0 + OUTPUT_TILE_PX * scale)
                    gy1 = min(height, gy0 + OUTPUT_TILE_PX * scale)
                    tile = poster.crop((gx0, gy0, gx1, gy1))
                    if tile.size != (OUTPUT_TILE_PX, OUTPUT_TILE_PX):
                        tile = tile.resize((OUTPUT_TILE_PX, OUTPUT_TILE_PX), Image.Resampling.LANCZOS)
                    out_dir = tiles_root / str(z) / str(tx)
                    out_dir.mkdir(parents=True, exist_ok=True)
                    tile.save(out_dir / f"{ty}.png", optimize=True)

    max_z = 0
    if tiles_root.exists():
        zoom_dirs = [int(p.name) for p in tiles_root.iterdir() if p.is_dir() and p.name.isdigit()]
        if zoom_dirs:
            max_z = max(zoom_dirs)

    ET.register_namespace("", KML_NS)
    doc = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(doc, f"{{{KML_NS}}}Document")
    ET.SubElement(document, f"{{{KML_NS}}}name").text = "Azeroth World"

    look_at = ET.SubElement(document, f"{{{KML_NS}}}LookAt")
    ET.SubElement(look_at, f"{{{KML_NS}}}longitude").text = f"{float(anchor.get('earth_lon', -160.0)):.6f}"
    ET.SubElement(look_at, f"{{{KML_NS}}}latitude").text = f"{float(anchor.get('earth_lat', 0.0)):.6f}"
    ET.SubElement(look_at, f"{{{KML_NS}}}altitude").text = "0"
    ET.SubElement(look_at, f"{{{KML_NS}}}range").text = "25000000"

    poster_img = Image.open(poster_path)
    width, height = poster_img.size

    for z in range(max_z + 1):
        scale = 2 ** (max_z - z)
        nx = max(1, math.ceil(width / (OUTPUT_TILE_PX * scale)))
        ny = max(1, math.ceil(height / (OUTPUT_TILE_PX * scale)))
        handoff = int(load_globe_config(project_root).get("zoom_transition", {}).get("poster_handoff_lod_pixels", 256))
        if z == 0:
            min_lod = 1
            max_lod = handoff
        elif z == max_z:
            min_lod = max(32, OUTPUT_TILE_PX // (2 ** (max_z - z)))
            max_lod = -1
        else:
            min_lod = max(32, OUTPUT_TILE_PX // (2 ** (max_z - z)))
            max_lod = -1

        for ty in range(ny):
            for tx in range(nx):
                png_path = tiles_root / str(z) / str(tx) / f"{ty}.png"
                if not png_path.exists():
                    continue

                u0 = (tx * OUTPUT_TILE_PX * scale) / width
                u1 = min(1.0, ((tx + 1) * OUTPUT_TILE_PX * scale) / width)
                v0 = (ty * OUTPUT_TILE_PX * scale) / height
                v1 = min(1.0, ((ty + 1) * OUTPUT_TILE_PX * scale) / height)
                tile_west = west + (east - west) * u0
                tile_east = west + (east - west) * u1
                tile_north = north - (north - south) * v0
                tile_south = north - (north - south) * v1

                rel_href = Path("..") / ".." / "02-tiles" / slug / str(z) / str(tx) / f"{ty}.png"
                overlay = ET.SubElement(document, f"{{{KML_NS}}}GroundOverlay")
                ET.SubElement(overlay, f"{{{KML_NS}}}name").text = f"Poster z{z} {tx}/{ty}"
                ET.SubElement(overlay, f"{{{KML_NS}}}drawOrder").text = str(z)

                region = ET.SubElement(overlay, f"{{{KML_NS}}}Region")
                box = ET.SubElement(region, f"{{{KML_NS}}}LatLonAltBox")
                for side, value in (
                    ("north", tile_north),
                    ("south", tile_south),
                    ("east", tile_east),
                    ("west", tile_west),
                ):
                    ET.SubElement(box, f"{{{KML_NS}}}{side}").text = f"{value:.8f}"
                lod = ET.SubElement(region, f"{{{KML_NS}}}Lod")
                ET.SubElement(lod, f"{{{KML_NS}}}minLodPixels").text = str(min_lod)
                ET.SubElement(lod, f"{{{KML_NS}}}maxLodPixels").text = str(max_lod)

                icon = ET.SubElement(overlay, f"{{{KML_NS}}}Icon")
                ET.SubElement(icon, f"{{{KML_NS}}}href").text = rel_href.as_posix()
                latlon = ET.SubElement(overlay, f"{{{KML_NS}}}LatLonBox")
                for side, value in (
                    ("north", tile_north),
                    ("south", tile_south),
                    ("east", tile_east),
                    ("west", tile_west),
                ):
                    ET.SubElement(latlon, f"{{{KML_NS}}}{side}").text = f"{value:.8f}"

    kml_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(doc)
    ET.indent(tree, space="  ")
    tree.write(kml_path, encoding="utf-8", xml_declaration=True)
    print(f"Poster KML: {kml_path}")
    return kml_path


def build_region_layers(
    project_root: Path,
    kml_only: bool,
    layer_ids: list[str] | None,
    *,
    tiers: tuple[str, ...] = ("full",),
    variant: str | None = None,
    raw_root: str | None = None,
) -> list[str]:
    config = load_globe_config(project_root)
    variant_cfg = config.get("world_variants", {}).get(variant or "", {})
    regions_from_raw = set(variant_cfg.get("regions_from_raw", []))
    built: list[str] = []
    for layer in config.get("layers", []):
        layer_id = layer.get("id")
        if layer_id == "azeroth" or not layer.get("enabled", False):
            continue
        if layer.get("layer_type") not in ("minimap", "subterranean"):
            continue
        if layer_ids and layer_id not in layer_ids:
            continue
        if not layer.get("earth_placement") and not layer.get("poster_placement"):
            print(f"[!] Skipping {layer_id}: no earth_placement or poster_placement")
            continue

        label = layer.get("label", layer_id)
        if variant:
            print(f"\n=== Building {label} [{variant}] ===")
        else:
            print(f"\n=== Building {label} ===")
        layer_raw_root = raw_root
        layer_kml_only = kml_only
        if variant and regions_from_raw:
            if layer.get("use_full_export"):
                layer_raw_root = None
            elif layer_id in regions_from_raw:
                layer_raw_root = layer_raw_root or variant_cfg.get("raw_root", "rawfilenoocean")
            else:
                layer_raw_root = None
                if not kml_only:
                    layer_kml_only = True

        if "tiles_subdir" in layer:
            tiles_check = (
                project_root / "02-tiles" / layer["tiles_subdir"] / layer_id
                if layer.get("tiles_subdir")
                else project_root / "02-tiles" / layer_id
            )
        else:
            tiles_sub = variant_cfg.get("tiles_subdir") if variant else None
            tiles_check = project_root / "02-tiles"
            if tiles_sub:
                tiles_check = tiles_check / tiles_sub
            tiles_check = tiles_check / layer_id
        detail_enabled = layer_detail_pyramids_enabled(layer, config)
        if layer_kml_only and detail_enabled and not (tiles_check / "0").exists():
            layer_kml_only = False

        for tier in layer_build_tiers(layer, config, tiers):
            cmd = [
                sys.executable,
                str(project_root / "scripts" / "build_kml_superoverlay.py"),
                "--layer-id",
                layer_id,
                "--tier",
                tier,
            ]
            if variant:
                cmd.extend(["--variant", variant])
            if layer_raw_root:
                cmd.extend(["--raw-root", layer_raw_root])
            if "tiles_subdir" in layer:
                if layer.get("tiles_subdir"):
                    cmd.extend(["--tiles-subdir", layer["tiles_subdir"]])
            else:
                sub = variant_cfg.get("tiles_subdir")
                if sub and variant:
                    cmd.extend(["--tiles-subdir", sub])
            if layer_kml_only:
                cmd.append("--kml-only")
            subprocess.run(cmd, check=True)
        built.append(layer_id)
    return built


def _collect_ground_overlays(kml_path: Path) -> list[ET.Element]:
    if not kml_path.exists():
        return []
    root = ET.parse(kml_path).getroot()
    document = root.find(f"{{{KML_NS}}}Document")
    if document is None:
        return []
    return list(document.findall(f"{{{KML_NS}}}GroundOverlay"))


def _rewrite_overlay_hrefs(
    overlay: ET.Element,
    source_kml: Path,
    target_kml: Path,
) -> ET.Element:
    """Rebase tile hrefs when inlining region overview into world/doc.kml."""
    cloned = copy.deepcopy(overlay)
    for href in cloned.iter(f"{{{KML_NS}}}href"):
        if not href.text or not href.text.endswith(".png"):
            continue
        abs_png = (source_kml.parent / href.text).resolve()
        href.text = Path(os.path.relpath(abs_png, target_kml.parent.resolve())).as_posix()
    return cloned


def _append_look_at(document: ET.Element, config: dict) -> None:
    append_document_planet_look_at(document, config)


def _make_folder(
    parent: ET.Element,
    name: str,
    *,
    open_default: int = 0,
    description: str | None = None,
) -> ET.Element:
    return make_folder(parent, name, open_default=open_default, description=description)


def _write_kml_document(
    path: Path,
    *,
    title: str,
    config: dict,
    children: list[ET.Element],
) -> None:
    ET.register_namespace("", KML_NS)
    kml = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(kml, f"{{{KML_NS}}}Document")
    ET.SubElement(document, f"{{{KML_NS}}}name").text = title
    _append_look_at(document, config)
    for child in children:
        document.append(copy.deepcopy(child))
    tree = ET.ElementTree(kml)
    ET.indent(tree, space="  ")
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _write_player_variant_kmls(
    *,
    project_root: Path,
    variant: str,
    variant_cfg: dict,
    config: dict,
    world_kml: Path,
    document: ET.Element,
) -> None:
    maps_rel = variant_cfg.get("maps_entry")
    player_rel = variant_cfg.get("player_entry")
    if not maps_rel or not player_rel:
        return

    campaign_folder = None
    map_layers_folder = None
    for child in document:
        if child.tag != f"{{{KML_NS}}}Folder":
            continue
        name_el = child.find(f"{{{KML_NS}}}name")
        name = (name_el.text or "") if name_el is not None else ""
        if name == "Campaign Board":
            campaign_folder = child
        elif name == MAP_LAYERS_FOLDER:
            map_layers_folder = child

    if campaign_folder is None or map_layers_folder is None:
        print("[!] player variant KMLs skipped — Campaign Board or Map layers missing")
        return

    maps_path = project_root / maps_rel
    player_path = project_root / player_rel
    _write_kml_document(
        maps_path,
        title="WOW Commander Alpha maps",
        config=config,
        children=[map_layers_folder],
    )

    maps_href = Path(os.path.relpath(maps_path.resolve(), player_path.parent.resolve())).as_posix()
    player_kml = ET.Element(f"{{{KML_NS}}}kml")
    player_doc = ET.SubElement(player_kml, f"{{{KML_NS}}}Document")
    ET.SubElement(player_doc, f"{{{KML_NS}}}name").text = "WOW Commander Alpha (play)"
    _append_look_at(player_doc, config)
    player_doc.append(copy.deepcopy(campaign_folder))
    _append_viewpoint_bookmarks(player_doc, config)
    maps_link = ET.SubElement(player_doc, f"{{{KML_NS}}}NetworkLink")
    ET.SubElement(maps_link, f"{{{KML_NS}}}name").text = PLAYER_MAP_LINK_NAME
    ET.SubElement(maps_link, f"{{{KML_NS}}}open").text = "0"
    link_elem = ET.SubElement(maps_link, f"{{{KML_NS}}}Link")
    ET.SubElement(link_elem, f"{{{KML_NS}}}href").text = maps_href
    tree = ET.ElementTree(player_kml)
    ET.indent(tree, space="  ")
    player_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(player_path, encoding="utf-8", xml_declaration=True)
    print(f"  player entry: {player_path}")
    print(f"  maps board: {maps_path}")

    deploy = str(variant_cfg.get("campaign_deploy_mode", "local"))
    if deploy == "hosted" and variant_cfg.get("campaign_base_url"):
        from campaign_deploy import apply_hosted_post_setup

        result = apply_hosted_post_setup(
            project_root,
            variant=variant,
            rebuild_views=False,
        )
        if result.get("patched"):
            print(f"  hosted player links: view/{result.get('player_cell')}/ ({result['patched']} NetworkLink(s))")


def _region_min_lod_pixels(
    earth_bounds: tuple[float, float, float, float],
    config: dict,
) -> int:
    """
    Eye-altitude threshold for lazy overview NetworkLinks (per-region handoff).

    Converts overview_load_max_miles (default planet silhouette range) into minLodPixels
    so continents appear at the same camera altitude, not only after zooming to ~2000 mi.
    """
    lazy = config.get("viewpoints", {}).get("lazy_links", {})
    load_miles = float(
        lazy.get(
            "overview_load_max_miles",
            config.get("zoom_transition", {})
            .get("camera_tiers", {})
            .get("silhouette_visible_from_miles", 10000),
        )
    )
    handoff = handoff_pixels_for_bounds(earth_bounds, config)
    return max(48, pixels_for_eye_altitude(handoff, load_miles, config))


def _append_viewpoint_bookmarks(document: ET.Element, config: dict) -> None:
    if append_quick_view_bookmarks(document, config):
        return

    presets = config.get("viewpoints", {}).get("presets", [])
    if not presets:
        return

    folder = _make_folder(document, "Quick View", open_default=0)
    for preset in presets:
        append_lookat_placemark(
            folder,
            preset.get("label", preset.get("id", "View")),
            float(preset.get("lon", -160)),
            float(preset.get("lat", 0)),
            float(preset.get("range_m", 5_000_000)),
            tier=preset.get("id", "view"),
            range_miles=float(preset.get("range_m", 5_000_000)) / miles_to_range_m(1),
        )


def _tier_link_min_lod_pixels(
    earth_bounds: tuple[float, float, float, float],
    config: dict,
    visible_from_miles: float,
) -> int:
    """NetworkLink preload threshold for one PNG tier (eye altitude in miles)."""
    handoff = handoff_pixels_for_bounds(earth_bounds, config)
    overlap = float(config.get("zoom_transition", {}).get("lod_overlap_fraction", 0.08))
    min_px = max(48, pixels_for_eye_altitude(handoff, visible_from_miles, config))
    pad = max(1, int(min_px * overlap))
    return max(48, min_px - pad)


def resolve_campaign_region_ids(config: dict, variant_cfg: dict) -> list[str]:
    """Theaters with campaign/{id}.kml — core-10 plus optional islands."""
    geo = config.get("geographic_placement", {})
    ids: list[str] = list(geo.get("core_10_regions", DEFAULT_CORE_10))
    if variant_cfg.get("campaign_include_secondary_islands", True):
        for rid in geo.get("silhouette_islands", []):
            if rid not in ids:
                ids.append(rid)
    if variant_cfg.get("campaign_include_minor_isles", True):
        for rid in geo.get("minor_isles", []):
            if rid not in ids:
                ids.append(rid)
    for rid in variant_cfg.get("campaign_extra_regions") or []:
        if rid not in ids:
            ids.append(rid)
    return [rid for rid in ids if layer_by_id(config, rid)]


def campaign_href_for_region(
    region_id: str,
    *,
    world_kml: Path,
    shell_path: Path,
    variant_cfg: dict,
    viewer_role: str | None = None,
) -> str:
    deploy = str(variant_cfg.get("campaign_deploy_mode", "local"))
    base_url = str(variant_cfg.get("campaign_base_url", "")).rstrip("/")
    use_views = bool(variant_cfg.get("campaign_hosted_views", True))
    if deploy == "hosted" and base_url:
        if use_views and viewer_role in {"red-cell", "blue-cell", "white-cell"}:
            return f"{base_url}/view/{viewer_role}/{region_id}.kml"
        return f"{base_url}/campaign/{region_id}.kml"
    return Path(os.path.relpath(shell_path.resolve(), world_kml.parent.resolve())).as_posix()


def write_regional_campaign_shell(
    campaign_dir: Path,
    region_id: str,
    label: str,
    bounds: tuple[float, float, float, float],
) -> Path:
    """Empty turn-state shell for one theater — Campaign Package with faction/tier folders."""
    campaign_dir.mkdir(parents=True, exist_ok=True)
    out_path = campaign_dir / f"{region_id}.kml"
    if out_path.exists():
        return out_path
    west, south, east, north = bounds
    kml = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(kml, f"{{{KML_NS}}}Document")
    ET.SubElement(document, f"{{{KML_NS}}}name").text = f"{label} campaign"
    ET.SubElement(document, f"{{{KML_NS}}}description").text = (
        f"Turn state for {label}. Use Campaign Package → red-cell or blue-cell → "
        "one tier per marker (Strategic / Operational / Tactical). Export turns: "
        "python3 scripts/package_wargame_client.py --turn N --player Name"
    )
    append_campaign_package_folder(document)
    tree = ET.ElementTree(kml)
    ET.indent(tree, space="  ")
    tree.write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


def _append_campaign_links(
    document: ET.Element,
    *,
    project_root: Path,
    world_kml: Path,
    config: dict,
    variant_cfg: dict,
    wowcommander: bool,
    variant: str = "wowcommanderalpha",
) -> None:
    campaign_rel = config.get(
        "campaign_kml",
        config.get("world_index", {}).get("campaign_kml", "03-kml/campaign/doc.kml"),
    )
    campaign_path = project_root / campaign_rel
    if not campaign_path.exists():
        return

    campaign_dir = campaign_path.parent
    refresh_mode = str(variant_cfg.get("campaign_refresh_mode", "manual"))
    interval_s = int(variant_cfg.get("campaign_refresh_interval_seconds", 60))
    use_regions = bool(variant_cfg.get("campaign_regions", False))
    campaign_label = "Campaign Board" if wowcommander else "Campaign overlays"

    def _link_campaign_file(
        parent: ET.Element,
        name: str,
        href: str,
        bounds: tuple[float, float, float, float] | None,
        *,
        lazy: bool,
        min_lod: int | None = None,
    ) -> None:
        link = ET.SubElement(parent, f"{{{KML_NS}}}NetworkLink")
        ET.SubElement(link, f"{{{KML_NS}}}name").text = name
        ET.SubElement(link, f"{{{KML_NS}}}open").text = "0" if lazy else "1"
        if bounds and min_lod is not None:
            west, south, east, north = bounds
            region = ET.SubElement(link, f"{{{KML_NS}}}Region")
            box = ET.SubElement(region, f"{{{KML_NS}}}LatLonAltBox")
            ET.SubElement(box, f"{{{KML_NS}}}north").text = f"{north:.8f}"
            ET.SubElement(box, f"{{{KML_NS}}}south").text = f"{south:.8f}"
            ET.SubElement(box, f"{{{KML_NS}}}east").text = f"{east:.8f}"
            ET.SubElement(box, f"{{{KML_NS}}}west").text = f"{west:.8f}"
            lod = ET.SubElement(region, f"{{{KML_NS}}}Lod")
            ET.SubElement(lod, f"{{{KML_NS}}}minLodPixels").text = str(min_lod)
        link_elem = ET.SubElement(link, f"{{{KML_NS}}}Link")
        ET.SubElement(link_elem, f"{{{KML_NS}}}href").text = href
        if refresh_mode == "interval":
            ET.SubElement(link_elem, f"{{{KML_NS}}}viewRefreshMode").text = "onInterval"
            ET.SubElement(link_elem, f"{{{KML_NS}}}viewRefreshTime").text = str(interval_s)

    places_mode = str(variant_cfg.get("campaign_places_mode", "network_link"))

    if use_regions and places_mode == "direct_open":
        region_ids = resolve_campaign_region_ids(config, variant_cfg)
        campaign_folder = ET.SubElement(document, f"{{{KML_NS}}}Folder")
        ET.SubElement(campaign_folder, f"{{{KML_NS}}}name").text = campaign_label
        ET.SubElement(campaign_folder, f"{{{KML_NS}}}open").text = "1"
        ET.SubElement(campaign_folder, f"{{{KML_NS}}}description").text = (
            "Campaign markers are editable only when you open theater files directly "
            "(File → Open). NetworkLink trees are read-only in Google Earth Pro. "
            "Example: campaign/kalimdor.kml — keep doc.kml open for the map; markers "
            "from open theater files still display on the globe."
        )
        theaters_folder = ET.SubElement(campaign_folder, f"{{{KML_NS}}}Folder")
        ET.SubElement(theaters_folder, f"{{{KML_NS}}}name").text = "Theater files (File → Open)"
        ET.SubElement(theaters_folder, f"{{{KML_NS}}}open").text = "1"
        ET.SubElement(theaters_folder, f"{{{KML_NS}}}description").text = (
            "Open the campaign file for each theater you are playing:\n"
            + "\n".join(
                f"  campaign/{region_id}.kml"
                for region_id in region_ids
            )
        )
        print(
            f"  campaign board: direct_open mode ({len(region_ids)} theater files — no NetworkLinks)"
        )
    elif use_regions:
        region_ids = resolve_campaign_region_ids(config, variant_cfg)
        campaign_folder = ET.SubElement(document, f"{{{KML_NS}}}Folder")
        ET.SubElement(campaign_folder, f"{{{KML_NS}}}name").text = campaign_label
        ET.SubElement(campaign_folder, f"{{{KML_NS}}}open").text = "0"
        if places_mode == "live_edit":
            ET.SubElement(campaign_folder, f"{{{KML_NS}}}description").text = (
                "VIEW: NetworkLinks below (read-only, lazy load, refresh after turns). "
                "EDIT: open campaign_live.kml — Add → Placemark works there. "
                "After save: python3 scripts/sync_campaign_live.py --push then Refresh links here."
            )
        deploy = variant_cfg.get("campaign_deploy_mode", "local")
        use_hierarchy = wowcommander and places_hierarchy_enabled(config)

        def _link_region(parent: ET.Element, region_id: str) -> None:
            layer = layer_by_id(config, region_id)
            if not layer:
                return
            bounds = layer_earth_bounds(layer, config)
            label = layer.get("label", region_id)
            shell = write_regional_campaign_shell(campaign_dir, region_id, label, bounds)
            href = campaign_href_for_region(
                region_id,
                world_kml=world_kml,
                shell_path=shell,
                variant_cfg=variant_cfg,
            )
            handoff = handoff_pixels_for_bounds(bounds, config)
            link_min, _ = overview_link_lod_band(layer, handoff, config)
            _link_campaign_file(
                parent,
                f"{label} (campaign)",
                href,
                bounds,
                lazy=True,
                min_lod=link_min,
            )
            print(
                f"  campaign region: {href} (load >= {link_min}px, deploy={deploy})"
            )

        if use_hierarchy:
            buckets = bucket_regions_by_parent(region_ids, config)
            for parent_id in core_parent_ids(config):
                continent_folder = _make_folder(
                    campaign_folder,
                    parent_label(config, parent_id),
                    open_default=0,
                )
                for region_id in buckets[parent_id]["continent"]:
                    _link_region(continent_folder, region_id)
                major_folder = _make_folder(
                    continent_folder,
                    MAJOR_ISLANDS_FOLDER,
                    open_default=0,
                )
                for region_id in buckets[parent_id]["major"]:
                    _link_region(major_folder, region_id)
                minor_folder = _make_folder(
                    continent_folder,
                    MINOR_ISLES_FOLDER,
                    open_default=0,
                )
                for region_id in buckets[parent_id]["minor"]:
                    _link_region(minor_folder, region_id)
        else:
            for region_id in region_ids:
                _link_region(campaign_folder, region_id)

        if places_mode == "live_edit" and build_campaign_live_kml is not None:
            build_campaign_live_kml(project_root, variant=variant)
    else:
        campaign_href = Path(
            os.path.relpath(campaign_path.resolve(), world_kml.parent.resolve())
        ).as_posix()
        _link_campaign_file(document, campaign_label, campaign_href, None, lazy=not wowcommander)
        print(f"  linked campaign: {campaign_href}")


def _add_network_link(
    document: ET.Element,
    name: str,
    href: str,
    earth_bounds: tuple[float, float, float, float] | None = None,
    *,
    lazy: bool = True,
    min_lod_pixels: int | None = None,
    max_lod_pixels: int | None = None,
    config: dict | None = None,
    view_refresh_time: int | None = None,
    refresh_class: str | None = None,
    static_links: bool = False,
) -> None:
    """
    NetworkLink for optional / sharing layouts.

    lazy=True: open=0 — never load all regions at startup (prevents GE crashes).
    min_lod_pixels: load only when the region occupies this many screen pixels
    (viewport-based, WyriMaps-style).
    max_lod_pixels: unload when the region is larger than this on screen (planet poster fade-out).
    """
    link_elem = ET.SubElement(document, f"{{{KML_NS}}}NetworkLink")
    ET.SubElement(link_elem, f"{{{KML_NS}}}name").text = name
    ET.SubElement(link_elem, f"{{{KML_NS}}}open").text = "0" if lazy else "1"

    if earth_bounds:
        west, south, east, north = earth_bounds
        region = ET.SubElement(link_elem, f"{{{KML_NS}}}Region")
        box = ET.SubElement(region, f"{{{KML_NS}}}LatLonAltBox")
        ET.SubElement(box, f"{{{KML_NS}}}north").text = f"{north:.8f}"
        ET.SubElement(box, f"{{{KML_NS}}}south").text = f"{south:.8f}"
        ET.SubElement(box, f"{{{KML_NS}}}east").text = f"{east:.8f}"
        ET.SubElement(box, f"{{{KML_NS}}}west").text = f"{west:.8f}"
        lod = ET.SubElement(region, f"{{{KML_NS}}}Lod")
        if min_lod_pixels is not None:
            ET.SubElement(lod, f"{{{KML_NS}}}minLodPixels").text = str(min_lod_pixels)
        if max_lod_pixels is not None:
            ET.SubElement(lod, f"{{{KML_NS}}}maxLodPixels").text = str(max_lod_pixels)

    link = ET.SubElement(link_elem, f"{{{KML_NS}}}Link")
    ET.SubElement(link, f"{{{KML_NS}}}href").text = href
    zoom_cfg = (config or {}).get("zoom_transition", {})
    if not static_links:
        if refresh_class and config:
            refresh_mode, default_time = _network_link_refresh(config, refresh_class)
        else:
            refresh_mode = str(zoom_cfg.get("network_link_view_refresh_mode", "onStop"))
            default_time = int(zoom_cfg.get("network_link_view_refresh_time", 2))
        if refresh_mode:
            ET.SubElement(link, f"{{{KML_NS}}}viewRefreshMode").text = refresh_mode
            refresh_time = (
                view_refresh_time
                if view_refresh_time is not None
                else default_time
            )
            ET.SubElement(link, f"{{{KML_NS}}}viewRefreshTime").text = str(refresh_time)
    ET.SubElement(link, f"{{{KML_NS}}}viewBoundScale").text = str(
        zoom_cfg.get("network_link_view_bound_scale", 1.0)
    )


def write_world_kml(
    project_root: Path,
    region_ids: list[str] | None = None,
    mode: str = "merge",
    *,
    variant: str | None = None,
) -> Path:
    base_config = load_globe_config(project_root)
    config = merge_variant_config(base_config, variant)
    variant_cfg = (base_config.get("world_variants", {}) or {}).get(variant or "world", {})
    if mode == "lazy_links":
        rel_out = config.get("world_index", {}).get("lazy_output", "03-kml/world_lazy/doc.kml")
        world_kml = project_root / rel_out
    elif variant_cfg.get("output"):
        world_kml = project_root / variant_cfg["output"]
    else:
        world_kml = project_root / "03-kml" / "world" / "doc.kml"
    world_kml.parent.mkdir(parents=True, exist_ok=True)
    region_dir = variant_cfg.get("region_kml_dir", "")
    region_root = project_root / "03-kml" / region_dir if region_dir else project_root / "03-kml"
    detail_href_prefix = "" if region_dir else "../"

    if region_ids is None:
        region_ids = [
            layer["id"]
            for layer in config.get("layers", [])
            if layer.get("enabled")
            and layer.get("layer_type") == "minimap"
            and (layer.get("earth_placement") or layer.get("poster_placement"))
        ]

    ET.register_namespace("", KML_NS)
    kml = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(kml, f"{{{KML_NS}}}Document")
    if mode == "lazy_links":
        title = "Azeroth World (lazy)"
    elif variant_cfg.get("label"):
        title = variant_cfg["label"]
    else:
        title = "Azeroth World Globe"
    ET.SubElement(document, f"{{{KML_NS}}}name").text = title
    if variant_cfg.get("explorer_mode"):
        release = load_explorer_release(project_root)
        ET.SubElement(document, f"{{{KML_NS}}}description").text = explorer_document_description(
            release
        )
    _append_look_at(document, config)

    explorer_mode = bool(variant_cfg.get("explorer_mode"))
    wowcommander = variant == "wowcommanderalpha"
    use_places_tree = (
        (wowcommander or explorer_mode)
        and mode == "poster_lazy"
        and places_hierarchy_enabled(config)
    )
    link_static = explorer_mode

    if mode in ("lazy_links", "poster_lazy") and not use_places_tree:
        _append_viewpoint_bookmarks(document, config)

    underlay_cfg = config.get("terrain_underlay") or {}

    def _append_terrain_underlay_link(parent: ET.Element) -> None:
        if not underlay_cfg.get("enabled"):
            return
        underlay_kml = project_root / "03-kml" / (region_dir or "wowcommanderalpha") / "terrain_underlay.kml"
        if underlay_kml.exists():
            underlay_href = Path(
                os.path.relpath(underlay_kml.resolve(), world_kml.parent.resolve())
            ).as_posix()
            link = ET.SubElement(parent, f"{{{KML_NS}}}NetworkLink")
            ET.SubElement(link, f"{{{KML_NS}}}name").text = "Terrain underlay (Earth land)"
            ET.SubElement(link, f"{{{KML_NS}}}open").text = "1"
            link_elem = ET.SubElement(link, f"{{{KML_NS}}}Link")
            ET.SubElement(link_elem, f"{{{KML_NS}}}href").text = underlay_href
            print(f"  terrain underlay: {underlay_href}")
        else:
            print(f"[!] terrain_underlay.enabled but missing {underlay_kml} — run build_terrain_underlay.py")

    if not use_places_tree:
        _append_terrain_underlay_link(document)

    include_poster = config.get("world_poster", {}).get("include_in_globe", False)

    if mode == "poster_lazy":
        poster_count = 0
        if include_poster:
            poster_kml = project_root / "03-kml" / "world_poster" / "doc.kml"
            if not poster_kml.exists():
                raise SystemExit(
                    f"world_poster.include_in_globe=true but poster KML missing at {poster_kml}. "
                    "Rebuild without --skip-poster."
                )
            poster_bounds = poster_full_earth_bounds(config)
            poster_href = Path(os.path.relpath(poster_kml.resolve(), world_kml.parent.resolve())).as_posix()
            zoom_cfg = config.get("zoom_transition", {})
            tiers = zoom_cfg.get("camera_tiers", {})
            poster_fade_miles = float(
                tiers.get(
                    "poster_fade_miles",
                    tiers.get("overview_all_loaded_miles", 3500),
                )
            )
            poster_handoff = handoff_pixels_for_bounds(poster_bounds, config)
            poster_min = int(config.get("viewpoints", {}).get("lazy_links", {}).get("base_min_lod_pixels", 128))
            poster_max = max(poster_min + 1, pixels_for_eye_altitude(poster_handoff, poster_fade_miles, config))
            _add_network_link(
                document,
                "Azeroth theater (planet navigation)",
                poster_href,
                poster_bounds,
                lazy=True,
                min_lod_pixels=poster_min,
                max_lod_pixels=poster_max,
            )
            poster_count = 1
            print(
                f"  poster navigation: {poster_href} "
                f"(visible ~6000–{poster_fade_miles:.0f} mi eye alt, maxLod {poster_max}px)"
            )

        def _append_pacific_vignette_link(parent: ET.Element) -> None:
            if not (wowcommander or explorer_mode):
                return
            vignette_kml = project_root / "03-kml" / (region_dir or "wowcommanderalpha") / "pacific_vignette.kml"
            if vignette_kml.exists():
                geo = config.get("geographic_placement", {})
                core_layers = [
                    layer_by_id(config, lid)
                    for lid in geo.get("core_10_regions", DEFAULT_CORE_10)
                ]
                core_layers = [layer for layer in core_layers if layer]
                if core_layers:
                    zoom_cfg = config.get("zoom_transition", {})
                    tiers = zoom_cfg.get("camera_tiers", {})
                    v_bounds = envelope_bounds(core_layers, config)
                    v_handoff = handoff_pixels_for_bounds(v_bounds, config)
                    v_from = float(tiers.get("vignette_visible_from_miles", 38000))
                    v_until = float(tiers.get("vignette_overview_until_miles", 10000))
                    v_min, v_max = png_tier_lod_band(
                        v_handoff, config, v_from, v_until
                    )
                    link_floor = int(
                        tiers.get(
                            "vignette_link_min_lod_pixels",
                            zoom_cfg.get("vignette_link_min_lod_pixels", 48),
                        )
                    )
                    v_min = max(link_floor, v_min)
                    v_href = Path(
                        os.path.relpath(vignette_kml.resolve(), world_kml.parent.resolve())
                    ).as_posix()
                    _add_network_link(
                        parent,
                        "Azeroth vignette (planet)",
                        v_href,
                        v_bounds,
                        lazy=False,
                        min_lod_pixels=v_min,
                        max_lod_pixels=v_max,
                        config=config,
                        refresh_class=None if link_static else "vignette",
                        static_links=link_static,
                    )
                    print(
                        f"  pacific vignette: {v_href} "
                        f"(load >= {v_min}px, fade by {v_max}px ~{v_until:.0f} mi)"
                    )
            else:
                print(
                    f"[!] pacific_vignette.kml missing at {vignette_kml} "
                    "— run scripts/build_pacific_vignette.py"
                )

        if not use_places_tree:
            _append_pacific_vignette_link(document)

        geo_placement = config.get("geographic_placement", {})
        secondary_islands = set(geo_placement.get("silhouette_islands", []))
        minor_isles = set(geo_placement.get("minor_isles", []))
        lazy_island_ids = secondary_islands | minor_isles
        pacific_region_ids, opposite_region_ids = split_pacific_and_opposite(region_ids, config)
        core_region_ids = [rid for rid in pacific_region_ids if rid not in lazy_island_ids]
        secondary_region_ids = [rid for rid in pacific_region_ids if rid in secondary_islands]
        minor_region_ids = [rid for rid in pacific_region_ids if rid in minor_isles]

        def _append_overview_links(
            parent: ET.Element,
            layer_ids: list[str],
        ) -> None:
            tier_lazy = config.get("zoom_transition", {}).get("overview_tier_lazy_links", True)
            zoom_cfg = config.get("zoom_transition", {})
            for layer_id in layer_ids:
                layer = layer_by_id(config, layer_id)
                if not layer:
                    continue
                bounds = layer_earth_bounds(layer, config)
                label = layer.get("label", layer_id)
                tier_specs = resolve_overview_png_tiers(layer, config)
                tier_handoff = handoff_pixels_for_bounds(bounds, config)
                if tier_specs and tier_lazy:
                    for spec in tier_specs:
                        load_miles = float(spec["visible_from_miles"])
                        tier_min, tier_max_lod = png_tier_lod_band(
                            tier_handoff,
                            config,
                            spec["visible_from_miles"],
                            spec["visible_until_miles"],
                        )
                        overlap = float(zoom_cfg.get("lod_overlap_fraction", 0.08))
                        pad = max(1, int(tier_min * overlap))
                        tier_min = max(48, tier_min - pad)
                        tier_max = (
                            None if spec.get("no_max_lod") else tier_max_lod
                        )
                        tier_href = (
                            f"{detail_href_prefix}{layer_id}/overview_{spec['id']}.kml"
                        )
                        tier_label = spec["id"]
                        if layer_id in lazy_island_ids and tier_label == "silhouette":
                            tier_label = "vignette"
                        _add_network_link(
                            parent,
                            f"{label} ({tier_label})",
                            tier_href,
                            bounds,
                            lazy=True,
                            min_lod_pixels=tier_min,
                            max_lod_pixels=tier_max,
                            config=config,
                            refresh_class=None if link_static else "overview",
                            static_links=link_static,
                        )
                        print(
                            f"  lazy overview {layer_id}/{spec['id']}: "
                            f"load >= {tier_min}px (~{load_miles:.0f} mi)"
                        )
                elif tier_specs:
                    link_min, link_max = overview_link_lod_band(layer, tier_handoff, config)
                    _add_network_link(
                        parent,
                        label,
                        f"{detail_href_prefix}{layer_id}/overview.kml",
                        bounds,
                        lazy=True,
                        min_lod_pixels=link_min,
                        max_lod_pixels=link_max,
                        config=config,
                        refresh_class=None if link_static else "overview",
                        static_links=link_static,
                    )
                    max_label = "∞" if link_max is None else str(link_max)
                    print(
                        f"  lazy overview: {layer_id} "
                        f"(LOD {link_min}–{max_label}px, merged tiers)"
                    )
                else:
                    min_lod = _region_min_lod_pixels(bounds, config)
                    _add_network_link(
                        parent,
                        label,
                        f"{detail_href_prefix}{layer_id}/overview.kml",
                        bounds,
                        lazy=True,
                        min_lod_pixels=min_lod,
                        config=config,
                        refresh_class=None if link_static else "overview",
                        static_links=link_static,
                    )
                    print(f"  lazy overview: {layer_id} (loads when bbox >= {min_lod}px on screen)")

        def _append_detail_links(
            parent: ET.Element,
            layer_ids: list[str],
        ) -> None:
            for layer_id in layer_ids:
                layer = layer_by_id(config, layer_id)
                if not layer or not layer_detail_pyramids_enabled(layer, config):
                    continue
                bounds = layer_earth_bounds(layer, config)
                _append_detail_network_link(
                    parent,
                    layer,
                    layer_id,
                    bounds,
                    detail_href_prefix=detail_href_prefix,
                    config=config,
                )

        if use_places_tree:
            if not explorer_mode:
                _append_campaign_links(
                    document,
                    project_root=project_root,
                    world_kml=world_kml,
                    config=config,
                    variant_cfg=variant_cfg,
                    wowcommander=wowcommander,
                    variant=variant or "wowcommanderalpha",
                )
            map_layers = _make_folder(document, MAP_LAYERS_FOLDER, open_default=0)
            _append_viewpoint_bookmarks(map_layers, config)
            if opposite_region_ids:
                from quick_view import append_opposite_quick_view_bookmarks

                append_opposite_quick_view_bookmarks(
                    map_layers, config, opposite_region_ids
                )
            _append_terrain_underlay_link(map_layers)
            _append_pacific_vignette_link(map_layers)
            buckets = bucket_regions_by_parent(pacific_region_ids, config)
            continents_root = _make_folder(map_layers, CONTINENTS_FOLDER, open_default=0)
            for parent_id in core_parent_ids(config):
                continent_folder = _make_folder(
                    continents_root,
                    parent_label(config, parent_id),
                    open_default=0,
                )
                bucket = buckets[parent_id]
                if bucket["continent"]:
                    _append_overview_links(continent_folder, bucket["continent"])
                major_folder = _make_folder(
                    continent_folder,
                    MAJOR_ISLANDS_FOLDER,
                    open_default=0,
                )
                if bucket["major"]:
                    _append_overview_links(major_folder, bucket["major"])
                    _append_detail_links(major_folder, bucket["major"])
                minor_folder = _make_folder(
                    continent_folder,
                    MINOR_ISLES_FOLDER,
                    open_default=0,
                )
                if bucket["minor"]:
                    _append_overview_links(minor_folder, bucket["minor"])
                    _append_detail_links(minor_folder, bucket["minor"])
            if opposite_region_ids:
                other_root = _make_folder(
                    map_layers,
                    OTHER_WORLDS_FOLDER,
                    open_default=0,
                    description=(
                        "Extra-world zones on the far side of the globe "
                        "(Outland, Draenor, Shadowlands, etc.) when enabled in a release."
                    ),
                )
                for region_id in opposite_region_ids:
                    layer = layer_by_id(config, region_id)
                    if not layer:
                        continue
                    zone_folder = _make_folder(
                        other_root,
                        layer.get("label", region_id),
                        open_default=0,
                    )
                    _append_overview_links(zone_folder, [region_id])
                    _append_detail_links(zone_folder, [region_id])
                print(f"  other worlds: {len(opposite_region_ids)} zone(s)")
            global_detail = config.get("zoom_transition", {}).get("detail_pyramids_enabled", True)
            if global_detail:
                detail_folder = _make_folder(
                    map_layers,
                    "Detail maps (load when zoomed in)",
                    open_default=0,
                )
                _append_detail_links(detail_folder, core_region_ids)
            elif not lazy_island_ids:
                print("  detail pyramids: disabled (overview PNG tiers only)")
            if not explorer_mode:
                _write_player_variant_kmls(
                    project_root=project_root,
                    variant=variant or "wowcommanderalpha",
                    variant_cfg=variant_cfg,
                    config=config,
                    world_kml=world_kml,
                    document=document,
                )
        else:
            _append_overview_links(document, core_region_ids)

            if secondary_region_ids:
                secondary_folder = _make_folder(
                    document,
                    "Pacific islands (vignette + detail)",
                    open_default=0,
                )
                _append_overview_links(secondary_folder, secondary_region_ids)
                _append_detail_links(secondary_folder, secondary_region_ids)

            if minor_region_ids:
                minor_folder = _make_folder(
                    document,
                    "Minor isles (vignette + detail)",
                    open_default=0,
                )
                _append_overview_links(minor_folder, minor_region_ids)
                _append_detail_links(minor_folder, minor_region_ids)

            global_detail = config.get("zoom_transition", {}).get("detail_pyramids_enabled", True)
            if global_detail:
                detail_folder = _make_folder(
                    document,
                    "Detail maps (load when zoomed in)",
                    open_default=0,
                )
                _append_detail_links(detail_folder, core_region_ids)
            elif not lazy_island_ids:
                print("  detail pyramids: disabled (overview PNG tiers only)")

            _append_campaign_links(
                document,
                project_root=project_root,
                world_kml=world_kml,
                config=config,
                variant_cfg=variant_cfg,
                wowcommander=wowcommander,
                variant=variant or "wowcommanderalpha",
            )

        tree = ET.ElementTree(kml)
        ET.indent(tree, space="  ")
        tree.write(world_kml, encoding="utf-8", xml_declaration=True)
        size_kb = world_kml.stat().st_size / 1024
        poster_note = f" + {poster_count} poster" if poster_count else " (lazy regions only)"
        print(f"\nLazy world KML: {world_kml} ({size_kb:.1f} KB, {len(region_ids)} regions{poster_note})")
        return world_kml

    if mode == "tiered":
        wowcommander = variant == "wowcommanderalpha"
        overview_count = 0
        for layer_id in region_ids:
            overview_kml = region_root / layer_id / "overview.kml"
            for overlay in _collect_ground_overlays(overview_kml):
                document.append(_rewrite_overlay_hrefs(overlay, overview_kml, world_kml))
                overview_count += 1

        detail_folder = ET.SubElement(document, f"{{{KML_NS}}}Folder")
        detail_name = "Detail maps (load when zoomed in)"
        ET.SubElement(detail_folder, f"{{{KML_NS}}}name").text = detail_name
        ET.SubElement(detail_folder, f"{{{KML_NS}}}open").text = "0"

        for layer_id in region_ids:
            layer = layer_by_id(config, layer_id)
            if not layer:
                continue
            bounds = layer_earth_bounds(layer, config)
            region_handoff = handoff_pixels_for_bounds(bounds, config)
            link_min_lod = detail_link_min_lod_pixels_for_layer(region_handoff, layer, config)
            _append_detail_network_link(
                detail_folder,
                layer,
                layer_id,
                bounds,
                detail_href_prefix=detail_href_prefix,
                config=config,
            )
            tiers = config.get("zoom_transition", {}).get("camera_tiers", {})
            print(
                f"  overview + detail link: {layer_id} "
                f"(overview handoff {region_handoff}px, link preload {link_min_lod}px "
                f"@ ~{tiers.get('detail_start_miles', 2000)} mi eye alt)"
            )

        _append_campaign_links(
            document,
            project_root=project_root,
            world_kml=world_kml,
            config=config,
            variant_cfg=variant_cfg,
            wowcommander=wowcommander,
            variant=variant or "wowcommanderalpha",
        )

        tree = ET.ElementTree(kml)
        ET.indent(tree, space="  ")
        tree.write(world_kml, encoding="utf-8", xml_declaration=True)
        size_kb = world_kml.stat().st_size / 1024
        print(f"\nTiered world KML: {world_kml} ({size_kb:.1f} KB, {overview_count} overview tiles)")
        return world_kml

    if mode == "merge":
        overlay_count = 0
        if include_poster:
            poster_kml = project_root / "03-kml" / "world_poster" / "doc.kml"
            for overlay in _collect_ground_overlays(poster_kml):
                document.append(overlay)
                overlay_count += 1

        for layer_id in region_ids:
            region_kml = project_root / "03-kml" / layer_id / "doc.kml"
            overlays = _collect_ground_overlays(region_kml)
            if not overlays:
                print(f"[!] No overlays in {region_kml}")
                continue
            for overlay in overlays:
                document.append(overlay)
                overlay_count += 1
            print(f"  merged {len(overlays):5d} overlays from {layer_id}")

        tree = ET.ElementTree(kml)
        ET.indent(tree, space="  ")
        tree.write(world_kml, encoding="utf-8", xml_declaration=True)
        print(f"\nMerged world KML: {world_kml} ({overlay_count} overlays)")
        return world_kml

    # NetworkLink index — lazy_links uses viewport minLodPixels (WyriMaps-style).
    lazy = mode == "lazy_links"
    if include_poster:
        bounds = poster_full_earth_bounds(config)
        _add_network_link(
            document,
            "World map (zoom out)",
            "../world_poster/doc.kml",
            bounds,
            lazy=lazy,
            min_lod_pixels=512 if lazy else 128,
        )

    for layer_id in region_ids:
        layer = layer_by_id(config, layer_id)
        if not layer:
            continue
        bounds = layer_earth_bounds(layer, config)
        label = layer.get("label", layer_id)
        min_lod = _region_min_lod_pixels(bounds, config) if lazy else 128
        _add_network_link(
            document,
            label,
            f"../{layer_id}/doc.kml",
            bounds,
            lazy=True,
            min_lod_pixels=min_lod,
        )
        print(f"  linked {layer_id} (loads when bbox >= {min_lod} px on screen)")

    campaign_rel = config.get("world_index", {}).get("campaign_kml", "03-kml/campaign/doc.kml")
    campaign_path = project_root / campaign_rel
    if campaign_path.exists():
        _add_network_link(document, "Campaign overlays", "../campaign/doc.kml", lazy=False)
        print("  linked campaign/doc.kml")

    tree = ET.ElementTree(kml)
    ET.indent(tree, space="  ")
    tree.write(world_kml, encoding="utf-8", xml_declaration=True)
    size_kb = world_kml.stat().st_size / 1024
    kind = "Lazy viewport index" if lazy else "World index"
    print(f"\n{kind}: {world_kml} ({size_kb:.1f} KB, {len(region_ids)} regions)")
    return world_kml


def main() -> None:
    parser = argparse.ArgumentParser(description="Build merged Azeroth world globe from poster placements")
    parser.add_argument("--kml-only", action="store_true", help="Skip tile pyramids; regenerate KML only")
    parser.add_argument("--layers", nargs="*", help="Only build these layer ids (default: all enabled)")
    parser.add_argument("--skip-poster", action="store_true", help="Skip poster pyramid build")
    parser.add_argument(
        "--network-links",
        action="store_true",
        help="Write 03-kml/world/doc.kml as NetworkLink index (not recommended — use --lazy-links).",
    )
    parser.add_argument(
        "--lazy-links",
        action="store_true",
        help="Write 03-kml/world_lazy/doc.kml — viewport-based NetworkLinks + camera bookmarks.",
    )
    parser.add_argument(
        "--variant",
        default=None,
        help="Build one world variant (default: all in world_index.build_variants).",
    )
    parser.add_argument(
        "--raw-root",
        default=None,
        help="Alternate raw export folder (e.g. rawfilenoocean). Use after manually removing ocean tiles.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config = load_globe_config(project_root)
    mode = config.get("world_index", {}).get("mode", "tiered")
    if args.lazy_links:
        mode = "lazy_links"
    elif args.network_links:
        mode = "network_links"

    include_poster = config.get("world_poster", {}).get("include_in_globe", False)

    if include_poster and not args.skip_poster:
        build_poster_layer(project_root, args.kml_only)
    elif not include_poster:
        print("Poster layer skipped (include_in_globe=false; poster is placement reference only)")

    if mode == "lazy_links":
        tiers = ("full",)
    elif mode in ("tiered", "poster_lazy"):
        tiers = (
            ("overview", "detail")
            if config.get("zoom_transition", {}).get("detail_pyramids_enabled", True)
            else ("overview",)
        )
    else:
        tiers = ("full",)

    variants = [args.variant] if args.variant else config.get("world_index", {}).get(
        "build_variants", ["wowcommanderalpha"]
    )
    built_paths: list[Path] = []
    for variant in variants:
        if len(variants) > 1:
            print(f"\n########## Variant: {variant} ##########")
        variant_config = merge_variant_config(config, variant)
        if (variant_config.get("terrain_underlay") or {}).get("enabled"):
            print("\n=== Terrain underlay ===")
            build_terrain_underlay(project_root, variant_config, variant=variant)
        region_ids = build_region_layers(
            project_root,
            args.kml_only,
            args.layers,
            tiers=tiers,
            variant=variant,
            raw_root=args.raw_root,
        )
        built_paths.append(write_world_kml(project_root, None, mode=mode, variant=variant))

    print("\n=== World globe ready ===")
    if args.lazy_links:
        rel = config.get("world_index", {}).get("lazy_output", "03-kml/world_lazy/doc.kml")
        print(f"Open (lazy): {project_root / rel}")
    for path in built_paths:
        print(f"Open: {path}")


if __name__ == "__main__":
    main()
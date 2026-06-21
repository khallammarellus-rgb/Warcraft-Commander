#!/usr/bin/env python3
"""
Audit NetworkLink count, overlay weight, and link/child LOD alignment for a globe variant.

Usage:
    python3 scripts/audit_globe_performance.py
    python3 scripts/audit_globe_performance.py --variant wowcommanderalpha --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_kml_superoverlay import (
    handoff_pixels_for_bounds,
    merge_variant_config,
    overview_link_lod_band,
    png_tier_lod_band,
    resolve_overview_png_tiers,
)
from globe_placement import layer_by_id, layer_earth_bounds, load_globe_config

KML_NS = "http://www.opengis.net/kml/2.2"
NS = {"k": KML_NS}


def _int_text(elem: ET.Element | None, tag: str, default: int | None = None) -> int | None:
    if elem is None:
        return default
    child = elem.find(f"k:{tag}", NS)
    if child is None or child.text is None:
        return default
    try:
        return int(float(child.text))
    except ValueError:
        return default


def _collect_network_links(kml_path: Path) -> list[dict]:
    if not kml_path.exists():
        return []
    root = ET.parse(kml_path).getroot()
    links: list[dict] = []
    for link in root.findall(".//k:NetworkLink", NS):
        name = (link.findtext("k:name", default="", namespaces=NS) or "").strip()
        href = link.findtext(".//k:Link/k:href", default="", namespaces=NS) or ""
        region = link.find("k:Region", NS)
        lod = region.find("k:Lod", NS) if region is not None else None
        links.append(
            {
                "name": name,
                "href": href,
                "min_lod": _int_text(lod, "minLodPixels"),
                "max_lod": _int_text(lod, "maxLodPixels"),
            }
        )
    return links


def _count_overlays(kml_path: Path) -> int:
    if not kml_path.exists():
        return 0
    root = ET.parse(kml_path).getroot()
    return len(root.findall(".//k:GroundOverlay", NS))


def _overview_overlay_lods(kml_path: Path) -> list[dict]:
    if not kml_path.exists():
        return []
    root = ET.parse(kml_path).getroot()
    rows: list[dict] = []
    for overlay in root.findall(".//k:GroundOverlay", NS):
        name = overlay.findtext("k:name", default="", namespaces=NS) or ""
        region = overlay.find("k:Region", NS)
        lod = region.find("k:Lod", NS) if region is not None else None
        rows.append(
            {
                "name": name,
                "min_lod": _int_text(lod, "minLodPixels"),
                "max_lod": _int_text(lod, "maxLodPixels"),
            }
        )
    return rows


def _count_placemarks(kml_path: Path) -> int:
    if not kml_path.exists():
        return 0
    root = ET.parse(kml_path).getroot()
    return len(root.findall(f".//{{{KML_NS}}}Placemark"))


def _audit_campaign_files(project_root: Path, variant_cfg: dict, config: dict) -> dict:
    from build_world_globe import resolve_campaign_region_ids

    campaign_rel = variant_cfg.get("campaign_kml", "03-kml/wowcommanderalpha/campaign/doc.kml")
    campaign_dir = project_root / Path(campaign_rel).parent
    per_file: list[dict] = []
    total = 0
    for region_id in resolve_campaign_region_ids(config, variant_cfg):
        path = campaign_dir / f"{region_id}.kml"
        if not path.exists():
            continue
        count = _count_placemarks(path)
        total += count
        per_file.append(
            {
                "id": region_id,
                "path": str(path.relative_to(project_root)),
                "placemarks": count,
                "bytes": path.stat().st_size,
            }
        )
    per_file.sort(key=lambda row: row["placemarks"], reverse=True)
    return {
        "placemark_total": total,
        "files": per_file,
        "estimated_turn_kmz_kb": round(max(8, total * 0.5 + len(per_file) * 2), 1),
    }


def _png_cache_bytes(project_root: Path, layer_id: str) -> int:
    tiles = project_root / "02-tiles" / layer_id
    if not tiles.is_dir():
        return 0
    total = 0
    for path in tiles.glob("overview_*.png"):
        total += path.stat().st_size
    return total


def audit_variant(project_root: Path, variant: str) -> dict:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, variant)
    variant_cfg = (base.get("world_variants", {}) or {}).get(variant, {})
    world_kml = project_root / variant_cfg.get("output", f"03-kml/{variant}/doc.kml")
    region_dir_name = variant_cfg.get("region_kml_dir", variant)
    region_root = project_root / "03-kml" / region_dir_name

    world_links = _collect_network_links(world_kml)
    overview_links = [link for link in world_links if "overview" in link["href"]]
    campaign_links = [link for link in world_links if "campaign/" in link["href"]]

    tier_lazy = config.get("zoom_transition", {}).get("overview_tier_lazy_links", True)
    lod_mismatches: list[dict] = []

    region_stats: list[dict] = []
    for layer in config.get("layers", []):
        if not layer.get("enabled") or layer.get("layer_type") != "minimap":
            continue
        layer_id = layer["id"]
        overview_kml = region_root / layer_id / "overview.kml"
        overlay_count = _count_overlays(overview_kml)
        if overlay_count == 0:
            continue
        bounds = layer_earth_bounds(layer, config)
        handoff = handoff_pixels_for_bounds(bounds, config)
        expected_min, expected_max = overview_link_lod_band(layer, handoff, config)
        world_link = next(
            (link for link in world_links if link["href"].endswith(f"{layer_id}/overview.kml")),
            None,
        )
        if world_link and not tier_lazy:
            link_min = world_link.get("min_lod")
            overlays = _overview_overlay_lods(overview_kml)
            first_min = overlays[0]["min_lod"] if overlays else None
            if link_min is not None and first_min is not None and link_min < first_min - 64:
                lod_mismatches.append(
                    {
                        "region": layer_id,
                        "link_min": link_min,
                        "first_overlay_min": first_min,
                        "expected_min": expected_min,
                    }
                )
        region_stats.append(
            {
                "id": layer_id,
                "overlay_count": overlay_count,
                "overview_png_bytes": _png_cache_bytes(project_root, layer_id),
                "world_overview_link": world_link,
                "expected_link_lod": [expected_min, expected_max],
            }
        )

    region_stats.sort(key=lambda row: row["overview_png_bytes"], reverse=True)
    campaign_audit = _audit_campaign_files(project_root, variant_cfg, config)

    return {
        "variant": variant,
        "globe_version": config.get("globe_version", {}).get("id"),
        "world_kml": str(world_kml.relative_to(project_root)),
        "overview_tier_lazy_links": tier_lazy,
        "network_link_count": len(world_links),
        "overview_link_count": len(overview_links),
        "campaign_link_count": len(campaign_links),
        "lod_mismatch_count": len(lod_mismatches),
        "lod_mismatches": lod_mismatches,
        "heaviest_regions": region_stats[:10],
        "refresh_policy": config.get("zoom_transition", {}).get("network_link_refresh"),
        "campaign_deploy_mode": variant_cfg.get("campaign_deploy_mode", "local"),
        "campaign": campaign_audit,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit globe NetworkLink and LOD performance")
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument("--json", action="store_true", help="Emit JSON report")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    report = audit_variant(project_root, args.variant)

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print(f"Globe audit — {report['variant']} ({report['globe_version']})")
    print(f"  world KML: {report['world_kml']}")
    print(f"  overview_tier_lazy_links: {report['overview_tier_lazy_links']}")
    print(f"  NetworkLinks: {report['network_link_count']} total")
    print(f"    overview: {report['overview_link_count']}")
    print(f"    campaign: {report['campaign_link_count']}")
    print(f"  LOD mismatches: {report['lod_mismatch_count']}")
    if report["lod_mismatches"]:
        for row in report["lod_mismatches"]:
            print(
                f"    {row['region']}: link min {row['link_min']}px "
                f"vs overlay min {row['first_overlay_min']}px"
            )
    print("  Heaviest regions (overview PNG cache):")
    for row in report["heaviest_regions"][:5]:
        mb = row["overview_png_bytes"] / (1024 * 1024)
        print(f"    {row['id']}: {row['overlay_count']} overlays, {mb:.1f} MB PNG cache")
    camp = report.get("campaign", {})
    print(
        f"  Campaign: {camp.get('placemark_total', 0)} placemarks, "
        f"est. turn KMZ ~{camp.get('estimated_turn_kmz_kb', 0)} KB "
        f"(deploy={report.get('campaign_deploy_mode', 'local')})"
    )
    for row in (camp.get("files") or [])[:5]:
        if row.get("placemarks"):
            print(f"    {row['id']}: {row['placemarks']} markers")


if __name__ == "__main__":
    main()
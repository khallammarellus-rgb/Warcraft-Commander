"""Read campaign_live.kml or campaign_live.kmz (Google Earth often saves KMZ)."""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from campaign_tier_lod import KML_NS

ET.register_namespace("", KML_NS)


def campaign_live_parent_for_variant(project_root: Path, variant: str) -> Path:
    from build_kml_superoverlay import merge_variant_config
    from globe_placement import load_globe_config

    base = load_globe_config(project_root)
    variant_cfg = (base.get("world_variants", {}) or {}).get(variant, {})
    rel = variant_cfg.get("output", "03-kml/wowcommanderalpha/doc.kml")
    return project_root / Path(rel).parent


def resolve_campaign_live_path(parent_dir: Path) -> Path | None:
    """Prefer KMZ when newer — GEP default save format."""
    kml = parent_dir / "campaign_live.kml"
    kmz = parent_dir / "campaign_live.kmz"
    if kmz.exists() and kml.exists():
        return kmz if kmz.stat().st_mtime >= kml.stat().st_mtime else kml
    if kmz.exists():
        return kmz
    if kml.exists():
        return kml
    return None


def parse_campaign_live_root(path: Path) -> ET.Element:
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path) as archive:
            kml_names = [n for n in archive.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError(f"No KML inside {path}")
            preferred = "doc.kml" if "doc.kml" in kml_names else kml_names[0]
            with archive.open(preferred) as handle:
                return ET.parse(handle).getroot()
    return ET.parse(path).getroot()
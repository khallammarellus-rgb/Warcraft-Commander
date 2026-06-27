"""Role-filtered hosted campaign views for Google Earth NetworkLinks."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from campaign_tier_lod import (
    inject_placemark_tier_regions,
    migrate_to_campaign_package,
    strip_tier_folder_regions,
)
from campaign_visibility import (
    GAME_FORMATS,
    VIEWER_ROLES,
    effective_format,
    filter_campaign_root,
    load_campaign_meta,
    load_reveal_state,
    merge_discovered_into_opponent_view,
    viewer_sees_everything,
)
from campaign_icons import rewrite_icon_hrefs_to_portal
from package_wargame_client import campaign_dir_for_variant

KML_NS = "http://www.opengis.net/kml/2.2"
HOSTED_VIEW_ROLES = ("red-cell", "blue-cell", "white-cell")


def _kml(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def hosted_view_href(base_url: str, role: str, theater_id: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/view/{role}/{theater_id}.kml"


def hosted_master_href(base_url: str, theater_id: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/campaign/{theater_id}.kml"


def filter_theater_kml_for_viewer(
    path: Path,
    *,
    campaign_dir: Path,
    viewer: str | None,
    game_format: str | None = None,
) -> str:
    """Build filtered KML XML for one theater and viewer role (no reveal-state mutation)."""
    meta = load_campaign_meta(campaign_dir)
    fmt = game_format or meta.get("game_format", "no-blind")
    if fmt not in GAME_FORMATS:
        fmt = "no-blind"

    root = ET.parse(path).getroot()
    migrate_to_campaign_package(root)
    strip_tier_folder_regions(root)
    inject_placemark_tier_regions(root)

    state = load_reveal_state(campaign_dir)
    fmt = effective_format(fmt, viewer)
    filtered = filter_campaign_root(root, viewer=viewer, game_format=fmt, state=state)
    if viewer in VIEWER_ROLES and not viewer_sees_everything(fmt, viewer):
        merge_discovered_into_opponent_view(filtered, viewer)

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        filtered, encoding="unicode"
    )


def write_hosted_views(
    project_root: Path,
    out_dir: Path,
    *,
    variant: str = "wowcommanderalpha",
    game_format: str | None = None,
    theaters: list[str] | None = None,
    subpath: str | None = None,
    portal_base: str | None = None,
    game_id: str | None = None,
) -> list[Path]:
    """Write view/{role}/{theater}.kml and campaign/{theater}.kml under out_dir (optional subpath prefix)."""
    if subpath:
        out_dir = out_dir / Path(subpath)
    campaign_dir = campaign_dir_for_variant(project_root, variant)
    written: list[Path] = []

    paths = sorted(campaign_dir.glob("*.kml"))
    paths = [p for p in paths if p.name != "doc.kml" and p.name != "campaign_live.kml"]
    if theaters:
        allow = set(theaters)
        paths = [p for p in paths if p.stem in allow]

    master_dir = out_dir / "campaign"
    master_dir.mkdir(parents=True, exist_ok=True)
    def _maybe_rewrite_icons(xml: str) -> str:
        if portal_base and game_id:
            return rewrite_icon_hrefs_to_portal(xml, portal_base, game_id)
        return xml

    for path in paths:
        dest = master_dir / path.name
        xml = _maybe_rewrite_icons(path.read_text(encoding="utf-8"))
        dest.write_text(xml, encoding="utf-8")
        written.append(dest)

    for role in HOSTED_VIEW_ROLES:
        role_dir = out_dir / "view" / role
        role_dir.mkdir(parents=True, exist_ok=True)
        for path in paths:
            xml = filter_theater_kml_for_viewer(
                path,
                campaign_dir=campaign_dir,
                viewer=role,
                game_format=game_format,
            )
            xml = _maybe_rewrite_icons(xml)
            dest = role_dir / path.name
            dest.write_text(xml, encoding="utf-8")
            written.append(dest)

    return written


def patch_player_kml_for_hosted_role(
    player_kml_path: Path,
    *,
    base_url: str,
    player_cell: str,
    use_views: bool = True,
) -> int:
    """Replace /campaign/ NetworkLink hrefs with /view/{player_cell}/ when hosted views enabled."""
    if not player_kml_path.exists():
        return 0
    base = base_url.rstrip("/")
    root = ET.parse(player_kml_path).getroot()
    changed = 0
    for link in root.iter(_kml("NetworkLink")):
        link_elem = link.find(_kml("Link"))
        if link_elem is None:
            continue
        href_el = link_elem.find(_kml("href"))
        if href_el is None or not (href_el.text or "").strip():
            continue
        href = href_el.text.strip()
        prefix = f"{base}/campaign/"
        if not href.startswith(prefix):
            continue
        theater_id = href[len(prefix) :].replace(".kml", "")
        if use_views and player_cell in VIEWER_ROLES:
            href_el.text = hosted_view_href(base, player_cell, theater_id)
        else:
            href_el.text = hosted_master_href(base, theater_id)
        changed += 1

    if changed:
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(player_kml_path, encoding="utf-8", xml_declaration=True)
    return changed
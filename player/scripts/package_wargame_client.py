#!/usr/bin/env python3
"""
Package campaign turn state for Discord / Gmail pass-and-play.

The full globe (imagery + doc.kml) stays installed locally. Each turn exports
only campaign/*.kml markers into a small KMZ for upload to Discord.

Usage:
    python3 scripts/package_wargame_client.py --instructions
    python3 scripts/package_wargame_client.py --turn 12 --player Blue
    python3 scripts/package_wargame_client.py --turn 12 --list
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_world_globe import resolve_campaign_region_ids
from campaign_tier_lod import prepare_campaign_kml_xml
from campaign_visibility import (
    GAME_FORMATS,
    VIEWER_ROLES,
    load_campaign_meta,
    prepare_view_kml_xml,
)
from globe_placement import layer_by_id, load_globe_config
from build_kml_superoverlay import merge_variant_config

KML_NS = "http://www.opengis.net/kml/2.2"


def campaign_dir_for_variant(project_root: Path, variant: str) -> Path:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, variant)
    rel = config.get(
        "campaign_kml",
        "03-kml/wowcommanderalpha/campaign/doc.kml",
    )
    return project_root / Path(rel).parent


def list_campaign_files(
    project_root: Path,
    variant: str,
) -> list[Path]:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, variant)
    variant_cfg = (base.get("world_variants", {}) or {}).get(variant, {})
    campaign_dir = campaign_dir_for_variant(project_root, variant)
    files: list[Path] = []
    for region_id in resolve_campaign_region_ids(config, variant_cfg):
        path = campaign_dir / f"{region_id}.kml"
        if path.exists():
            files.append(path)
    return files


def count_placemarks(kml_path: Path) -> int:
    root = ET.parse(kml_path).getroot()
    return len(root.findall(f".//{{{KML_NS}}}Placemark"))


def build_turn_doc_kml(
    *,
    turn: int,
    player: str,
    campaign_entries: list[tuple[str, str]],
) -> str:
    """Wrapper doc.kml with NetworkLinks to campaign/*.kml inside the KMZ."""
    kml = ET.Element(f"{{{KML_NS}}}kml")
    document = ET.SubElement(kml, f"{{{KML_NS}}}Document")
    title = f"WOW Commander — Turn {turn}"
    if player:
        title = f"{title} ({player})"
    ET.SubElement(document, f"{{{KML_NS}}}name").text = title
    ET.SubElement(document, f"{{{KML_NS}}}description").text = (
        "Pass-and-play turn package. Open this file in Google Earth Pro on top of your "
        "local WOW Commander Alpha globe. Markers load from embedded campaign/*.kml files."
    )
    ET.SubElement(document, f"{{{KML_NS}}}open").text = "1"

    for label, archive_href in campaign_entries:
        link = ET.SubElement(document, f"{{{KML_NS}}}NetworkLink")
        ET.SubElement(link, f"{{{KML_NS}}}name").text = label
        ET.SubElement(link, f"{{{KML_NS}}}open").text = "1"
        link_elem = ET.SubElement(link, f"{{{KML_NS}}}Link")
        ET.SubElement(link_elem, f"{{{KML_NS}}}href").text = archive_href

    tree = ET.ElementTree(kml)
    ET.indent(tree, space="  ")
    return ET.tostring(kml, encoding="unicode")


def resolve_export_defaults(
    project_root: Path,
    *,
    variant: str,
    role: str | None = None,
    game_format: str | None = None,
    player: str = "",
    use_session: bool = True,
) -> tuple[str | None, str | None, str, str | None]:
    """
    Merge CLI args with game_session.json and campaign_meta.json.

    Returns (role, game_format, player_name, session_note).
    """
    session = None
    if use_session:
        from campaign_session import load_session

        session = load_session(project_root, variant=variant)
    campaign_dir = campaign_dir_for_variant(project_root, variant)
    meta = load_campaign_meta(campaign_dir)

    resolved_role = role
    resolved_format = game_format
    resolved_player = player.strip()
    notes: list[str] = []

    if session:
        if resolved_role is None and session.get("player_cell") in VIEWER_ROLES:
            resolved_role = session["player_cell"]
            notes.append(f"role from session ({resolved_role})")
        if resolved_format is None and session.get("game_format") in GAME_FORMATS:
            resolved_format = session["game_format"]
            notes.append(f"format from session ({resolved_format})")
        if not resolved_player and session.get("commander_name"):
            resolved_player = str(session["commander_name"]).strip()
            notes.append("player name from session commander")

    if resolved_format is None:
        meta_fmt = meta.get("game_format")
        if meta_fmt in GAME_FORMATS:
            resolved_format = meta_fmt
            notes.append(f"format from campaign_meta ({resolved_format})")

    if resolved_role and not any("role" in n for n in notes):
        notes.append(f"role from CLI ({resolved_role})")
    if game_format and game_format in GAME_FORMATS and not any("format from session" in n for n in notes):
        notes.append(f"format from CLI ({game_format})")

    note = "; ".join(notes) if notes else None
    return resolved_role, resolved_format, resolved_player, note


def default_turn_filename(turn: int, player: str) -> str:
    today = date.today().isoformat()
    slug = player.strip().replace(" ", "_") if player else "table"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in slug)
    return f"wowcommander_turn{turn:02d}_{today}_{safe}.kmz"


def maybe_push_campaign_live(project_root: Path, *, variant: str) -> tuple[int, str]:
    """If using campaign_live.kml/.kmz, copy edits into campaign/*.kml before export."""
    base = load_globe_config(project_root)
    variant_cfg = (base.get("world_variants", {}) or {}).get(variant, {})
    if str(variant_cfg.get("campaign_places_mode", "")) != "live_edit":
        return 0, ""
    from campaign_live_io import resolve_campaign_live_path

    live_dir = project_root / Path(variant_cfg.get("output", "03-kml/wowcommanderalpha/doc.kml")).parent
    live_path = resolve_campaign_live_path(live_dir)
    if live_path is None:
        return 0, ""
    from sync_campaign_live import push_live_to_theaters

    return push_live_to_theaters(project_root, variant=variant), live_path.name


def package_turn_kmz(
    project_root: Path,
    *,
    variant: str,
    turn: int,
    player: str,
    output: Path,
    include_empty: bool = False,
    role: str | None = None,
    game_format: str | None = None,
    reveal_radius_km: float | None = None,
    skip_live_push: bool = False,
) -> dict:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, variant)
    variant_cfg = (base.get("world_variants", {}) or {}).get(variant, {})
    campaign_dir = campaign_dir_for_variant(project_root, variant)
    meta = load_campaign_meta(campaign_dir)
    fmt = game_format or meta.get("game_format", "no-blind")

    pushed = 0
    if not skip_live_push:
        pushed, live_name = maybe_push_campaign_live(project_root, variant=variant)
        if pushed:
            print(f"Synced {live_name} → {pushed} theater file(s)")

    entries: list[tuple[str, str]] = []
    packed_files: list[Path] = []
    placemark_total = 0

    for region_id in resolve_campaign_region_ids(config, variant_cfg):
        path = campaign_dir / f"{region_id}.kml"
        if not path.exists():
            continue
        marks = count_placemarks(path)
        if marks == 0 and not include_empty:
            continue
        layer = layer_by_id(config, region_id)
        label = layer.get("label", region_id) if layer else region_id
        archive_href = f"campaign/{region_id}.kml"
        entries.append((f"{label} (campaign)", archive_href))
        packed_files.append(path)
        placemark_total += marks

    if not packed_files:
        raise SystemExit(
            "No campaign files to pack. Add placemarks in campaign_live.kml "
            "(Campaign Live → theater → Campaign Package → faction → tier), "
            "File → Save in Google Earth, then export again — sync runs automatically. "
            "Or pass --include-empty."
        )

    doc_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    doc_xml += build_turn_doc_kml(turn=turn, player=player, campaign_entries=entries)

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", doc_xml)
        for path in packed_files:
            if role:
                kml_xml = prepare_view_kml_xml(
                    path,
                    campaign_dir=campaign_dir,
                    turn=turn,
                    viewer=role,
                    game_format=fmt,
                    radius_km=reveal_radius_km,
                    persistent=None,
                )
            else:
                kml_xml = prepare_campaign_kml_xml(path)
            archive.writestr(f"campaign/{path.name}", kml_xml)

    size_kb = output.stat().st_size / 1024
    return {
        "output": str(output),
        "turn": turn,
        "player": player,
        "regions": len(packed_files),
        "placemarks": placemark_total,
        "size_kb": round(size_kb, 1),
        "role": role,
        "game_format": fmt if role else "no-blind",
    }


def print_instructions() -> None:
    print(
        """
WOW Commander Alpha — pass-the-table (Discord primary, Gmail fallback)

ONE-TIME SETUP (each player)
  1. Install the full globe locally and open:
       03-kml/wowcommanderalpha/doc.kml
     in Google Earth Pro. Leave it in Places — this is the board.

EACH TURN (active player)
  1. Place markers in campaign_live.kml (editable — NetworkLinks are read-only):
       python3 scripts/open_theater_campaign.py kalimdor
     Places → Campaign Live (EDIT HERE) → Campaign Package (live) → Kalimdor
       → Campaign Package → red-cell or blue-cell → tier → Add → Placemark
     File → Save in Google Earth. Turn export syncs automatically (no Terminal).
     To refresh Campaign Board mid-game without exporting: double-click
       scripts/Sync Campaign Board.command
     (or run python3 scripts/sync_campaign_live.py --push), then Refresh the link.
     (Strategic / Operational / Tactical). White-cell uses redcell-discovered /
     bluecell-discovered for manual reveal. Add → Placemark in the target folder.
     Optional while editing: python3 scripts/sync_campaign_tier_lod.py
     Template to copy: 03-kml/wowcommanderalpha/campaign/Campaign Package/
  2. Export the turn package:
       python3 scripts/package_wargame_client.py --turn 12 --player YourName
  3. Upload the .kmz to your Discord game channel (or DM).

NEXT PLAYER
  1. Download the .kmz from Discord.
  2. Double-click it (or File → Open in Google Earth Pro).
  3. Uncheck older "WOW Commander — Turn …" entries in Places if clutter builds.
  4. Play your turn, export the next turn number, upload back to Discord.

GMAIL FALLBACK
  Same .kmz as an email attachment if Discord is unavailable.

HOSTED MODE (optional, no Discord file each turn)
  Set campaign_deploy_mode: hosted and campaign_base_url in config/globe.json.
  Rebuild doc.kml. GM uploads updated campaign/*.kml to the HTTPS host after each turn;
  other players refresh NetworkLinks in GEP (or wait for onInterval).

WHY CAMPAIGN LINKS ARE REFRESHABLE
  Each theater (Kalimdor, etc.) is a NetworkLink to a file on disk — not inline markers.
  Refresh reloads that file after you save edits. The Campaign Board groups these links;
  they load only when you zoom near that theater (lazy load — keeps GEP fast).

PASSWORD / ANTI-TAMPER
  Google Earth cannot password-protect folders. Anyone with the master campaign/*.kml
  on disk can open it in a text editor. Use honor rules at the table, or export
  filtered turn KMZs (--role below) so opponents never receive hidden unit data.

BLIND PLAY (export-time filtering — not live in GEP)
  Set format once in campaign/campaign_meta.json (templates in Campaign Package/):
    no-blind       — everyone sees all factions (default)
    single-blind   — red-cell sees all; blue-cell sees only blue + reveals
    double-blind   — each side sees own faction + reveals only

  Export per player:
    python3 scripts/package_wargame_client.py --turn 12 --player Red --role red-cell
    python3 scripts/package_wargame_client.py --turn 12 --player Blue --role blue-cell
    python3 scripts/package_wargame_client.py --turn 12 --role white-cell

  Without --role, export includes everything (table honor system).

PROXIMITY REVEAL (1 km default)
  When using --role, moved or newly placed markers trigger reveal of enemy units
  within reveal_radius_km (default 1.0 in campaign_meta.json). Reveals persist
  turn-to-turn. Referee manual reveal: white-cell → redcell-discovered or
  bluecell-discovered (copied into that player's view on export).

WHITE CELL
  Passive referee — only steps in when asked. Full truth export: --role white-cell.
  Manual reveal folders override blind filtering for the matching side.

MARKER TIPS (keeps turn files small)
  - Point icons only at Strategic/Operational; shared icon href, not embedded images.
  - LabelStyle scale 0 at Strategic.
  - Paths/polygons only in Tactical.
"""
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export campaign turn KMZ for Discord / Gmail pass-and-play"
    )
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument("--turn", type=int, help="Turn number for filename and document title")
    parser.add_argument("--player", default="", help="Player name for filename (optional)")
    parser.add_argument(
        "--output",
        type=Path,
        help="Output .kmz path (default: exports/wowcommander_turnNN_date_player.kmz)",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Include regional campaign files even with zero placemarks",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List campaign files and placemark counts without packaging",
    )
    parser.add_argument(
        "--instructions",
        action="store_true",
        help="Print player workflow for Discord / Gmail turns",
    )
    parser.add_argument(
        "--role",
        choices=sorted(VIEWER_ROLES),
        help="Filter export for red-cell, blue-cell, or white-cell (blind play)",
    )
    parser.add_argument(
        "--format",
        choices=sorted(GAME_FORMATS),
        help="Blind format override (default from campaign/campaign_meta.json)",
    )
    parser.add_argument(
        "--reveal-radius-km",
        type=float,
        help="Proximity reveal radius in km (default from campaign_meta.json)",
    )
    parser.add_argument(
        "--no-session",
        action="store_true",
        help="Ignore game_session.json (export all cells — honor system)",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    if args.instructions:
        print_instructions()
        return

    if args.list:
        files = list_campaign_files(project_root, args.variant)
        if not files:
            print("No campaign/*.kml files found.")
            return
        total = 0
        for path in files:
            n = count_placemarks(path)
            total += n
            print(f"  {path.name}: {n} placemarks")
        print(f"Total: {total} placemarks in {len(files)} files")
        return

    if args.turn is None:
        parser.error("--turn is required unless using --instructions or --list")

    role, game_format, player, session_note = resolve_export_defaults(
        project_root,
        variant=args.variant,
        role=args.role,
        game_format=args.format,
        player=args.player,
        use_session=not args.no_session,
    )
    if session_note:
        print(f"Export settings: {session_note}")
    elif not args.no_session:
        print("Export settings: no game_session.json — exporting all cells (honor system)")
        print("  Tip: run Setup Campaign.command or pass --role red-cell|blue-cell")

    output = args.output
    if output is None:
        output = (
            project_root
            / "exports"
            / default_turn_filename(args.turn, player)
        )

    if output.suffix.lower() != ".kmz":
        output = output.with_suffix(".kmz")

    summary = package_turn_kmz(
        project_root,
        variant=args.variant,
        turn=args.turn,
        player=player,
        output=output,
        include_empty=args.include_empty,
        role=role,
        game_format=game_format,
        reveal_radius_km=args.reveal_radius_km,
    )
    print(f"Turn package: {summary['output']}")
    print(
        f"  turn {summary['turn']}, {summary['placemarks']} placemarks "
        f"in {summary['regions']} theaters, {summary['size_kb']} KB"
    )
    if summary.get("role"):
        print(f"  view: {summary['role']} ({summary['game_format']})")
    else:
        print("  view: all cells (no --role filter)")
    print("Upload to Discord (or Gmail). Next player: download → open in Google Earth Pro.")


if __name__ == "__main__":
    main()
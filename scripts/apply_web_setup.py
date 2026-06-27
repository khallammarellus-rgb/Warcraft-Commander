#!/usr/bin/env python3
"""
Apply a web Executive Officer session to local campaign files.

  python3 scripts/apply_web_setup.py --file game_session.json
  python3 scripts/apply_web_setup.py --game table-01 --cell blue-cell
  python3 scripts/apply_web_setup.py --game table-01 --cell blue-cell --portal https://wow-commander-campaign.pages.dev
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_deploy import apply_hosted_post_setup, apply_session_deploy
from campaign_dossier import open_commander_dossier, write_commander_dossier
from campaign_hq import hq_name, theater_center
from campaign_session import finalize_session
from campaign_tactician_opord import append_gameplay_blocks, assemble_tactician_opord
from campaign_visibility import meta_path
from faction_library import executive_officer, faction_by_id
from package_wargame_client import campaign_dir_for_variant

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _fetch_latest_session(portal: str, game_id: str, cell: str, organizer_token: str) -> dict:
    base = portal.rstrip("/")
    url = f"{base}/api/executive-officer/latest?game_id={game_id}&cell={cell}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {organizer_token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Portal error {exc.code}: {body}") from exc
    session = payload.get("session")
    if not session:
        raise SystemExit("Portal response missing session")
    return session


def _enrich_session(project_root: Path, session: dict) -> dict:
    factions = session.get("factions") or []
    if not factions:
        raise ValueError("Session missing factions")
    primary = factions[0]
    theater = session["theater"]
    force_size = session.get("force_size", "battalion")
    force_name = session.get("force_name", "Task Force")
    coords = theater_center(project_root, theater)

    knowledge = session.get("knowledge_level", "casual")
    opord_mode = session.get("opord_mode")
    opord_sections = session.get("opord_sections")
    opord_text = session.get("operation_order")
    warn_o = session.get("warn_o")

    if knowledge == "tactician":
        opord_mode = None
        if opord_sections:
            answers = {k: v for k, v in opord_sections.items() if v}
            opord_text = assemble_tactician_opord(answers) or None
    elif opord_mode == "skip":
        warn_o = None
        opord_text = None
    elif opord_text:
        opord_text = append_gameplay_blocks(str(opord_text))

    if warn_o is not None and not str(warn_o).strip():
        warn_o = None
    if opord_text is not None and not str(opord_text).strip():
        opord_text = None

    entry = faction_by_id(project_root, primary)
    eo = session.get("executive_officer") or executive_officer(project_root, primary)

    out = dict(session)
    out.update(
        {
            "primary_faction": primary,
            "executive_officer": eo,
            "hq_name": hq_name(force_size, force_name=force_name),
            "hq_coords": [coords[0], coords[1]],
            "knowledge_level": knowledge,
            "opord_mode": opord_mode,
            "warn_o": warn_o,
            "operation_order": opord_text,
            "opord_sections": opord_sections if knowledge == "tactician" else None,
            "tutorial_completed": bool(session.get("tutorial_completed")),
        }
    )
    return out


def _write_campaign_meta(project_root: Path, game_format: str, *, variant: str = "wowcommanderalpha") -> None:
    path = meta_path(campaign_dir_for_variant(project_root, variant))
    data = {"game_format": game_format, "reveal_radius_km": 1.0, "reveal_persistent": True}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply web Executive Officer session locally")
    parser.add_argument("--file", type=Path, help="game_session.json from wizard download")
    parser.add_argument("--game", help="Portal game id (table-01)")
    parser.add_argument("--cell", choices=["red-cell", "blue-cell"], help="Player cell")
    parser.add_argument("--portal", default="https://wow-commander-campaign.pages.dev", help="Portal base URL")
    parser.add_argument("--organizer-token", help="ORGANIZER_SECRET for portal API (or WOWC_ORGANIZER_TOKEN env)")
    parser.add_argument("--variant", default="wowcommanderalpha")
    args = parser.parse_args()

    if args.file:
        session = json.loads(args.file.read_text(encoding="utf-8"))
    elif args.game and args.cell:
        import os

        token = args.organizer_token or os.environ.get("WOWC_ORGANIZER_TOKEN")
        if not token:
            raise SystemExit("Provide --organizer-token or set WOWC_ORGANIZER_TOKEN")
        session = _fetch_latest_session(args.portal, args.game, args.cell, token)
    else:
        raise SystemExit("Use --file or --game with --cell")

    try:
        session = _enrich_session(PROJECT_ROOT, session)
    except (ValueError, KeyError) as exc:
        print(f"Invalid session: {exc}", file=sys.stderr)
        return 1

    _write_campaign_meta(PROJECT_ROOT, session["game_format"], variant=args.variant)
    finalize_session(PROJECT_ROOT, session, variant=args.variant)

    try:
        deploy_result = apply_session_deploy(PROJECT_ROOT, session, rebuild=True)
        if deploy_result.get("rebuild_exit_code", 0) != 0:
            print("Warning: doc.kml rebuild had errors", file=sys.stderr)
        if session.get("campaign_deploy_mode") == "hosted":
            post = apply_hosted_post_setup(PROJECT_ROOT, rebuild_views=True)
            if post.get("views_built"):
                print(f"Hosted views built ({post['views_built']} files)")
    except ValueError as exc:
        print(f"Deploy config not applied: {exc}", file=sys.stderr)

    dossier_path = write_commander_dossier(PROJECT_ROOT, session)
    opened = open_commander_dossier(dossier_path)
    print("Campaign setup applied.")
    print(f"  Commander: {session.get('commander_name')}")
    print(f"  Theater:   {session.get('theater')}")
    print(f"  Cell:      {session.get('player_cell')}")
    print(f"  EO:        {session.get('executive_officer')}")
    print(f"  Dossier:   {dossier_path}" + (" (opened)" if opened else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
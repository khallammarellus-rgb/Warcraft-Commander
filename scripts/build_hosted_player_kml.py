#!/usr/bin/env python3
"""Patch doc_player.kml Campaign Board links for hosted role-filtered views."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_kml_superoverlay import merge_variant_config
from campaign_deploy import read_deploy_settings
from campaign_hosted_views import patch_player_kml_for_hosted_role
from campaign_session import load_session
from globe_placement import load_globe_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch player KML for hosted role views")
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument("--cell", choices=["red-cell", "blue-cell", "white-cell"], default=None)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    deploy = read_deploy_settings(project_root, variant=args.variant)
    if deploy.get("campaign_deploy_mode") != "hosted":
        print("Not in hosted mode — no changes.")
        return 0

    base_url = deploy.get("campaign_base_url", "")
    if not base_url:
        print("campaign_base_url is empty.")
        return 1

    session = load_session(project_root, variant=args.variant)
    cell = args.cell or (session.get("player_cell") if session else None)
    if not cell:
        print("No player cell — pass --cell or run campaign setup.")
        return 1

    base = load_globe_config(project_root)
    variant_cfg = (base.get("world_variants", {}) or {}).get(args.variant, {})
    player_rel = variant_cfg.get(
        "player_entry",
        variant_cfg.get("output", "03-kml/wowcommanderalpha/doc_player.kml"),
    )
    player_path = project_root / player_rel
    use_views = bool(variant_cfg.get("campaign_hosted_views", True))

    n = patch_player_kml_for_hosted_role(
        player_path,
        base_url=base_url,
        player_cell=cell,
        use_views=use_views,
    )
    print(f"Patched {n} NetworkLink(s) in {player_path} → view/{cell}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
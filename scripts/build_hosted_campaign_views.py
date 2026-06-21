#!/usr/bin/env python3
"""
Build role-filtered campaign views for Cloudflare Pages hosting.

Writes:
  <out>/campaign/<theater>.kml     — master (organizer / white-cell reference)
  <out>/view/red-cell/<theater>.kml
  <out>/view/blue-cell/<theater>.kml
  <out>/view/white-cell/<theater>.kml

  python3 scripts/build_hosted_campaign_views.py
  python3 scripts/build_hosted_campaign_views.py --out portal/dist
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_deploy import read_deploy_settings
from campaign_hosted_views import write_hosted_views
from campaign_session import load_session


def main() -> int:
    parser = argparse.ArgumentParser(description="Build hosted role-filtered campaign KML views")
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: portal/dist)",
    )
    parser.add_argument("--theater", action="append", help="Limit to theater id(s)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_dir = args.out or (project_root / "portal" / "dist")
    out_dir.mkdir(parents=True, exist_ok=True)

    session = load_session(project_root, variant=args.variant)
    game_format = session.get("game_format") if session else None

    written = write_hosted_views(
        project_root,
        out_dir,
        variant=args.variant,
        game_format=game_format,
        theaters=args.theater,
    )

    deploy = read_deploy_settings(project_root, variant=args.variant)
    base = deploy.get("campaign_base_url", "")
    print(f"Wrote {len(written)} files under {out_dir}")
    if base:
        print(f"Red player example:   {base.rstrip('/')}/view/red-cell/kalimdor.kml")
        print(f"Blue player example:  {base.rstrip('/')}/view/blue-cell/kalimdor.kml")
    else:
        print("Set campaign_base_url (hosted mode) for live NetworkLink URLs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
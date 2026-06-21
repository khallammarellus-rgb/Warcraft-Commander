#!/usr/bin/env python3
"""
Configure local vs hosted campaign deploy mode in config/globe.json.

  python3 scripts/configure_hosted_campaign.py --mode local
  python3 scripts/configure_hosted_campaign.py --mode hosted --url https://example.com/wowcommander
  python3 scripts/configure_hosted_campaign.py --mode hosted --url https://example.com/wowcommander --rebuild
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_deploy import (
    DEFAULT_VARIANT,
    apply_hosted_post_setup,
    apply_session_deploy,
    read_deploy_settings,
    write_deploy_settings,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure campaign deploy mode (local or hosted)")
    parser.add_argument(
        "--mode",
        choices=["local", "hosted"],
        help="local = relative campaign paths; hosted = HTTPS NetworkLinks",
    )
    parser.add_argument(
        "--url",
        default="",
        help="HTTPS base URL for hosted mode (no trailing slash)",
    )
    parser.add_argument("--variant", default=DEFAULT_VARIANT)
    parser.add_argument("--rebuild", action="store_true", help="Rebuild doc.kml after writing config")
    parser.add_argument("--show", action="store_true", help="Print current deploy settings and exit")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent

    if args.show:
        current = read_deploy_settings(project_root, variant=args.variant)
        print(f"variant:               {args.variant}")
        print(f"campaign_deploy_mode:  {current['campaign_deploy_mode']}")
        print(f"campaign_base_url:     {current['campaign_base_url'] or '(empty)'}")
        print(f"campaign_refresh_mode: {current['campaign_refresh_mode']}")
        print(f"campaign_hosted_views: {current.get('campaign_hosted_views', False)}")
        return 0

    if not args.mode:
        parser.error("Provide --mode local|hosted or use --show")

    if args.rebuild:
        result = apply_session_deploy(
            project_root,
            {
                "campaign_deploy_mode": args.mode,
                "campaign_base_url": args.url,
            },
            variant=args.variant,
            rebuild=True,
        )
    else:
        result = write_deploy_settings(
            project_root,
            variant=args.variant,
            deploy_mode=args.mode,
            base_url=args.url,
        )

    print(f"campaign_deploy_mode:  {result['campaign_deploy_mode']}")
    print(f"campaign_base_url:     {result.get('campaign_base_url', '') or '(empty)'}")
    print(f"campaign_refresh_mode: {result['campaign_refresh_mode']}")
    if result.get("campaign_hosted_views"):
        print("campaign_hosted_views: true (players use /view/{cell}/ URLs)")
    if args.rebuild:
        code = result.get("rebuild_exit_code", 0)
        if code == 0:
            print("doc.kml rebuilt.")
        else:
            print(f"doc.kml rebuild failed (exit {code}).", file=sys.stderr)
            return code
    if args.mode == "hosted":
        post = apply_hosted_post_setup(project_root, variant=args.variant, rebuild_views=True)
        if post.get("patched"):
            print(f"doc_player.kml patched → view/{post.get('player_cell')}/ ({post['patched']} link(s))")
        if post.get("views_built"):
            print(f"portal/dist built ({post['views_built']} KML files) — deploy: python3 scripts/publish_portal_site.py --deploy")
        elif not args.rebuild:
            print("Run with --rebuild to refresh doc.kml NetworkLink hrefs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""
Configure merge automation secrets for Cloudflare Pages and print GitHub setup steps.

  python3 scripts/configure_merge_automation.py
  python3 scripts/configure_merge_automation.py --pages-only
  python3 scripts/configure_merge_automation.py --github-dispatch-token ghp_...
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

GITHUB_REPO = "khallammarellus-rgb/Warcraft-Commander"
PORTAL_ORIGIN = "https://wow-commander-campaign.pages.dev"
PAGES_PROJECT = "wow-commander-campaign"
CF_ACCOUNT_ID = "855414bc6c2032e637d52e2c6ce8076e"


def _load_deploy_secrets(project_root: Path) -> dict[str, str]:
    path = project_root / "portal" / ".deploy-secrets.env"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _put_pages_secret(portal_dir: Path, name: str, value: str) -> bool:
    wrangler = portal_dir / "node_modules" / ".bin" / "wrangler"
    if not wrangler.exists():
        print("Install wrangler first: cd portal && npm install", file=sys.stderr)
        return False
    proc = subprocess.run(
        [
            str(wrangler),
            "pages",
            "secret",
            "put",
            name,
            "--project-name",
            PAGES_PROJECT,
        ],
        cwd=portal_dir,
        input=value.encode("utf-8"),
        capture_output=True,
        text=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace")
        print(f"Failed to set {name}: {err}", file=sys.stderr)
        return False
    print(f"Set Pages secret {name}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure merge automation")
    parser.add_argument("--pages-only", action="store_true", help="Only update Cloudflare Pages secrets")
    parser.add_argument("--github-dispatch-token", default=os.environ.get("GITHUB_MERGE_DISPATCH_TOKEN"))
    parser.add_argument("--portal-origin", default=PORTAL_ORIGIN)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    portal_dir = project_root / "portal"
    secrets = _load_deploy_secrets(project_root)
    organizer = secrets.get("ORGANIZER_SECRET", "")

    ok = _put_pages_secret(portal_dir, "GITHUB_REPO", GITHUB_REPO)
    if args.github_dispatch_token:
        ok = _put_pages_secret(portal_dir, "GITHUB_MERGE_DISPATCH_TOKEN", args.github_dispatch_token) and ok

    print()
    print("=== GitHub Actions (primary) ===")
    print(f"Repository: {GITHUB_REPO}")
    print("Add these repository secrets at:")
    print(f"  https://github.com/{GITHUB_REPO}/settings/secrets/actions")
    print()
    print("  PORTAL_ORGANIZER_SECRET  = (same as ORGANIZER_SECRET on Pages)")
    print(f"  CLOUDFLARE_ACCOUNT_ID    = {CF_ACCOUNT_ID}")
    print("  CLOUDFLARE_API_TOKEN     = Cloudflare API token with Pages + R2 read")
    if organizer:
        print()
        print("  PORTAL_ORGANIZER_SECRET value is in portal/.deploy-secrets.env")
    print()
    print("Optional repository variable:")
    print(f"  PORTAL_ORIGIN = {args.portal_origin}")
    print()
    print("Workflows:")
    print("  .github/workflows/merge-portal-poll.yml   — polls every 3 min (primary)")
    print("  .github/workflows/merge-portal-turn.yml   — instant dispatch (optional)")
    print()

    if not args.pages_only:
        print("=== Local daemon (backup) ===")
        print("  export ORGANIZER_SECRET=...")
        print("  python3 scripts/merge_runner_daemon.py")
        print()

    if args.github_dispatch_token:
        print("Instant dispatch: GITHUB_MERGE_DISPATCH_TOKEN set on Pages.")
    else:
        print("Instant dispatch: create a GitHub PAT (repo scope) and run:")
        print("  python3 scripts/configure_merge_automation.py --github-dispatch-token ghp_...")
        print("Poll workflow works without the PAT.")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
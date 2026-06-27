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


def _sync_github_secrets(project_root: Path, gh_token: str) -> bool:
    script = project_root / "scripts" / "set_github_secret.py"
    pairs = [
        ("PORTAL_ORGANIZER_SECRET", "ORGANIZER_SECRET"),
        ("CLOUDFLARE_API_TOKEN", "MERGE_CLOUDFLARE_API_TOKEN"),
        ("CLOUDFLARE_ACCOUNT_ID", "MERGE_CLOUDFLARE_ACCOUNT_ID"),
    ]
    ok = True
    env = {**os.environ, "GITHUB_ADMIN_TOKEN": gh_token}
    for gh_name, local_key in pairs:
        proc = subprocess.run(
            [sys.executable, str(script), gh_name, "--from-env", local_key, "--github-token", gh_token],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            print(proc.stderr or proc.stdout, file=sys.stderr)
            ok = False
        else:
            print(proc.stdout.strip())
    if ok and not _load_deploy_secrets(project_root).get("MERGE_CLOUDFLARE_ACCOUNT_ID"):
        proc = subprocess.run(
            [sys.executable, str(script), "CLOUDFLARE_ACCOUNT_ID", "--value", CF_ACCOUNT_ID, "--github-token", gh_token],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        if proc.stdout.strip():
            print(proc.stdout.strip())
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure merge automation")
    parser.add_argument("--pages-only", action="store_true", help="Only update Cloudflare Pages secrets")
    parser.add_argument("--github-dispatch-token", default=os.environ.get("GITHUB_MERGE_DISPATCH_TOKEN"))
    parser.add_argument("--github-admin-token", default=os.environ.get("GITHUB_ADMIN_TOKEN"))
    parser.add_argument("--sync-github-secrets", action="store_true", help="Push Actions secrets from portal/.deploy-secrets.env")
    parser.add_argument("--install-daemon", action="store_true", help="Install macOS LaunchAgent for local merge daemon (Option B)")
    parser.add_argument("--portal-origin", default=PORTAL_ORIGIN)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    portal_dir = project_root / "portal"
    secrets = _load_deploy_secrets(project_root)
    organizer = secrets.get("ORGANIZER_SECRET", "")

    ok = _put_pages_secret(portal_dir, "GITHUB_REPO", GITHUB_REPO)
    if args.github_dispatch_token:
        ok = _put_pages_secret(portal_dir, "GITHUB_MERGE_DISPATCH_TOKEN", args.github_dispatch_token) and ok

    if args.sync_github_secrets:
        gh_token = (args.github_admin_token or "").strip()
        if not gh_token:
            print("Pass --github-admin-token or set GITHUB_ADMIN_TOKEN to sync GitHub secrets", file=sys.stderr)
            ok = False
        else:
            ok = _sync_github_secrets(project_root, gh_token) and ok

    if args.install_daemon:
        installer = project_root / "scripts" / "install_merge_daemon.sh"
        proc = subprocess.run(["/bin/bash", str(installer)], cwd=project_root, check=False)
        ok = proc.returncode == 0 and ok

    print()
    print("=== GitHub Actions (primary) ===")
    print(f"Repository: {GITHUB_REPO}")
    print("Add these repository secrets at:")
    print(f"  https://github.com/{GITHUB_REPO}/settings/secrets/actions")
    print()
    print("  PORTAL_ORGANIZER_SECRET  = (same as ORGANIZER_SECRET on Pages; ORGANIZER_SECRET also accepted)")
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
        print("  ./scripts/run_merge_daemon.sh")
        print("  ./scripts/install_merge_daemon.sh   # macOS LaunchAgent (login + keep-alive)")
        print("  open 'scripts/Start Merge Daemon.command'")
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
#!/usr/bin/env python3
"""Store merge-runner Cloudflare credentials on Pages (and local deploy secrets)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PAGES_PROJECT = "wow-commander-campaign"
DEFAULT_ACCOUNT_ID = "855414bc6c2032e637d52e2c6ce8076e"


def _put_pages_secret(portal_dir: Path, name: str, value: str) -> bool:
    wrangler = portal_dir / "node_modules" / ".bin" / "wrangler"
    if not wrangler.exists():
        print("Install wrangler: cd portal && npm install", file=sys.stderr)
        return False
    proc = subprocess.run(
        [str(wrangler), "pages", "secret", "put", name, "--project-name", PAGES_PROJECT],
        cwd=portal_dir,
        input=value.encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or b"").decode("utf-8", errors="replace")
        print(f"Failed to set {name}: {err}", file=sys.stderr)
        return False
    print(f"Set Pages secret {name}")
    return True


def _append_local_secrets(project_root: Path, token: str, account_id: str) -> None:
    path = project_root / "portal" / ".deploy-secrets.env"
    lines: list[str] = []
    if path.is_file():
        lines = path.read_text(encoding="utf-8").splitlines()
    keys = {line.split("=", 1)[0] for line in lines if "=" in line}
    if "MERGE_CLOUDFLARE_API_TOKEN" not in keys:
        lines.append(f"MERGE_CLOUDFLARE_API_TOKEN={token}")
    if "MERGE_CLOUDFLARE_ACCOUNT_ID" not in keys:
        lines.append(f"MERGE_CLOUDFLARE_ACCOUNT_ID={account_id}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Updated {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Store merge-runner Cloudflare credentials")
    parser.add_argument("--api-token", required=True, help="Cloudflare API token value")
    parser.add_argument("--account-id", default=DEFAULT_ACCOUNT_ID)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    portal_dir = project_root / "portal"
    ok = _put_pages_secret(portal_dir, "MERGE_CLOUDFLARE_API_TOKEN", args.api_token)
    ok = _put_pages_secret(portal_dir, "MERGE_CLOUDFLARE_ACCOUNT_ID", args.account_id) and ok
    _append_local_secrets(project_root, args.api_token, args.account_id)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
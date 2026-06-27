#!/usr/bin/env python3
"""
Set a GitHub Actions repository secret (requires admin PAT).

  export GITHUB_ADMIN_TOKEN=ghp_...
  python3 scripts/set_github_secret.py CLOUDFLARE_API_TOKEN --from-env MERGE_CLOUDFLARE_API_TOKEN
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = "khallammarellus-rgb/Warcraft-Commander"


def _load_local_env(project_root: Path) -> dict[str, str]:
    path = project_root / "portal" / ".deploy-secrets.env"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    try:
        from nacl import encoding, public
    except ImportError:
        print("Install PyNaCl: python3 -m pip install pynacl", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(description="Set GitHub Actions repository secret")
    parser.add_argument("name", help="GitHub secret name")
    parser.add_argument("--value", default=None, help="Secret value")
    parser.add_argument("--from-env", default=None, help="Read value from portal/.deploy-secrets.env key")
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_ADMIN_TOKEN"))
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args()

    gh_token = (args.github_token or "").strip()
    if not gh_token:
        print("Set GITHUB_ADMIN_TOKEN (PAT with repo admin / secrets write)", file=sys.stderr)
        return 1

    value = args.value
    if args.from_env:
        value = _load_local_env(Path(__file__).resolve().parent.parent).get(args.from_env)
    if not value:
        print("Missing secret value", file=sys.stderr)
        return 1

    owner, repo = args.repo.split("/", 1)
    headers = {
        "Authorization": f"Bearer {gh_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    key_url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/public-key"
    proc = subprocess.run(
        ["curl", "-fsS", "-H", f"Authorization: Bearer {gh_token}", "-H", "Accept: application/vnd.github+json",
         "-H", "X-GitHub-Api-Version: 2022-11-28", key_url],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return 1
    key_data = json.loads(proc.stdout)

    public_key = public.PublicKey(key_data["key"].encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(value.encode("utf-8"))
    payload = {
        "encrypted_value": base64.b64encode(encrypted).decode("utf-8"),
        "key_id": key_data["key_id"],
    }

    put_url = f"https://api.github.com/repos/{owner}/{repo}/actions/secrets/{args.name}"
    proc = subprocess.run(
        [
            "curl", "-fsS", "-X", "PUT",
            "-H", f"Authorization: Bearer {gh_token}",
            "-H", "Accept: application/vnd.github+json",
            "-H", "X-GitHub-Api-Version: 2022-11-28",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(payload),
            put_url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return 1

    print(f"Set GitHub secret {args.name} on {args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
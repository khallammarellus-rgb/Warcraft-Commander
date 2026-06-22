#!/usr/bin/env python3
"""
Execute a hosted merge job: claim via portal API, pull KMZ from R2, merge, deploy, report back.

  python3 scripts/run_merge_job.py --job-id abc123 --portal-origin https://wow-commander-campaign.pages.dev
  python3 scripts/run_merge_job.py --job-id abc123 --no-deploy

Requires ORGANIZER_SECRET in env (or --organizer-secret). Cloudflare deploy needs
CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID when --deploy is set.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from portal_http import api_json
from process_r2_turns import download_r2_object, wrangler_bin

BUCKET = "wow-commander-turns"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a portal merge job end-to-end")
    parser.add_argument("--job-id", required=True, help="Merge job id from portal KV")
    parser.add_argument(
        "--portal-origin",
        default=os.environ.get("PORTAL_ORIGIN", "https://wow-commander-campaign.pages.dev"),
        help="Portal base URL (no trailing slash)",
    )
    parser.add_argument("--organizer-secret", default=os.environ.get("ORGANIZER_SECRET"))
    parser.add_argument("--deploy", action="store_true", default=True, help="Deploy portal after merge (default)")
    parser.add_argument("--no-deploy", action="store_true", help="Merge only — skip Pages deploy")
    args = parser.parse_args()

    if args.no_deploy:
        args.deploy = False

    token = (args.organizer_secret or "").strip()
    if not token:
        print("Set ORGANIZER_SECRET or pass --organizer-secret", file=sys.stderr)
        return 1

    origin = args.portal_origin.rstrip("/")
    project_root = Path(__file__).resolve().parent.parent

    claim = api_json("POST", f"{origin}/api/merge/{args.job_id}/claim", token)
    job = claim.get("job") or {}
    game_id = job.get("game_id")
    if not game_id:
        print(f"Claim failed or missing job payload: {claim}", file=sys.stderr)
        return 1

    r2_key = job.get("r2_key") or ""
    canonical = job.get("canonical_name") or Path(r2_key).name
    cell = job.get("cell")
    variant = job.get("variant") or "wowcommanderalpha"
    theater = job.get("theater")

    archive_dir = project_root / "portal" / "local_turns" / "games" / game_id / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / canonical

    if not wrangler_bin(project_root).exists():
        _complete(origin, token, args.job_id, ok=False, error="wrangler not installed — cd portal && npm install")
        return 1

    print(f"Downloading s3://{BUCKET}/{r2_key} → {dest}")
    rc = download_r2_object(project_root, r2_key, dest)
    if rc != 0 or not dest.is_file():
        _complete(origin, token, args.job_id, ok=False, error=f"R2 download failed for {r2_key}")
        return rc or 1

    merge_script = project_root / "scripts" / "process_r2_turns.py"
    cmd = [
        sys.executable,
        str(merge_script),
        "--game",
        game_id,
        "--variant",
        variant,
        "--merge-file",
        str(dest),
    ]
    if cell:
        cmd.extend(["--cell", cell])
    if theater:
        cmd.extend(["--theater", theater])
    if args.deploy:
        cmd.append("--deploy")

    print("Running:", " ".join(cmd))
    rc = subprocess.call(cmd, cwd=project_root)
    if rc != 0:
        _complete(origin, token, args.job_id, ok=False, error=f"merge pipeline exited {rc}")
        return rc

    deploy_url = f"{origin}/games/{game_id}/"
    _complete(origin, token, args.job_id, ok=True, deploy_url=deploy_url)
    print(f"Merge job {args.job_id} complete — refresh GEP NetworkLinks for {game_id}")
    return 0


def _complete(
    origin: str,
    token: str,
    job_id: str,
    *,
    ok: bool,
    error: str | None = None,
    deploy_url: str | None = None,
) -> None:
    payload = {"ok": ok}
    if error:
        payload["error"] = error
    if deploy_url:
        payload["deploy_url"] = deploy_url
    api_json("POST", f"{origin}/api/merge/{job_id}/complete", token, payload)


if __name__ == "__main__":
    raise SystemExit(main())
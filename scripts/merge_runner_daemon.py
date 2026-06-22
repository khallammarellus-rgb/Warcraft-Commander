#!/usr/bin/env python3
"""
Poll the portal for pending merge jobs and run them locally.

Use when GITHUB_MERGE_DISPATCH_TOKEN / MERGE_RUNNER_WEBHOOK_URL are not configured.

  export ORGANIZER_SECRET=...
  python3 scripts/merge_runner_daemon.py
  python3 scripts/merge_runner_daemon.py --once
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_ORIGIN = "https://wow-commander-campaign.pages.dev"


def _fetch_pending(origin: str, token: str) -> list[dict]:
    req = urllib.request.Request(
        f"{origin.rstrip('/')}/api/merge/pending",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("jobs") or []


def main() -> int:
    parser = argparse.ArgumentParser(description="Poll and run portal merge jobs")
    parser.add_argument("--portal-origin", default=os.environ.get("PORTAL_ORIGIN", DEFAULT_ORIGIN))
    parser.add_argument("--organizer-secret", default=os.environ.get("ORGANIZER_SECRET"))
    parser.add_argument("--interval", type=int, default=45, help="Poll interval seconds")
    parser.add_argument("--once", action="store_true", help="Process one batch and exit")
    args = parser.parse_args()

    token = (args.organizer_secret or "").strip()
    if not token:
        print("Set ORGANIZER_SECRET", file=sys.stderr)
        return 1

    origin = args.portal_origin.rstrip("/")
    project_root = Path(__file__).resolve().parent.parent
    runner = project_root / "scripts" / "run_merge_job.py"

    while True:
        try:
            jobs = _fetch_pending(origin, token)
        except urllib.error.HTTPError as exc:
            print(f"Pending poll failed ({exc.code})", file=sys.stderr)
            if args.once:
                return 1
            time.sleep(args.interval)
            continue

        if not jobs:
            if args.once:
                print("No pending merge jobs.")
                return 0
        else:
            for job in jobs:
                job_id = job.get("id")
                if not job_id:
                    continue
                print(f"Running merge job {job_id} ({job.get('canonical_name')})")
                rc = subprocess.call(
                    [sys.executable, str(runner), "--job-id", job_id, "--portal-origin", origin],
                    cwd=project_root,
                )
                if rc != 0:
                    print(f"Job {job_id} failed (exit {rc})", file=sys.stderr)

        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
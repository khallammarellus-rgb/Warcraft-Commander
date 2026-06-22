#!/usr/bin/env python3
"""
Process pending board-turn archives from R2 (or local mirror) and merge into campaign KML.

After merge, rebuild portal dist and optionally deploy.

  python3 scripts/process_r2_turns.py --game table-01 --list
  python3 scripts/process_r2_turns.py --game table-01 --merge-latest --variant wowcommanderalpha
  python3 scripts/process_r2_turns.py --game table-01 --merge-latest --deploy

Requires local campaign tree; R2 download uses wrangler r2 object get when --from-r2 is set.
For local dev, copy archives to portal/local_turns/games/{id}/archive/ and omit --from-r2.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from merge_campaign_submission import merge_cell_folder
from package_wargame_client import campaign_dir_for_variant
from portal_games import game_by_id


BUCKET_NAME = "wow-commander-turns"


def wrangler_bin(project_root: Path) -> Path:
    return project_root / "portal" / "node_modules" / ".bin" / "wrangler"


def download_r2_object(project_root: Path, r2_key: str, dest: Path) -> int:
    wrangler = wrangler_bin(project_root)
    if not wrangler.exists():
        print("Install wrangler: cd portal && npm install", file=sys.stderr)
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(wrangler),
        "r2",
        "object",
        "get",
        f"{BUCKET_NAME}/{r2_key}",
        "--file",
        str(dest),
        "--remote",
    ]
    print(" ".join(cmd))
    return subprocess.call(cmd, cwd=project_root / "portal")


def _list_r2_archives(project_root: Path, game_id: str) -> list[str]:
    wrangler = wrangler_bin(project_root)
    if not wrangler.exists():
        return []
    prefix = f"games/{game_id}/archive/"
    cmd = [
        str(wrangler),
        "r2",
        "object",
        "list",
        BUCKET_NAME,
        f"--prefix={prefix}",
        "--remote",
    ]
    proc = subprocess.run(cmd, cwd=project_root / "portal", capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return []
    keys: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("Listing"):
            continue
        if line.endswith(".kmz"):
            keys.append(line if "/" in line else f"{prefix}{line}")
    return sorted(keys)


def _sync_archives_from_r2(project_root: Path, game_id: str, dest_dir: Path) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    keys = _list_r2_archives(project_root, game_id)
    if not keys:
        print(f"No KMZ objects under games/{game_id}/archive/ in R2", file=sys.stderr)
        return 1
    failures = 0
    for key in keys:
        name = Path(key).name
        rc = download_r2_object(project_root, key, dest_dir / name)
        if rc != 0:
            failures += 1
    return 1 if failures else 0


def _latest_board_archive(archive_dir: Path) -> Path | None:
    kmz = sorted(archive_dir.glob("*_*Cell.kmz"), key=lambda p: p.stat().st_mtime)
    return kmz[-1] if kmz else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge latest R2 turn into campaign KML")
    parser.add_argument("--game", required=True, help="Portal game id (table-01)")
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument("--list", action="store_true", help="List local archive files")
    parser.add_argument("--merge-latest", action="store_true", help="Merge newest board KMZ")
    parser.add_argument("--merge-file", default=None, help="Explicit archive KMZ to merge")
    parser.add_argument("--cell", default=None, help="Cell folder name (red-cell / blue-cell)")
    parser.add_argument("--theater", default=None, help="Theater id (default: from game_session)")
    parser.add_argument("--from-r2", action="store_true", help="Pull all archives from R2 before merge")
    parser.add_argument("--deploy", action="store_true", help="Run publish_portal_site --deploy --game")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    game = game_by_id(project_root, args.game)
    if not game:
        print(f"Unknown game: {args.game}", file=sys.stderr)
        return 1

    archive_dir = project_root / "portal" / "local_turns" / "games" / args.game / "archive"
    if args.from_r2:
        rc = _sync_archives_from_r2(project_root, args.game, archive_dir)
        if rc != 0:
            return rc

    if not archive_dir.is_dir():
        print(f"No archive dir: {archive_dir}", file=sys.stderr)
        return 1

    files = sorted(archive_dir.glob("*.kmz"))
    if args.list:
        for f in files:
            print(f.name)
        return 0

    if not args.merge_latest and not args.merge_file:
        parser.print_help()
        return 0

    if args.merge_file:
        latest = Path(args.merge_file)
        if not latest.is_file():
            print(f"Missing merge file: {latest}", file=sys.stderr)
            return 1
    else:
        latest = _latest_board_archive(archive_dir)
        if not latest:
            print("No board KMZ archives found", file=sys.stderr)
            return 1

    cell = args.cell
    if not cell:
        name = latest.stem
        if "BlueCell" in name:
            cell = "blue-cell"
        elif "RedCell" in name:
            cell = "red-cell"
        else:
            print("Pass --cell red-cell|blue-cell", file=sys.stderr)
            return 1

    campaign_dir = campaign_dir_for_variant(project_root, args.variant)
    theater = args.theater
    if not theater:
        from campaign_session import load_session

        session = load_session(project_root, variant=args.variant)
        theater = (session or {}).get("theater", "kalimdor")

    master = campaign_dir / f"{theater}.kml"
    if not master.exists():
        print(f"Missing master: {master}", file=sys.stderr)
        return 1

    print(f"Merging {latest.name} → {master} (cell={cell})")
    merge_cell_folder(
        master,
        latest,
        cell=cell,
        theater_id=theater,
    )
    print("Merge complete.")

    if args.deploy:
        script = project_root / "scripts" / "publish_portal_site.py"
        cmd = [sys.executable, str(script), "--all-games", "--deploy", "--game", args.game]
        return subprocess.call(cmd)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""
Refresh player/ and optionally git-push to Warcraft-Commander (tiles in ~1 GB batches).

  python3 scripts/sync_player_package.py
  python3 scripts/sync_player_package.py --push
  python3 scripts/sync_player_package.py --push --skip-tiles-copy   # metadata only push

Mirrors sync_explorer_project.py but targets player/ inside this repo.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from package_commander_player import PLAYER_DIR, package_commander_player
from sync_explorer_project import batch_tile_regions, dir_size, tile_region_dirs

DEFAULT_CHUNK_GB = 1.0
PLAYER_SUBPATH = Path(PLAYER_DIR)


def git_push_origin(cwd: Path) -> None:
    push = subprocess.run(
        ["git", "push", "origin", "HEAD"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if push.returncode != 0:
        err = (push.stderr or "") + (push.stdout or "")
        if "non-fast-forward" in err or "rejected" in err:
            subprocess.run(["git", "pull", "--rebase", "origin", "HEAD"], cwd=cwd, check=True)
            subprocess.run(["git", "push", "origin", "HEAD"], cwd=cwd, check=True)
        else:
            raise SystemExit(err or f"git push failed ({push.returncode})")


def git_commit_paths(repo_root: Path, message: str, paths: list[Path]) -> bool:
    for path in paths:
        rel = path.relative_to(repo_root).as_posix()
        subprocess.run(["git", "add", "-A", "--", rel], cwd=repo_root, check=True)
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *[p.relative_to(repo_root).as_posix() for p in paths]],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    if not status.stdout.strip():
        return False
    subprocess.run(["git", "commit", "-m", message], cwd=repo_root, check=True)
    git_push_origin(repo_root)
    return True


def player_metadata_paths(repo_root: Path) -> list[Path]:
    player = repo_root / PLAYER_DIR
    if not player.is_dir():
        return []
    paths: list[Path] = []
    for child in player.iterdir():
        if child.name == "tiles":
            continue
        paths.append(child)
    return paths


def git_push_player(repo_root: Path, version: str, *, chunk_gb: float) -> int:
    player = repo_root / PLAYER_DIR
    tiles_root = player / "tiles"
    if not tiles_root.is_dir():
        raise SystemExit(f"Missing {tiles_root} — run without --skip-tiles-copy")

    chunk_bytes = int(chunk_gb * 1024 * 1024 * 1024)
    regions = tile_region_dirs(tiles_root)
    batches = batch_tile_regions(regions, chunk_bytes)
    pushes = 0

    meta = player_metadata_paths(repo_root)
    if git_commit_paths(repo_root, f"Sync WoW Commander player v{version} (KML + scripts)", meta):
        pushes += 1
        print(f"  Git push {pushes}: player/ metadata (no tiles)")

    total = len(batches)
    for index, batch in enumerate(batches, start=1):
        batch_paths = [tiles_root / name for name in batch]
        batch_bytes = sum(size for name, size in regions if name in batch)
        batch_mb = round(batch_bytes / (1024 * 1024), 1)
        label = ", ".join(batch[:3])
        if len(batch) > 3:
            label += f", +{len(batch) - 3} more"
        message = f"Player tiles batch {index}/{total} (~{batch_mb} MB): {label}"
        if git_commit_paths(repo_root, message, batch_paths):
            pushes += 1
            print(f"  Git push {pushes}: tiles batch {index}/{total} (~{batch_mb} MB)")

    return pushes


def write_player_release_config(repo_root: Path, manifest: dict) -> None:
    cfg = {
        "github_repo": manifest.get("github_repo"),
        "download_url": manifest.get("download_url"),
        "entry_kml": manifest.get("entry_kml"),
        "globe_version": manifest.get("globe_version"),
        "packaged_at": manifest.get("packaged_at"),
        "tile_files": manifest.get("tile_files"),
        "region_count": manifest.get("region_count"),
        "instructions": "Code → Download ZIP → open player/WoW Commander.kml",
    }
    path = repo_root / "config" / "player_release.json"
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync player/ package to Warcraft-Commander repo")
    parser.add_argument("--skip-tiles-copy", action="store_true", help="Package without copying tiles")
    parser.add_argument("--push", action="store_true", help="Git commit + push player/ in batches")
    parser.add_argument("--chunk-gb", type=float, default=DEFAULT_CHUNK_GB, help="Tile batch size for git push")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    result = package_commander_player(repo_root, skip_tiles=args.skip_tiles_copy)
    write_player_release_config(repo_root, result)

    print(f"Synced {result['dest']}")
    print(f"  Players: Code → Download ZIP → {result['entry_kml']}")

    if not args.push:
        print("  Git: run with --push to upload player/tiles/ in batches")
        return 0

    version = result.get("globe_version", "v3")
    pushes = git_push_player(repo_root, version, chunk_gb=args.chunk_gb)
    print(f"  Done: {pushes} git push(es) → {result['download_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
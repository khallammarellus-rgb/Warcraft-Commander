#!/usr/bin/env python3
"""
Copy Commander globe assets into the Azeroth Explorer project folder.

  python3 scripts/sync_explorer_project.py
  python3 scripts/sync_explorer_project.py --push              # git push in ~1 GB tile batches
  python3 scripts/sync_explorer_project.py --push-metadata-only  # KML/docs only (no tiles)

The Explorer project is a sibling folder — not inside Commander.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from package_azeroth_explorer import explorer_project_dir, package_explorer, split_zip_for_upload
from publish_github_pages import render_page

DEFAULT_CHUNK_GB = 1
DEFAULT_SPLIT_GB = 1
REMOTE = "git@github.com:khallammarellus-rgb/Azeroth-Explorer.git"
SKIP_TOP_LEVEL = {".DS_Store", ".git", "tiles", "exports"}

GITIGNORE_METADATA_ONLY = """# macOS
.DS_Store

# Map tiles — use --push (default) to upload in 1 GB git batches instead
tiles/
exports/
*.zip
*.z01
*.z02
*.z03
*.z04
*.z05
"""

GITIGNORE_WITH_TILES = """# macOS
.DS_Store

# Release zips — too large for git (upload exports/*-parts/ to GitHub Releases)
exports/
"""


def explorer_project_root(commander_root: Path) -> Path:
    dest = explorer_project_dir(commander_root)
    if dest is None:
        raise SystemExit("Missing config/explorer_project.json")
    return dest


def dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def tile_region_dirs(tiles_root: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for entry in sorted(tiles_root.iterdir()):
        if entry.is_dir():
            rows.append((entry.name, dir_size(entry)))
    return rows


def batch_tile_regions(regions: list[tuple[str, int]], chunk_bytes: int) -> list[list[str]]:
    """Group tile folders into ~chunk_bytes batches (largest regions first)."""
    ordered = sorted(regions, key=lambda row: row[1], reverse=True)
    batches: list[list[str]] = []
    current: list[str] = []
    current_size = 0

    for name, size in ordered:
        if current and current_size + size > chunk_bytes:
            batches.append(current)
            current = []
            current_size = 0
        current.append(name)
        current_size += size

    if current:
        batches.append(current)
    return batches


def ensure_git_repo(dest: Path) -> None:
    if (dest / ".git").is_dir():
        return
    subprocess.run(["git", "init"], cwd=dest, check=True)
    subprocess.run(["git", "branch", "-M", "main"], cwd=dest, check=True)
    subprocess.run(["git", "remote", "add", "origin", REMOTE], cwd=dest, check=True)


def git_push(dest: Path) -> None:
    push = subprocess.run(
        ["git", "push", "-u", "origin", "main"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    if push.returncode != 0:
        err = (push.stderr or "") + (push.stdout or "")
        if "non-fast-forward" in err or "rejected" in err:
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=dest, check=True)
            subprocess.run(["git", "push", "-u", "origin", "main"], cwd=dest, check=True)
        else:
            subprocess.run(["git", "push", "-u", "origin", "main"], cwd=dest, check=True)


def git_commit_paths(dest: Path, message: str, paths: list[Path]) -> bool:
    for path in paths:
        subprocess.run(["git", "add", "-A", "--", str(path)], cwd=dest, check=True)
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=True,
    )
    if not status.stdout.strip():
        return False
    subprocess.run(["git", "commit", "-m", message], cwd=dest, check=True)
    git_push(dest)
    return True


def top_level_paths(dest: Path) -> list[Path]:
    return [p for p in dest.iterdir() if p.name not in SKIP_TOP_LEVEL]


def git_push_metadata_only(dest: Path, version: str) -> None:
    ensure_git_repo(dest)
    git_commit_paths(dest, f"Sync Azeroth Explorer v{version} (metadata)", top_level_paths(dest))


def git_push_chunked_tiles(dest: Path, version: str, *, chunk_gb: float) -> int:
    """Push KML/docs first, then tiles/_shared + each region batch (~chunk_gb per push)."""
    ensure_git_repo(dest)
    tiles_root = dest / "tiles"
    if not tiles_root.is_dir():
        raise SystemExit(f"Missing {tiles_root}")

    chunk_bytes = int(chunk_gb * 1024 * 1024 * 1024)
    regions = tile_region_dirs(tiles_root)
    batches = batch_tile_regions(regions, chunk_bytes)
    pushes = 0

    if git_commit_paths(dest, f"Sync Azeroth Explorer v{version} (KML + docs)", top_level_paths(dest)):
        pushes += 1
        print(f"  Git push {pushes}: KML, docs, manifest")

    total = len(batches)
    for index, batch in enumerate(batches, start=1):
        batch_paths = [tiles_root / name for name in batch]
        batch_bytes = sum(size for name, size in regions if name in batch)
        batch_mb = round(batch_bytes / (1024 * 1024), 1)
        label = ", ".join(batch[:4])
        if len(batch) > 4:
            label += f", +{len(batch) - 4} more"
        message = f"Tiles batch {index}/{total} (~{batch_mb} MB): {label}"
        if git_commit_paths(dest, message, batch_paths):
            pushes += 1
            print(f"  Git push {pushes}: tiles batch {index}/{total} (~{batch_mb} MB)")

    return pushes


def sync_explorer(
    commander_root: Path,
    *,
    skip_build: bool,
    push_tiles: bool,
    split_gb: float,
) -> dict:
    dest = explorer_project_root(commander_root)
    dest.mkdir(parents=True, exist_ok=True)

    result = package_explorer(
        commander_root,
        package_dir=dest,
        skip_build=skip_build,
        skip_zip=True,
    )

    config = dest / "config"
    config.mkdir(exist_ok=True)
    stale = config / "commander_source.json"
    if stale.is_file():
        stale.unlink()
    shutil.copy2(
        commander_root / "config" / "explorer_project.json",
        config / "commander_project.json",
    )

    docs = dest / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "index.html").write_text(render_page(commander_root), encoding="utf-8")
    (docs / ".nojekyll").write_text("", encoding="utf-8")

    gitignore = GITIGNORE_WITH_TILES if push_tiles else GITIGNORE_METADATA_ONLY
    (dest / ".gitignore").write_text(gitignore, encoding="utf-8")

    version = result["version"]
    map_zip = result["zip"]
    exports = dest / "exports"
    exports.mkdir(exist_ok=True)
    if map_zip.is_file():
        shutil.copy2(map_zip, exports / map_zip.name)

    part_count = 0
    if split_gb and map_zip.is_file():
        split_mb = max(1, int(split_gb * 1024))
        parts = split_zip_for_upload(exports / map_zip.name, split_mb)
        part_count = len([p for p in parts if p.suffix not in {".txt"}])

    push_mode = (
        f"git push in ~{split_gb:g} GB tile batches"
        if push_tiles
        else "metadata-only git push (tiles excluded)"
    )
    (dest / "DEVELOPERS.md").write_text(
        f"""# Azeroth Explorer — developer notes

Built from **WoW Commander Alpha Project**.

## Refresh

```bash
cd "../WoW Commander Alpha Project"
python3 scripts/sync_explorer_project.py --push
```

## Git publish

Default `--push` uploads tiles in ~{DEFAULT_CHUNK_GB} GB batches so GitHub accepts the repo.
Release zips are split into ~{DEFAULT_SPLIT_GB} GB parts under `exports/` for GitHub Releases.

## Open locally

File → Open → `Azeroth Explorer.kml` (keep `kml/` and `tiles/` alongside it).
""",
        encoding="utf-8",
    )

    return {
        "dest": dest,
        "map_zip": map_zip,
        "version": version,
        "tile_files": result["tile_files"],
        "region_count": result["region_count"],
        "part_count": part_count,
        "push_tiles": push_tiles,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Explorer package to its own folder")
    parser.add_argument("--skip-build", action="store_true", help="Use existing Commander KML")
    parser.add_argument("--push", action="store_true", help="Git push (~1 GB tile batches)")
    parser.add_argument(
        "--push-metadata-only",
        action="store_true",
        help="Git push KML/docs only (skip tiles/)",
    )
    parser.add_argument(
        "--chunk-gb",
        type=float,
        default=DEFAULT_CHUNK_GB,
        help="Target size per git push batch for tiles/ (default: 1)",
    )
    parser.add_argument(
        "--split-gb",
        type=float,
        default=DEFAULT_SPLIT_GB,
        help="Split MAP zip into N-GB parts under exports/ (default: 1)",
    )
    args = parser.parse_args()

    if args.push and args.push_metadata_only:
        raise SystemExit("Use either --push or --push-metadata-only, not both")

    push_tiles = bool(args.push and not args.push_metadata_only)
    commander_root = Path(__file__).resolve().parent.parent
    result = sync_explorer(
        commander_root,
        skip_build=args.skip_build,
        push_tiles=push_tiles,
        split_gb=args.split_gb if (args.push or args.push_metadata_only) else 0,
    )
    dest = result["dest"]
    print(f"Globe copied from Commander → {dest}")
    print(f"  Regions: {result['region_count']}")
    print(f"  Tile PNGs: {result['tile_files']} (in tiles/)")
    print(f"  Underlay: {dest / 'tiles/_shared/terrain_underlay.png'}")
    print(f"  Open: {dest / 'Azeroth Explorer.kml'}")
    if result["map_zip"]:
        print(f"  MAP zip: {dest / 'exports' / result['map_zip'].name}")
    if result["part_count"]:
        print(f"  Release parts: {result['part_count']} files in exports/ (*-parts/)")

    if args.push:
        pushes = git_push_chunked_tiles(dest, result["version"], chunk_gb=args.chunk_gb)
        print(f"  Done: {pushes} git push(es) → https://github.com/khallammarellus-rgb/Azeroth-Explorer")
    elif args.push_metadata_only:
        git_push_metadata_only(dest, result["version"])
        print("  Pushed metadata only → https://github.com/khallammarellus-rgb/Azeroth-Explorer")
    else:
        print("  Run with --push to upload tiles in ~1 GB git batches")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
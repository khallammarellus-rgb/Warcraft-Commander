#!/usr/bin/env python3
"""
Package a player-install zip for GitHub Releases.

Includes scripts, config, KML entry points, map tiles (02-tiles), and assets
needed to play locally. Excludes raw exports (01-raw-export, 04-edited-exports).

  python3 scripts/package_player_release.py
  python3 scripts/package_player_release.py --split-mb 1800
  python3 scripts/package_player_release.py --out exports/wowcommander-player-v3.zip
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_kml_superoverlay import merge_variant_config
from globe_placement import load_globe_config
from package_azeroth_explorer import split_zip_for_upload

COMMANDER_REPO = "khallammarellus-rgb/Warcraft-Commander"
DEFAULT_SPLIT_MB = 1800

DEFAULT_VARIANT = "wowcommanderalpha"

INCLUDE_PATHS = [
    "scripts/WOW Commander.command",
    "scripts/player_menu.py",
    "scripts/setup_campaign.py",
    "scripts/open_theater_campaign.py",
    "scripts/sync_campaign_live.py",
    "scripts/package_wargame_client.py",
    "scripts/configure_hosted_campaign.py",
    "scripts/build_hosted_player_kml.py",
    "scripts/campaign_session.py",
    "scripts/campaign_deploy.py",
    "scripts/campaign_hosted_views.py",
    "scripts/campaign_visibility.py",
    "scripts/campaign_tier_lod.py",
    "scripts/campaign_live_io.py",
    "scripts/campaign_hq.py",
    "scripts/campaign_org_tree.py",
    "scripts/campaign_branding.py",
    "scripts/campaign_briefing.py",
    "scripts/campaign_dossier.py",
    "scripts/campaign_terminal_image.py",
    "scripts/campaign_tactician_opord.py",
    "scripts/campaign_setup_tui.py",
    "scripts/clipboard_utils.py",
    "scripts/faction_library.py",
    "scripts/globe_placement.py",
    "scripts/build_kml_superoverlay.py",
    "scripts/build_campaign_live.py",
    "scripts/build_world_globe.py",
    "scripts/quick_view.py",
    "scripts/places_hierarchy.py",
    "scripts/mgrs_utils.py",
    "scripts/tile_filters.py",
    "scripts/package_wargame_client.py",
    "config/globe.json",
    "config/placements",
    "config/subterranean.json",
    "config/misc_islands.json",
    "assets/faction_library",
    "requirements.txt",
]

PLAYER_KML_GLOBS = [
    "03-kml/wowcommanderalpha/doc_player.kml",
    "03-kml/wowcommanderalpha/doc_maps.kml",
    "03-kml/wowcommanderalpha/campaign_live.kml",
    "03-kml/wowcommanderalpha/campaign_live.kmz",
]


def _globe_version_label(project_root: Path) -> str:
    globe = load_globe_config(project_root)
    gv = globe.get("globe_version") or {}
    return str(gv.get("id", "v3"))


def _collect_files(project_root: Path) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen or not path.exists():
            return
        seen.add(resolved)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and ".DS_Store" not in child.name:
                    if child.resolve() not in seen:
                        seen.add(child.resolve())
                        files.append(child)

    for rel in INCLUDE_PATHS:
        add(project_root / rel)

    variant_dir = project_root / "03-kml" / DEFAULT_VARIANT
    if variant_dir.is_dir():
        for child in variant_dir.rglob("*.kml"):
            if "campaign" not in child.parts:
                add(child)

    for rel in PLAYER_KML_GLOBS:
        add(project_root / rel)

    campaign_dir = project_root / "03-kml" / DEFAULT_VARIANT / "campaign"
    if campaign_dir.is_dir():
        for child in campaign_dir.glob("*.kml"):
            add(child)

    base = load_globe_config(project_root)
    config = merge_variant_config(base, DEFAULT_VARIANT)
    tiles_root = project_root / "02-tiles"
    for layer in config.get("layers", []):
        if not layer.get("enabled"):
            continue
        if layer.get("layer_type") != "minimap":
            continue
        region_id = layer.get("id")
        if not region_id:
            continue
        add(tiles_root / region_id)

    return sorted(files)


def _default_output(project_root: Path) -> Path:
    version = _globe_version_label(project_root)
    today = date.today().isoformat()
    exports = project_root / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    return exports / f"wowcommander-player-{version}_{today}.zip"


def package_release(project_root: Path, output: Path) -> dict:
    files = _collect_files(project_root)
    output.parent.mkdir(parents=True, exist_ok=True)

    tile_files = sum(
        1 for p in files if "02-tiles" in p.parts
    )
    manifest = {
        "variant": DEFAULT_VARIANT,
        "globe_version": _globe_version_label(project_root),
        "file_count": len(files),
        "tile_files": tile_files,
        "tiles_included": tile_files > 0,
    }

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        total = len(files)
        for index, path in enumerate(files, start=1):
            arcname = path.relative_to(project_root).as_posix()
            compress = zipfile.ZIP_STORED if path.suffix.lower() == ".png" else zipfile.ZIP_DEFLATED
            zf.write(path, arcname, compress_type=compress)
            if index % 2000 == 0 or index == total:
                print(f"  Packed {index}/{total} files…", flush=True)
        getting_started = project_root / "docs" / "PLAYER_GETTING_STARTED.txt"
        if getting_started.is_file():
            zf.write(getting_started, "GETTING_STARTED.txt")
        zf.writestr(
            "PLAYER_RELEASE_README.txt",
            (
                "WoW Commander Alpha — player pack\n"
                "================================\n\n"
                "Full setup: read GETTING_STARTED.txt in this folder.\n\n"
                "Quick start:\n"
                "1. Join split parts if needed (see HOW_TO_JOIN.txt).\n"
                "2. Unzip anywhere (keep folder structure).\n"
                "3. python3 -m pip install -r requirements.txt\n"
                "4. Open 03-kml/wowcommanderalpha/doc_player.kml in Google Earth Pro\n"
                "5. Portal: https://wow-commander-campaign.pages.dev/start/\n\n"
                f"Packaged: {date.today().isoformat()}\n"
                f"Globe: {manifest['globe_version']}\n"
            ),
        )
        zf.writestr("release_manifest.json", json.dumps(manifest, indent=2) + "\n")

    return {"output": output, **manifest}


def _write_player_release_config(project_root: Path, result: dict, *, split_mb: int | None) -> Path:
    output: Path = result["output"]
    version = result["globe_version"]
    tag = f"player-{version}"
    cfg = {
        "github_repo": COMMANDER_REPO,
        "github_releases_url": f"https://github.com/{COMMANDER_REPO}/releases/tag/{tag}",
        "release_tag": tag,
        "asset_zip": output.name,
        "packaged_at": date.today().isoformat(),
        "globe_version": version,
        "file_count": result["file_count"],
        "tile_files": result["tile_files"],
        "split_mb": split_mb,
        "player_entry": "03-kml/wowcommanderalpha/doc_player.kml",
    }
    if split_mb:
        cfg["parts_dir"] = f"exports/{output.stem}-parts"
    path = project_root / "config" / "player_release.json"
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return path


def _write_upload_notes(project_root: Path, result: dict, *, split_mb: int | None) -> Path:
    output: Path = result["output"]
    version = result["globe_version"]
    tag = f"player-{version}"
    releases_url = f"https://github.com/{COMMANDER_REPO}/releases"
    lines = [
        "How to publish the WoW Commander player pack on GitHub Releases",
        "================================================================",
        "",
        "CAN PLAYERS USE \"Source code (zip)\"?",
        "  No. That snapshot has no 02-tiles/ map imagery.",
        "",
        "WHAT TO UPLOAD",
        f"  {output}",
    ]
    if split_mb:
        lines.extend(
            [
                f"  exports/{output.stem}-parts/  (all .zip + .zNN parts + HOW_TO_JOIN.txt)",
                "",
                f"GitHub allows up to 2 GB per file — this pack is split at {split_mb} MB.",
            ]
        )
    else:
        lines.append("  GitHub allows up to 2 GB per uploaded file.")
    lines.extend(
        [
            "",
            "STEPS",
            "  1. Build: python3 scripts/package_player_release.py --split-mb 1800",
            f"  2. GitHub → {COMMANDER_REPO} → Releases → Draft a new release",
            f"  3. Tag: {tag}   Title: WoW Commander player pack v{version}",
            "  4. Attach the zip (and all split parts if used) under Assets",
            "  5. At the TOP of the release description, paste:",
            "",
            f"     >>> DOWNLOAD: {output.name} (+ parts if split) <<<",
            '     Do NOT download "Source code (zip)".',
            "",
            "  6. Publish",
            "",
            "PORTAL",
            "  /start/ links to config/player_release.json → github_releases_url",
            "",
            "WHAT PLAYERS DO",
            "  1. Download assets from the release (not Source code)",
            "  2. Join parts if split, then unzip",
            "  3. Open 03-kml/wowcommanderalpha/doc_player.kml in Google Earth Pro",
            f"  4. Open table page: https://wow-commander-campaign.pages.dev/games/table-01/",
            "",
        ]
    )
    path = project_root / "exports" / "PLAYER_RELEASE_UPLOAD.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Package player release zip for GitHub")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--split-mb",
        type=int,
        default=DEFAULT_SPLIT_MB,
        help=f"Split zip into N-MB parts for GitHub (0 = single file). Default: {DEFAULT_SPLIT_MB}",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    output = args.out or _default_output(project_root)
    split_mb = None if not args.split_mb or args.split_mb <= 0 else args.split_mb

    print(f"Packaging player release → {output.name}")
    result = package_release(project_root, output)
    print(f"Wrote {result['output']} ({result['file_count']} files)")
    if result.get("tiles_included"):
        print(f"  Includes {result['tile_files']} tile files under 02-tiles/")
    else:
        print("  Warning: no 02-tiles/ found — run build_world_globe.py first")
        return 1

    split_parts: list[Path] = []
    if split_mb:
        print(f"Splitting for GitHub upload ({split_mb} MB parts)…")
        split_parts = split_zip_for_upload(output, split_mb)
        parts_dir = output.parent / f"{output.stem}-parts"
        (parts_dir / "DOWNLOAD.txt").write_text(
            f"""WoW Commander — what to download from GitHub

DO NOT download "Source code (zip)" or "Source code (tar.gz)".
Those are developer snapshots without map tiles.

DO download every file under ASSETS on the release page:
  {output.name}
  {output.stem}.z01, .z02, … (all parts)
  HOW_TO_JOIN.txt

Then follow HOW_TO_JOIN.txt to join and unzip the player pack.
""",
            encoding="utf-8",
        )
        (parts_dir / "HOW_TO_JOIN.txt").write_text(
            f"""WoW Commander — join split zip parts

Download every ASSET from the GitHub release (not "Source code"):
  {output.name}
  {output.stem}.z01, .z02, … (all parts)

Put them in one folder, then:

Mac Terminal (from that folder):
  zip -FF {output.name} --out {output.stem}-joined.zip
  unzip {output.stem}-joined.zip

Windows (7-Zip):
  Select all part files → 7-Zip → Extract Here

Open 03-kml/wowcommanderalpha/doc_player.kml in Google Earth Pro.
Keep 02-tiles/, 03-kml/, scripts/, and config/ together.
""",
            encoding="utf-8",
        )
        print(f"  Parts: {len([p for p in split_parts if p.suffix != '.txt'])} files in {parts_dir}")

    cfg_path = _write_player_release_config(project_root, result, split_mb=split_mb)
    notes_path = _write_upload_notes(project_root, result, split_mb=split_mb)
    print(f"  Config: {cfg_path.relative_to(project_root)}")
    print(f"  Upload notes: {notes_path.relative_to(project_root)}")
    print(f"  Publish at: https://github.com/{COMMANDER_REPO}/releases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
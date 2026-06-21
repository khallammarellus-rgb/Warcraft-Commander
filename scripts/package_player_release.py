#!/usr/bin/env python3
"""
Package a player-install zip for GitHub Releases.

Includes scripts, config, KML entry points, map tiles (02-tiles), and assets
needed to play locally. Excludes raw exports (01-raw-export, 04-edited-exports).

  python3 scripts/package_player_release.py
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
        for path in files:
            arcname = path.relative_to(project_root).as_posix()
            zf.write(path, arcname)
        zf.writestr(
            "PLAYER_RELEASE_README.txt",
            (
                "WoW Commander Alpha — player pack\n"
                "================================\n\n"
                "1. Unzip anywhere (keep folder structure).\n"
                "2. Install Python deps: pip install -r requirements.txt\n"
                "3. Double-click scripts/WOW Commander.command\n"
                "4. Open doc_player.kml in Google Earth Pro when prompted\n\n"
                f"Packaged: {date.today().isoformat()}\n"
                f"Globe: {manifest['globe_version']}\n"
            ),
        )
        zf.writestr("release_manifest.json", json.dumps(manifest, indent=2) + "\n")

    return {"output": output, **manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description="Package player release zip for GitHub")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    output = args.out or _default_output(project_root)
    result = package_release(project_root, output)
    print(f"Wrote {result['output']} ({result['file_count']} files)")
    if result.get("tiles_included"):
        print(f"  Includes {result['tile_files']} tile files under 02-tiles/")
    else:
        print("  Warning: no 02-tiles/ found — run build_world_globe.py first")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
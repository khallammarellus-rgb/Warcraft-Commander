#!/usr/bin/env python3
"""
Package WoW Commander player install — Explorer-style flat layout under player/.

  python3 scripts/package_commander_player.py
  python3 scripts/package_commander_player.py --skip-tiles   # KML + scripts only (fast test)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_kml_superoverlay import merge_variant_config
from globe_placement import layer_by_id, load_globe_config
from package_azeroth_explorer import (
    ensure_commander_globe_assets,
    rewrite_entry_hrefs,
    rewrite_kml_paths,
)

PLAYER_DIR = "player"
ENTRY_KML = "WoW Commander.kml"
SOURCE_VARIANT = "wowcommanderalpha"
COMMANDER_REPO = "khallammarellus-rgb/Warcraft-Commander"
REPO_URL = f"https://github.com/{COMMANDER_REPO}"

PACKAGE_ROOT_FILES = (ENTRY_KML, "README.md", "manifest.json", "requirements.txt")
PACKAGE_DIRS = ("kml", "tiles", "scripts", "config", "assets", "03-kml")

SHARED_KML_FILES = frozenset({"terrain_underlay.kml", "pacific_vignette.kml"})
SKIP_KML_NAMES = frozenset(
    {"campaign", "doc.kml", "doc_player.kml", "doc_maps.kml", "doc_explorer.kml"}
)

PLAYER_SCRIPTS = [
    "WOW Commander.command",
    "WOW Commander.cmd",
    "player_install_wizard.py",
    "package_icon_pack.py",
    "import_icon_pack.py",
    "create_app_launcher.py",
    "player_menu.py",
    "setup_campaign.py",
    "open_theater_campaign.py",
    "sync_campaign_live.py",
    "package_wargame_client.py",
    "campaign_session.py",
    "campaign_deploy.py",
    "campaign_hosted_views.py",
    "campaign_visibility.py",
    "campaign_tier_lod.py",
    "campaign_live_io.py",
    "campaign_hq.py",
    "campaign_org_tree.py",
    "campaign_branding.py",
    "campaign_briefing.py",
    "campaign_dossier.py",
    "campaign_terminal_image.py",
    "campaign_tactician_opord.py",
    "campaign_setup_tui.py",
    "clipboard_utils.py",
    "faction_library.py",
    "globe_placement.py",
    "build_campaign_live.py",
    "quick_view.py",
    "places_hierarchy.py",
    "mgrs_utils.py",
    "tile_filters.py",
    "build_kml_superoverlay.py",
]

CONFIG_PATHS = [
    "config/globe.json",
    "config/placements",
    "config/subterranean.json",
    "config/misc_islands.json",
    "assets/faction_library",
    "assets/branding",
    "assets/player_custom_icons",
]


def enabled_region_ids(project_root: Path) -> list[str]:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, SOURCE_VARIANT)
    return [
        layer["id"]
        for layer in config.get("layers", [])
        if layer.get("enabled")
        and layer.get("layer_type") == "minimap"
        and layer.get("id")
    ]


def prepare_player_dir(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in (*PACKAGE_ROOT_FILES, *PACKAGE_DIRS):
        path = out_dir / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()


def rewrite_player_entry(text: str) -> str:
    text = rewrite_entry_hrefs(text)
    text = text.replace("<href>doc_maps.kml</href>", "<href>kml/doc_maps.kml</href>")
    text = text.replace("campaign_live.kml", "kml/campaign_live.kml")
    return text


def copy_kml_tree(project_root: Path, out_dir: Path, region_ids: list[str]) -> None:
    source_kml = project_root / "03-kml" / SOURCE_VARIANT
    kml_dest = out_dir / "kml"
    kml_dest.mkdir(parents=True)

    for item in source_kml.iterdir():
        if item.name in SKIP_KML_NAMES:
            continue
        if item.is_dir():
            if item.name not in region_ids:
                continue
            shutil.copytree(item, kml_dest / item.name)
        elif item.suffix.lower() == ".kml" and item.name in SHARED_KML_FILES:
            text = rewrite_kml_paths(item.read_text(encoding="utf-8"))
            (kml_dest / item.name).write_text(text, encoding="utf-8")

    for name in ("doc_maps.kml", "campaign_live.kml", "campaign_live.kmz"):
        src = source_kml / name
        if src.is_file():
            shutil.copy2(src, kml_dest / name)

    for kml_file in kml_dest.rglob("*.kml"):
        text = kml_file.read_text(encoding="utf-8")
        rewritten = rewrite_kml_paths(text)
        if rewritten != text:
            kml_file.write_text(rewritten, encoding="utf-8")


def _hardlink_tree(src: Path, dest: Path) -> None:
    """Hard-link a tile tree (no extra disk — same inode as 02-tiles/)."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cp", "-Rl", str(src), str(dest)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"cp -Rl {src} → {dest} failed: {result.stderr or result.stdout}")


def copy_tiles(project_root: Path, out_dir: Path, region_ids: list[str]) -> int:
    tiles_dest = out_dir / "tiles"
    tiles_dest.mkdir(parents=True, exist_ok=True)
    tiles_root = project_root / "02-tiles"
    shared_src = tiles_root / "_shared"
    if not shared_src.is_dir():
        raise SystemExit(f"Missing {shared_src} — run build_world_globe.py first")

    _hardlink_tree(shared_src, tiles_dest / "_shared")
    count = sum(1 for _ in (tiles_dest / "_shared").rglob("*") if _.is_file())
    for region_id in region_ids:
        src = tiles_root / region_id
        if not src.is_dir():
            raise SystemExit(f"Missing tiles for {region_id}: {src}")
        _hardlink_tree(src, tiles_dest / region_id)
        count += sum(1 for _ in (tiles_dest / region_id).rglob("*") if _.is_file())
    return count


def copy_scripts_and_config(project_root: Path, out_dir: Path) -> None:
    scripts_dest = out_dir / "scripts"
    scripts_dest.mkdir(parents=True)
    for name in PLAYER_SCRIPTS:
        src = project_root / "scripts" / name
        if src.is_file():
            shutil.copy2(src, scripts_dest / name)
    install_pkg = project_root / "scripts" / "player_install"
    if install_pkg.is_dir():
        dest_pkg = scripts_dest / "player_install"
        if dest_pkg.exists():
            shutil.rmtree(dest_pkg)
        shutil.copytree(install_pkg, dest_pkg)

    for rel in CONFIG_PATHS:
        src = project_root / rel
        dest = out_dir / rel
        if src.is_file():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        elif src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)

    variant_src = project_root / "03-kml" / SOURCE_VARIANT
    variant_dest = out_dir / "03-kml" / SOURCE_VARIANT
    if variant_dest.exists():
        shutil.rmtree(variant_dest.parent)
    variant_dest.parent.mkdir(parents=True)
    shutil.copytree(variant_src, variant_dest, ignore=shutil.ignore_patterns(".DS_Store"))

    req = project_root / "requirements.txt"
    if req.is_file():
        shutil.copy2(req, out_dir / "requirements.txt")


def validate_package(package_root: Path, region_ids: list[str], *, require_tiles: bool = True) -> None:
    entry = package_root / ENTRY_KML
    if not entry.is_file():
        raise SystemExit(f"Missing {entry}")
    text = entry.read_text(encoding="utf-8")
    if "02-tiles" in text or "03-kml/" in text:
        raise SystemExit(f"{ENTRY_KML} still references dev paths")

    if require_tiles:
        sample_tile = package_root / "tiles" / region_ids[0]
        if not sample_tile.is_dir():
            raise SystemExit(f"Missing tiles/{region_ids[0]}")

    broken: list[str] = []
    for kml_file in (package_root / "kml").rglob("*.kml"):
        body = kml_file.read_text(encoding="utf-8")
        if "02-tiles" in body:
            broken.append(str(kml_file.relative_to(package_root)))
    if broken:
        raise SystemExit(f"Dev tile paths remain in {broken[0]}")


def write_readme(dest: Path, *, version: str, region_ids: list[str], commander_root: Path) -> None:
    base = load_globe_config(commander_root)
    config = merge_variant_config(base, SOURCE_VARIANT)
    region_lines = []
    for rid in region_ids[:20]:
        layer = layer_by_id(config, rid)
        if layer:
            region_lines.append(f"- {layer.get('label', rid)}")
    if len(region_ids) > 20:
        region_lines.append(f"- … and {len(region_ids) - 20} more regions")

    body = f"""# WoW Commander — player install

Play on the hosted campaign board in **Google Earth Pro**.

**Globe:** {version} · Built {date.today().isoformat()}

---

## Download and play (3 steps)

1. Open **{REPO_URL}**
2. Click **Code → Download ZIP**
3. Unzip the folder, then open **`player/WoW Commander.kml`** in Google Earth Pro

Keep `player/kml/`, `player/tiles/`, and `WoW Commander.kml` together inside the `player/` folder.

**Do not** download **Source code** from old Releases (`player-v3` split zip) — use **Code → Download ZIP** on the main repo page.

## Portal (hosted campaign)

- Getting started: https://wow-commander-campaign.pages.dev/start/
- Table 01: https://wow-commander-campaign.pages.dev/games/table-01/

Campaign markers refresh from the portal (~60s). Right-click **Campaign Board** links → **Refresh** after turns update.

## Optional — Python player menu

Only needed for local setup, sync, or turn export — **not** for viewing the map or hosted portal uploads.

```bash
cd player
python3 -m pip install -r requirements.txt
```

Mac: double-click `scripts/WOW Commander.command`

## Map regions in this pack

{chr(10).join(region_lines)}

---

## Credits

Map imagery via [wow.export](https://github.com/Kruithne/wow.export).
"""
    dest.write_text(body, encoding="utf-8")


def package_commander_player(
    project_root: Path,
    *,
    skip_tiles: bool = False,
) -> dict:
    out_dir = project_root / PLAYER_DIR
    prepare_player_dir(out_dir)
    ensure_commander_globe_assets(project_root)
    region_ids = enabled_region_ids(project_root)

    copy_kml_tree(project_root, out_dir, region_ids)

    entry_src = project_root / "03-kml" / SOURCE_VARIANT / "doc_player.kml"
    if not entry_src.is_file():
        raise SystemExit(f"Missing {entry_src}")
    entry_xml = rewrite_player_entry(entry_src.read_text(encoding="utf-8"))
    (out_dir / ENTRY_KML).write_text(entry_xml, encoding="utf-8")

    tile_count = 0
    if not skip_tiles:
        tile_count = copy_tiles(project_root, out_dir, region_ids)

    copy_scripts_and_config(project_root, out_dir)
    validate_package(out_dir, region_ids, require_tiles=not skip_tiles)

    globe = load_globe_config(project_root)
    version = (globe.get("globe_version") or {}).get("id", "v3")
    write_readme(out_dir / "README.md", version=version, region_ids=region_ids, commander_root=project_root)

    manifest = {
        "package": "wow_commander_player",
        "globe_version": version,
        "github_repo": COMMANDER_REPO,
        "download_url": REPO_URL,
        "entry_kml": f"{PLAYER_DIR}/{ENTRY_KML}",
        "regions": region_ids,
        "region_count": len(region_ids),
        "tile_files": tile_count,
        "packaged_at": date.today().isoformat(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return {"dest": out_dir, "tile_files": tile_count, "region_count": len(region_ids), **manifest}


def main() -> int:
    parser = argparse.ArgumentParser(description="Package Explorer-style player/ folder")
    parser.add_argument("--skip-tiles", action="store_true", help="Skip copying tiles (fast test)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    result = package_commander_player(project_root, skip_tiles=args.skip_tiles)
    print(f"Packaged {result['dest']} ({result['region_count']} regions, {result['tile_files']} tile files)")
    print(f"  Open: player/{ENTRY_KML}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
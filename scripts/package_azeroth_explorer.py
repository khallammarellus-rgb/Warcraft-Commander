#!/usr/bin/env python3
"""
Package Azeroth Explorer — self-contained zip for Google Earth exploration (maps only).

  python3 scripts/package_azeroth_explorer.py
  python3 scripts/package_azeroth_explorer.py --skip-build
  python3 scripts/package_azeroth_explorer.py --out exports/azeroth-explorer-3.0.0.zip
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_kml_superoverlay import merge_variant_config
from explorer_release import github_releases_url, load_explorer_release
from globe_placement import layer_by_id, load_globe_config
from places_hierarchy import opposite_hemisphere_ids, split_pacific_and_opposite
from readme_blocks import README_FOOTER

EXPLORER_DIR = "Azeroth Explorer"
ENTRY_KML = "Azeroth Explorer.kml"
SOURCE_VARIANT = "wowcommanderalpha"
BUILD_VARIANT = "azeroth_explorer"
TILE_REWRITES = (
    ("../../../02-tiles/", "../../tiles/"),
    ("../../02-tiles/", "../tiles/"),
)


def enabled_explorer_region_ids(project_root: Path, release: dict) -> list[str]:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, SOURCE_VARIANT)
    variant_cfg = (base.get("world_variants", {}) or {}).get(SOURCE_VARIANT, {})
    ids = [
        layer["id"]
        for layer in config.get("layers", [])
        if layer.get("enabled")
        and layer.get("layer_type") == "minimap"
        and (layer.get("earth_placement") or layer.get("poster_placement"))
    ]
    opposite = opposite_hemisphere_ids(config)
    if not release.get("include_opposite_hemisphere"):
        ids = [rid for rid in ids if rid not in opposite]
    extra = set(release.get("extra_regions") or [])
    if extra:
        ids = [rid for rid in ids if rid not in opposite or rid in extra]
    return ids


def rewrite_kml_paths(text: str) -> str:
    for old, new in TILE_REWRITES:
        text = text.replace(old, new)
    return text


def rewrite_entry_hrefs(text: str) -> str:
    """Point NetworkLinks at kml/ subtree from package root."""
    text = rewrite_kml_paths(text)

    def repl_href(match: re.Match[str]) -> str:
        href = match.group(1)
        if href.startswith(("http://", "https://")):
            return match.group(0)
        if href.startswith("kml/"):
            return match.group(0)
        return f"<href>kml/{href}</href>"

    return re.sub(r"<href>([^<]+)</href>", repl_href, text)


def build_explorer_kml(project_root: Path) -> Path:
    script = project_root / "scripts" / "build_world_globe.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--kml-only",
            "--variant",
            BUILD_VARIANT,
            "--skip-poster",
        ],
        cwd=project_root,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"build_world_globe failed (exit {result.returncode})")
    return project_root / "03-kml" / SOURCE_VARIANT / "doc_explorer.kml"


def write_readme(dest: Path, release: dict, region_ids: list[str]) -> None:
    base = load_globe_config(dest.parent.parent)
    config = merge_variant_config(base, SOURCE_VARIANT)
    pacific, other = split_pacific_and_opposite(region_ids, config)
    region_lines = []
    for rid in pacific:
        layer = layer_by_id(config, rid)
        if layer:
            region_lines.append(f"- {layer.get('label', rid)}")
    other_lines = []
    for rid in other:
        layer = layer_by_id(config, rid)
        if layer:
            other_lines.append(f"- {layer.get('label', rid)}")

    gh_url = github_releases_url(release)
    updates_line = (
        f"Download the latest zip from GitHub Releases: {gh_url}"
        if gh_url
        else "Download the latest zip from the project GitHub Releases page when available."
    )

    body = f"""# Azeroth Explorer

Fly around World of Warcraft's Azeroth in **Google Earth Pro** — maps only. No wargame markers, no scripts, no live updates.

**Version:** {release.get('explorer_version', '?')} ({release.get('label', '')})  
**Globe:** {release.get('globe_version', '?')} · Built {release.get('released_at', date.today().isoformat())}

---

## Install Google Earth Pro

Download and install **Google Earth Pro** from Google's Earth versions page. Launch it before you open the map below.

## Open this map

1. Unzip the download and **keep the folder structure** — `Azeroth Explorer.kml`, `kml/`, and `tiles/` must stay together.
2. In Google Earth Pro, choose **File → Open**.
3. Select **`Azeroth Explorer.kml`** in this folder.

## Navigate

- Expand **Map layers → Quick View** and double-click **Planet** or a continent name to fly there.
- Zoom with the scroll wheel; drag to pan and rotate the globe.
- Map imagery loads as you zoom in. Wait a moment near each landmass while tiles load.

### Pacific theater (this release)

{chr(10).join(region_lines) if region_lines else '- (see manifest.json)'}

"""
    if other_lines:
        body += f"""
### Other worlds (far side of the globe)

{chr(10).join(other_lines)}
"""
    else:
        body += """
### Other worlds (coming in future releases)

Outland, Draenor, Shadowlands, and other extra-world zones will ship under **Map layers → Other worlds** in a future release.
"""

    body += f"""
---

## Updates

{updates_line}

Replace your old folder with the new unzip, or use a fresh folder each time.

## What this is not

- Not **WoW Commander** — no campaign board, turn export, or live play layer.
- No internet refresh — everything runs from files on your computer.

## Changelog ({release.get('explorer_version', '')})

{release.get('changelog', '')}

See `manifest.json` in this folder for the exact region list in this zip.

{README_FOOTER}
"""
    dest.write_text(body, encoding="utf-8")


def package_explorer(
    project_root: Path,
    *,
    output_zip: Path | None = None,
    skip_build: bool = False,
) -> dict:
    release = load_explorer_release(project_root)
    release = {**release, "released_at": release.get("released_at") or date.today().isoformat()}
    region_ids = enabled_explorer_region_ids(project_root, release)

    if not skip_build:
        build_explorer_kml(project_root)

    source_kml_root = project_root / "03-kml" / SOURCE_VARIANT
    entry_source = source_kml_root / "doc_explorer.kml"
    if not entry_source.exists():
        raise SystemExit(f"Missing {entry_source} — run without --skip-build")

    out_dir = project_root / EXPLORER_DIR
    if out_dir.exists():
        shutil.rmtree(out_dir)
    kml_dest = out_dir / "kml"
    tiles_dest = out_dir / "tiles"
    kml_dest.mkdir(parents=True)
    tiles_dest.mkdir(parents=True)

    skip_names = {"campaign", "doc.kml", "doc_player.kml", "doc_maps.kml", "doc_explorer.kml"}
    for item in source_kml_root.iterdir():
        if item.name in skip_names:
            continue
        dest = kml_dest / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        elif item.suffix.lower() == ".kml":
            text = rewrite_kml_paths(item.read_text(encoding="utf-8"))
            dest.write_text(text, encoding="utf-8")

    for kml_file in kml_dest.rglob("*.kml"):
        text = kml_file.read_text(encoding="utf-8")
        rewritten = rewrite_kml_paths(text)
        if rewritten != text:
            kml_file.write_text(rewritten, encoding="utf-8")

    entry_xml = rewrite_entry_hrefs(entry_source.read_text(encoding="utf-8"))
    (out_dir / ENTRY_KML).write_text(entry_xml, encoding="utf-8")

    tile_count = 0
    tiles_root = project_root / "02-tiles"
    shared_src = tiles_root / "_shared"
    if shared_src.is_dir():
        shutil.copytree(shared_src, tiles_dest / "_shared")
        tile_count += sum(1 for _ in (tiles_dest / "_shared").rglob("*") if _.is_file())
    for region_id in region_ids:
        src_tiles = tiles_root / region_id
        if src_tiles.is_dir():
            shutil.copytree(src_tiles, tiles_dest / region_id)
            tile_count += sum(1 for _ in (tiles_dest / region_id).rglob("*") if _.is_file())

    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                **release,
                "regions": region_ids,
                "region_count": len(region_ids),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    write_readme(out_dir / "README.md", release, region_ids)

    version = release.get("explorer_version", "0.0.0")
    zip_path = output_zip or (
        project_root / "exports" / f"azeroth-explorer-{version}.zip"
    )
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                arcname = path.relative_to(out_dir).as_posix()
                zf.write(path, arcname)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    return {
        "zip": zip_path,
        "explorer_dir": out_dir,
        "region_count": len(region_ids),
        "tile_files": tile_count,
        "size_mb": round(size_mb, 1),
        "version": version,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Package Azeroth Explorer zip")
    parser.add_argument("--out", type=Path, default=None, help="Output zip path")
    parser.add_argument("--skip-build", action="store_true", help="Use existing doc_explorer.kml")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    result = package_explorer(
        project_root,
        output_zip=args.out,
        skip_build=args.skip_build,
    )
    print(f"Packaged {result['version']} → {result['zip']}")
    print(f"  Regions: {result['region_count']} · Tile files: {result['tile_files']}")
    print(f"  Size: {result['size_mb']} MB")
    print(f"  Folder: {result['explorer_dir']}")
    print("Upload the zip to GitHub Releases when ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
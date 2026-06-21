#!/usr/bin/env python3
"""
Package Azeroth Explorer — self-contained zips for Google Earth exploration (maps only).

  python3 scripts/package_azeroth_explorer.py
  python3 scripts/package_azeroth_explorer.py --skip-build
  python3 scripts/package_azeroth_explorer.py --single-zip   # legacy one-file package
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
PACKAGE_ROOT_FILES = (ENTRY_KML, "README.md", "manifest.json")
PACKAGE_DIRS = ("kml", "tiles")
SHARED_KML_FILES = frozenset({"terrain_underlay.kml", "pacific_vignette.kml"})
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


def explorer_project_dir(commander_root: Path) -> Path | None:
    cfg_path = commander_root / "config" / "explorer_project.json"
    if not cfg_path.is_file():
        return None
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    return (commander_root / cfg["path"]).resolve()


def prepare_package_dir(out_dir: Path) -> None:
    """Clear only map package contents — preserve .git, config/, docs/, exports/."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in (*PACKAGE_ROOT_FILES, *PACKAGE_DIRS):
        path = out_dir / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()


def ensure_commander_globe_assets(project_root: Path) -> None:
    """Ensure Commander has shared underlay + vignette before copying tiles."""
    base = load_globe_config(project_root)
    config = merge_variant_config(base, SOURCE_VARIANT)
    shared = project_root / "02-tiles" / "_shared"
    underlay = shared / "terrain_underlay.png"
    vignette = shared / "pacific_vignette.png"

    if not underlay.is_file() and (config.get("terrain_underlay") or {}).get("enabled"):
        from build_terrain_underlay import build_terrain_underlay

        print("Building terrain underlay in Commander 02-tiles/_shared/ ...")
        build_terrain_underlay(project_root, config, variant=SOURCE_VARIANT)

    if not vignette.is_file():
        script = project_root / "scripts" / "build_pacific_vignette.py"
        print("Building Pacific vignette in Commander 02-tiles/_shared/ ...")
        subprocess.run(
            [sys.executable, str(script), "--variant", SOURCE_VARIANT],
            cwd=project_root,
            check=True,
        )

    missing = [p.name for p in (underlay, vignette) if not p.is_file()]
    if missing:
        raise SystemExit(f"Missing shared globe assets in 02-tiles/_shared/: {', '.join(missing)}")


def validate_standalone_package(package_root: Path, region_ids: list[str]) -> None:
    """Explorer must work when downloaded alone from GitHub — no Commander paths."""
    allowed = set(region_ids) | {"terrain_underlay", "pacific_vignette"}
    missing: list[str] = []
    forbidden: list[str] = []

    for kml_file in (package_root / "kml").rglob("*.kml"):
        region = kml_file.relative_to(package_root / "kml").parts[0].replace(".kml", "")
        if region not in allowed:
            forbidden.append(f"unexpected KML: {kml_file.relative_to(package_root)}")
            continue
        text = kml_file.read_text(encoding="utf-8")
        if "02-tiles" in text:
            forbidden.append(f"Commander tile path in {kml_file.relative_to(package_root)}")
        for match in re.finditer(r"<href>([^<]+\.png)</href>", text):
            href = match.group(1).strip()
            if href.startswith(("http://", "https://")):
                continue
            if href.startswith("tiles/"):
                forbidden.append(
                    f"{kml_file.relative_to(package_root)}: {href} (must be relative to this KML file)"
                )
                continue
            target = (kml_file.parent / href).resolve()
            if not target.is_file():
                missing.append(f"{kml_file.relative_to(package_root)}: {href}")

    if forbidden:
        sample = "\n  ".join(forbidden[:8])
        raise SystemExit(f"Explorer package is not standalone-safe ({len(forbidden)}):\n  {sample}")
    if missing:
        sample = "\n  ".join(missing[:8])
        raise SystemExit(f"Broken tile hrefs in package ({len(missing)}):\n  {sample}")


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


def write_readme(
    dest: Path, release: dict, region_ids: list[str], *, commander_root: Path
) -> None:
    base = load_globe_config(commander_root)
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

    repo = (release.get("github_repo") or "").strip()
    gh_url = github_releases_url(release)
    repo_url = f"https://github.com/{repo}" if repo else gh_url
    updates_line = (
        f"Get updates from {repo_url}"
        if repo_url
        else "Check the project GitHub page for updates."
    )

    version = release.get("explorer_version", "?")
    body = f"""# Azeroth Explorer

Fly around World of Warcraft's Azeroth in **Google Earth Pro** — maps only. No wargame markers, no scripts, no live updates.

**Version:** {version} ({release.get('label', '')})  
**Globe:** {release.get('globe_version', '?')} · Built {release.get('released_at', date.today().isoformat())}

---

## Download

This repo is a **standalone map** — you do not need WoW Commander.

1. Open **{repo_url or 'the GitHub repo'}**
2. Click **Code → Download ZIP**
3. Unzip the folder (e.g. `Azeroth-Explorer-main`)
4. Inside that folder, keep these together: `Azeroth Explorer.kml`, `kml/`, `tiles/`

Optional: on **Releases**, you can also download **`Azeroth-Explorer-{version}-MAP.zip`** if you prefer one archive.

## Install Google Earth Pro

Download and install **Google Earth Pro** from Google's Earth versions page. Launch it before you open the map below.

## Open this map

1. In Google Earth Pro, choose **File → Open**
2. Select **`Azeroth Explorer.kml`** from inside the unzipped folder
3. Do not move `Azeroth Explorer.kml` away from `kml/` and `tiles/`

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


DEFAULT_SPLIT_MB = 25


def split_zip_for_upload(zip_path: Path, part_mb: int) -> list[Path]:
    """Split a zip into upload-sized parts (macOS/Linux zip -s)."""
    parts_dir = zip_path.parent / f"{zip_path.stem}-parts"
    if parts_dir.exists():
        shutil.rmtree(parts_dir)
    parts_dir.mkdir(parents=True)
    split_base = parts_dir / zip_path.name
    subprocess.run(
        ["zip", "-s", f"{part_mb}m", str(zip_path), "--out", str(split_base)],
        check=True,
    )
    parts = sorted(parts_dir.glob(f"{zip_path.stem}*"))
    join_txt = parts_dir / "HOW_TO_JOIN.txt"
    download_txt = parts_dir / "DOWNLOAD.txt"
    download_txt.write_text(
        f"""Azeroth Explorer — what to download from GitHub

DO NOT download "Source code (zip)" or "Source code (tar.gz)".
Those are GitHub's automatic project snapshots (scripts, portal, etc.).

DO download every file under ASSETS on the release page:
  {zip_path.name}
  {zip_path.stem}.z01, .z02, .z03, ... (all parts)
  HOW_TO_JOIN.txt

Then follow HOW_TO_JOIN.txt to join and unzip the map.
""",
        encoding="utf-8",
    )
    join_txt.write_text(
        f"""Azeroth Explorer — join split zip parts

Download every ASSET from the GitHub release (not "Source code"):
  {zip_path.name}
  {zip_path.stem}.z01, .z02, .z03, ... (all parts)

Put them in one folder, then:

Mac Terminal (from that folder):
  zip -FF {zip_path.name} --out {zip_path.stem}-joined.zip
  unzip {zip_path.stem}-joined.zip

Windows (7-Zip):
  Select all part files → 7-Zip → Extract Here

Open Azeroth Explorer.kml from the unzipped folder in Google Earth Pro.
Keep Azeroth Explorer.kml, kml/, and tiles/ together.
""",
        encoding="utf-8",
    )
    return parts + [join_txt, download_txt]


def package_explorer(
    project_root: Path,
    *,
    output_zip: Path | None = None,
    package_dir: Path | None = None,
    skip_build: bool = False,
    split_mb: int | None = None,
    skip_zip: bool = False,
) -> dict:
    release = load_explorer_release(project_root)
    release = {**release, "released_at": release.get("released_at") or date.today().isoformat()}
    region_ids = enabled_explorer_region_ids(project_root, release)

    ensure_commander_globe_assets(project_root)

    if not skip_build:
        build_explorer_kml(project_root)

    source_kml_root = project_root / "03-kml" / SOURCE_VARIANT
    entry_source = source_kml_root / "doc_explorer.kml"
    if not entry_source.exists():
        raise SystemExit(f"Missing {entry_source} — run without --skip-build")

    out_dir = package_dir or (project_root / EXPLORER_DIR)
    prepare_package_dir(out_dir)
    kml_dest = out_dir / "kml"
    tiles_dest = out_dir / "tiles"
    kml_dest.mkdir(parents=True)
    tiles_dest.mkdir(parents=True)

    skip_names = {"campaign", "doc.kml", "doc_player.kml", "doc_maps.kml", "doc_explorer.kml"}
    allowed_regions = set(region_ids)
    for item in source_kml_root.iterdir():
        if item.name in skip_names:
            continue
        if item.is_dir():
            if item.name not in allowed_regions:
                continue
            shutil.copytree(item, kml_dest / item.name)
        elif item.suffix.lower() == ".kml" and item.name in SHARED_KML_FILES:
            text = rewrite_kml_paths(item.read_text(encoding="utf-8"))
            (kml_dest / item.name).write_text(text, encoding="utf-8")

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
    if not shared_src.is_dir():
        raise SystemExit(f"Missing {shared_src} — run build_terrain_underlay.py")
    shutil.copytree(shared_src, tiles_dest / "_shared")
    tile_count += sum(1 for _ in (tiles_dest / "_shared").rglob("*") if _.is_file())
    for region_id in region_ids:
        src_tiles = tiles_root / region_id
        if not src_tiles.is_dir():
            raise SystemExit(f"Missing Commander tiles for {region_id}: {src_tiles}")
        shutil.copytree(src_tiles, tiles_dest / region_id)
        tile_count += sum(1 for _ in (tiles_dest / region_id).rglob("*") if _.is_file())

    version = release.get("explorer_version", "0.0.0")
    exports_dir = project_root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    release_zip_name = f"Azeroth-Explorer-{version}-MAP.zip"
    zip_path = output_zip or exports_dir / release_zip_name
    for stale in exports_dir.glob(f"azeroth-explorer-{version}-kml.zip"):
        stale.unlink()
    for stale in exports_dir.glob(f"azeroth-explorer-{version}-tiles.zip"):
        stale.unlink()

    write_readme(out_dir / "README.md", release, region_ids, commander_root=project_root)
    validate_standalone_package(out_dir, region_ids)

    size_mb = 0.0
    split_parts: list[Path] = []
    if skip_zip:
        zip_path = output_zip or exports_dir / release_zip_name
    else:
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(out_dir.rglob("*")):
                if path.is_file():
                    arcname = path.relative_to(out_dir).as_posix()
                    zf.write(path, arcname)
        size_mb = zip_path.stat().st_size / (1024 * 1024)
        if split_mb:
            split_parts = split_zip_for_upload(zip_path, split_mb)

    (out_dir / "manifest.json").write_text(
        json.dumps(
            {
                **release,
                "regions": region_ids,
                "region_count": len(region_ids),
                "package_layout": "single_zip" if not split_mb else "split_parts",
                "split_mb": split_mb,
                "full_zip": zip_path.name,
                "tile_files": tile_count,
                "part_count": len([p for p in split_parts if p.suffix != ".txt"]),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "zip": zip_path,
        "parts_dir": zip_path.parent / f"{zip_path.stem}-parts" if split_mb else None,
        "explorer_dir": out_dir,
        "region_count": len(region_ids),
        "tile_files": tile_count,
        "size_mb": round(size_mb, 1),
        "version": version,
        "split_parts": split_parts,
        "split_mb": split_mb,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Package Azeroth Explorer zip")
    parser.add_argument("--out", type=Path, default=None, help="Output zip path")
    parser.add_argument("--skip-build", action="store_true", help="Use existing doc_explorer.kml")
    parser.add_argument(
        "--to-explorer",
        action="store_true",
        help="Write package directly into ../Azeroth Explorer Project",
    )
    parser.add_argument(
        "--split-mb",
        type=int,
        default=None,
        metavar="N",
        help=f"Optional: split into N-MB parts for hosts with tiny upload limits",
    )
    args = parser.parse_args()

    split_mb = None if not args.split_mb or args.split_mb == 0 else args.split_mb

    project_root = Path(__file__).resolve().parent.parent
    package_dir = explorer_project_dir(project_root) if args.to_explorer else None
    result = package_explorer(
        project_root,
        output_zip=args.out,
        package_dir=package_dir,
        skip_build=args.skip_build,
        split_mb=split_mb,
    )
    print(f"Packaged {result['version']}")
    print(f"  Regions: {result['region_count']} · Tile files: {result['tile_files']}")
    print(f"  Underlay: tiles/_shared/terrain_underlay.png")
    print(f"  Vignette: tiles/_shared/pacific_vignette.png")
    print(f"  Full zip: {result['zip']} ({result['size_mb']} MB)")
    print(f"  Folder: {result['explorer_dir']}")
    if result.get("split_parts"):
        print(f"  Upload parts: {len(result['split_parts'])} files in {result['parts_dir']}")
    else:
        print("  Upload this ONE file to GitHub Releases → Attach binaries.")
        print("  Ignore Source code (zip) on the release page — GitHub adds that automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
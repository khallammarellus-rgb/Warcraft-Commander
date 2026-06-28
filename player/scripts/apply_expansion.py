#!/usr/bin/env python3
"""
Install an expansion pack zip into a WoW Commander or Explorer install.

  python3 scripts/apply_expansion.py --zip exports/wowcommander-expansion-subterranean-2026-06-27.zip
  python3 scripts/apply_expansion.py --zip pack.zip --install-root ~/Games/WoWCommander
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from expansions import load_expansions_config, pack_install_dir
from player_install.core import detect_install_root, resolve_paths


def load_manifest_from_zip(zf: zipfile.ZipFile) -> dict:
    try:
        raw = zf.read("expansion_manifest.json").decode("utf-8")
        return json.loads(raw)
    except KeyError:
        raise SystemExit("Zip missing expansion_manifest.json — use package_expansion.py output")


def resolve_tiles_dest(install_root: Path, paths: dict) -> Path:
    if paths["tiles"].is_dir():
        return paths["tiles"]
    play = paths["play_root"]
    candidate = play / "tiles"
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def resolve_kml_dest(install_root: Path, paths: dict) -> Path:
    if (paths["play_root"] / "kml").is_dir():
        return paths["play_root"] / "kml"
    if paths["kml"].is_dir():
        return paths["kml"]
    dest = paths["play_root"] / "kml"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def update_installed_manifest(
    install_root: Path,
    expansions_cfg: dict,
    pack_id: str,
    layer_ids: list[str],
    zip_name: str,
) -> Path:
    rel = expansions_cfg.get("manifest_file", "expansions_installed.json")
    path = install_root / rel
    data = {"packs": {}, "updated_at": date.today().isoformat()}
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("packs", {})[pack_id] = {
        "layers": layer_ids,
        "source_zip": zip_name,
        "installed_at": date.today().isoformat(),
    }
    data["updated_at"] = date.today().isoformat()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def extract_pack(
    zip_path: Path,
    install_root: Path,
    *,
    also_archive: bool = True,
) -> dict:
    expansions_cfg = load_expansions_config(install_root)
    paths = resolve_paths(install_root)

    with zipfile.ZipFile(zip_path, "r") as zf:
        manifest = load_manifest_from_zip(zf)
        pack_id = manifest.get("pack_id", "unknown")
        layer_ids = list(manifest.get("layers") or [])

        pack_dir = pack_install_dir(install_root, pack_id, expansions_cfg)
        if also_archive and pack_dir.exists():
            shutil.rmtree(pack_dir)
        pack_dir.mkdir(parents=True, exist_ok=True)

        tiles_dest = resolve_tiles_dest(install_root, paths)
        kml_dest = resolve_kml_dest(install_root, paths)

        copied_tiles = 0
        copied_kml = 0
        for member in zf.namelist():
            if member.endswith("/"):
                continue
            target: Path | None = None
            if member.startswith("tiles/"):
                rel = Path(member).relative_to("tiles")
                target = tiles_dest / rel
                copied_tiles += 1
            elif member.startswith("kml/"):
                rel = Path(member).relative_to("kml")
                target = kml_dest / rel
                copied_kml += 1
            elif member in ("expansion_manifest.json", "README.txt"):
                target = pack_dir / Path(member).name
            if target is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)

        manifest_path = update_installed_manifest(
            install_root,
            expansions_cfg,
            pack_id,
            layer_ids,
            zip_path.name,
        )

    return {
        "pack_id": pack_id,
        "layers": layer_ids,
        "tiles_dest": str(tiles_dest),
        "kml_dest": str(kml_dest),
        "pack_dir": str(pack_dir),
        "manifest_path": str(manifest_path),
        "copied_tiles": copied_tiles,
        "copied_kml": copied_kml,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply expansion pack zip to local install")
    parser.add_argument("--zip", type=Path, required=True, help="Expansion zip from package_expansion.py")
    parser.add_argument("--install-root", type=Path, help="WoW Commander install folder")
    args = parser.parse_args()

    zip_path = args.zip.resolve()
    if not zip_path.is_file():
        raise SystemExit(f"Zip not found: {zip_path}")

    install_root = args.install_root
    if install_root:
        install_root = install_root.resolve()
    else:
        install_root = detect_install_root(Path.cwd())
    if not install_root:
        raise SystemExit("No install detected — pass --install-root")

    result = extract_pack(zip_path, install_root)
    print(f"Installed pack: {result['pack_id']}")
    print(f"  Layers: {', '.join(result['layers'])}")
    print(f"  Tiles → {result['tiles_dest']}")
    print(f"  KML → {result['kml_dest']}")
    print(f"  Manifest: {result['manifest_path']}")
    print("\nRebuild KML if needed: python3 scripts/build_world_globe.py --kml-only")
    return 0


if __name__ "__main__":
    raise SystemExit(main())
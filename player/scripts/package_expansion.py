#!/usr/bin/env python3
"""
Package optional expansion zips for WoW Commander and Azeroth Explorer.

  python3 scripts/package_expansion.py
  python3 scripts/package_expansion.py --pack subterranean
  python3 scripts/package_expansion.py --pack other_worlds --explorer
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

from expansions import load_expansions_config, pack_layer_ids
from globe_placement import layer_by_id, load_globe_config

SOURCE_VARIANT = "wowcommanderalpha"
KML_VARIANT_DIR = "wowcommanderalpha"


def layer_has_built_tiles(project_root: Path, layer_id: str) -> bool:
    tiles = project_root / "02-tiles" / layer_id
    return tiles.is_dir() and any(tiles.rglob("*.png"))


def layer_has_built_kml(project_root: Path, layer_id: str) -> bool:
    for name in ("overview.kml", "detail.kml"):
        if (project_root / "03-kml" / layer_id / name).is_file():
            return True
    return any((project_root / "03-kml" / layer_id).glob("overview_*.kml"))


def collect_pack_layers(project_root: Path, pack: dict) -> list[str]:
    config = load_globe_config(project_root)
    candidates = pack_layer_ids(project_root, pack, config)
    built: list[str] = []
    for layer_id in candidates:
        if layer_has_built_tiles(project_root, layer_id):
            built.append(layer_id)
            continue
        layer = layer_by_id(config, layer_id)
        if layer and layer.get("enabled") and layer_has_built_kml(project_root, layer_id):
            built.append(layer_id)
    return built


def add_tree_to_zip(zf: zipfile.ZipFile, source: Path, arc_prefix: str) -> int:
    count = 0
    if not source.exists():
        return 0
    for path in source.rglob("*"):
        if not path.is_file() or ".DS_Store" in path.name:
            continue
        arcname = f"{arc_prefix}/{path.relative_to(source).as_posix()}"
        zf.write(path, arcname)
        count += 1
    return count


def package_one(
    project_root: Path,
    pack_id: str,
    pack: dict,
    *,
    explorer: bool,
    out_dir: Path,
) -> Path | None:
    layer_ids = collect_pack_layers(project_root, pack)
    if not layer_ids:
        print(f"  [!] {pack_id}: no built layers — run build_world_globe.py for expansion zones first")
        return None

    prefix = pack.get("zip_prefix", f"expansion-{pack_id}")
    target_name = f"{prefix}-{date.today().isoformat()}.zip"
    if explorer:
        target_name = target_name.replace("wowcommander-", "azeroth-explorer-")
    output = out_dir / target_name
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "pack_id": pack_id,
        "label": pack.get("label", pack_id),
        "packaged_at": date.today().isoformat(),
        "target": "azeroth_explorer" if explorer else "wowcommander",
        "layers": layer_ids,
    }

    tiles_root = project_root / "02-tiles"
    kml_root = project_root / "03-kml"
    variant_kml = kml_root / KML_VARIANT_DIR

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for layer_id in layer_ids:
            add_tree_to_zip(zf, tiles_root / layer_id, f"tiles/{layer_id}")
            add_tree_to_zip(zf, kml_root / layer_id, f"kml/{layer_id}")
        zf.writestr("expansion_manifest.json", json.dumps(manifest, indent=2) + "\n")
        readme = (
            f"{pack.get('label', pack_id)} expansion pack\n"
            f"Layers: {', '.join(layer_ids)}\n\n"
            "Apply with: python3 scripts/apply_expansion.py --zip <this-file>\n"
        )
        zf.writestr("README.txt", readme)

    print(f"  {pack_id}: {output.name} ({len(layer_ids)} layer(s), {explorer and 'explorer' or 'commander'})")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Package Subterranean / Other Worlds expansion zips")
    parser.add_argument("--pack", choices=("subterranean", "other_worlds"), help="Single pack (default: all)")
    parser.add_argument("--explorer", action="store_true", help="Also build Azeroth Explorer layout zips")
    parser.add_argument("--out", type=Path, help="Output directory (default: exports/)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    out_dir = args.out or (project_root / "exports")
    expansions_cfg = load_expansions_config(project_root)
    packs = expansions_cfg.get("packs", {})

    pack_ids = [args.pack] if args.pack else list(packs.keys())
    outputs: list[Path] = []
    for pack_id in pack_ids:
        pack = packs.get(pack_id)
        if not pack:
            print(f"Unknown pack: {pack_id}")
            continue
        path = package_one(project_root, pack_id, pack, explorer=False, out_dir=out_dir)
        if path:
            outputs.append(path)
        if args.explorer:
            path = package_one(project_root, pack_id, pack, explorer=True, out_dir=out_dir)
            if path:
                outputs.append(path)

    if not outputs:
        return 1
    print(f"\nPackaged {len(outputs)} expansion zip(s) → {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
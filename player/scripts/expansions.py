#!/usr/bin/env python3
"""Expansion pack manifest, layer resolution, and install detection."""

from __future__ import annotations

import json
from pathlib import Path

from globe_placement import layer_by_id, load_globe_config
from places_hierarchy import opposite_hemisphere_ids


def load_expansions_config(project_root: Path) -> dict:
    path = project_root / "config" / "expansions.json"
    if not path.is_file():
        return {"packs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def load_installed_manifest(install_root: Path, expansions_cfg: dict) -> dict:
    rel = expansions_cfg.get("manifest_file", "expansions_installed.json")
    path = install_root / rel
    if not path.is_file():
        return {"packs": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def pack_layer_ids(project_root: Path, pack: dict, config: dict | None = None) -> list[str]:
    config = config or load_globe_config(project_root)
    if pack.get("layer_type") == "subterranean":
        return [
            layer["id"]
            for layer in config.get("layers", [])
            if layer.get("layer_type") == "subterranean" and layer.get("id")
        ]
    if pack.get("hemisphere") == "opposite":
        return sorted(opposite_hemisphere_ids(config))
    return list(pack.get("layer_ids") or [])


def layer_has_tiles(install_root: Path, layer_id: str) -> bool:
    for tiles_root in (
        install_root / "tiles" / layer_id,
        install_root / "02-tiles" / layer_id,
        install_root / "player" / "tiles" / layer_id,
    ):
        if (tiles_root / "0").is_dir() or any(tiles_root.rglob("*.png")):
            return True
    return False


def pack_install_dir(install_root: Path, pack_id: str, expansions_cfg: dict) -> Path:
    root_name = expansions_cfg.get("install_root", "expansions")
    return install_root / root_name / pack_id


def scan_pack_status(
    install_root: Path,
    project_root: Path | None = None,
) -> list[dict]:
    """Return per-pack installed/missing layer summary for wizard UI."""
    project_root = project_root or install_root
    expansions_cfg = load_expansions_config(project_root)
    installed = load_installed_manifest(install_root, expansions_cfg)
    config = load_globe_config(project_root)
    results: list[dict] = []

    for pack_id, pack in (expansions_cfg.get("packs") or {}).items():
        layer_ids = pack_layer_ids(project_root, pack, config)
        pack_dir = pack_install_dir(install_root, pack_id, expansions_cfg)
        manifest_layers = set((installed.get("packs") or {}).get(pack_id, {}).get("layers", []))
        present: list[str] = []
        missing: list[str] = []
        for layer_id in layer_ids:
            layer = layer_by_id(config, layer_id)
            if not layer:
                continue
            in_manifest = layer_id in manifest_layers
            has_tiles = layer_has_tiles(install_root, layer_id)
            in_pack_dir = (pack_dir / "tiles" / layer_id).is_dir()
            if in_manifest or has_tiles or in_pack_dir:
                present.append(layer_id)
            else:
                missing.append(layer_id)
        results.append(
            {
                "id": pack_id,
                "label": pack.get("label", pack_id),
                "description": pack.get("description", ""),
                "pack_dir": pack_dir,
                "pack_dir_exists": pack_dir.is_dir(),
                "layers_total": len(layer_ids),
                "layers_present": len(present),
                "layers_missing": len(missing),
                "installed": len(missing) == 0 and len(present) > 0,
                "partial": 0 < len(present) < len(layer_ids),
                "missing_ids": missing,
                "present_ids": present,
            }
        )
    return results
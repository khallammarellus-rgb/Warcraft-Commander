#!/usr/bin/env python3
"""
Build optimized icon assets + manifest for the hosted icon builder.

  python3 scripts/build_icon_library.py
  python3 scripts/build_icon_library.py --source ~/Downloads/icons

Outputs:
  portal/public/tools/icon-builder/assets/
  portal/public/tools/icon-builder/assets/icon_manifest.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path.home() / "Downloads" / "icons"
OUT_DIR = PROJECT_ROOT / "portal" / "public" / "tools" / "icon-builder" / "assets"
MAX_PX = 512
ARTBOARD = 512

# 4×3 class icon grid in class icons.jpg (570×749).
# Mapped by matching each tile's silhouette to official WoW class iconography.
CLASS_GRID = [
    ["paladin", "mage", "rogue"],
    ["druid", "hunter", "warlock"],
    ["monk", "priest", "evoker"],
    ["demon_hunter", "death_knight", "warrior"],
]

SOURCE_FOLDERS: dict[str, tuple[str, bool, str | None]] = {
    "Colorless Unit Shapes": ("shapes", True, "shape"),
    "Identifiers": ("identifiers", True, "border"),
    "Unit Add Ons": ("addons", True, "fill"),
    "Custom Features": ("custom_features", True, "border"),
    "Tactical Ops Graphics": ("tactical_ops", False, None),
}

# Per-addon tint overrides (default folder mode is solid fill).
ADDON_TINT_OVERRIDES: dict[str, str] = {
    "mercenary": "shape_preserve_white",
    "hq_flag_add_on": "shape",
    "text_banner_add_on": "shape",
}
TEXT_EDITABLE_ASSETS = {"text_banner_add_on"}

# Shape picker order (remainder sorted by label).
SHAPE_SORT_PRIORITY = ["friendly_generic_rectangle", "enemy_generic_diamond", "triangle", "circle"]

# MIL-STD-2525 friendly frame fill used throughout wargaming-and-briefing-graphics.pptx.
PPTX_FRIENDLY_FILL = "#80ffff"


def _slug(name: str) -> str:
    s = name.lower()
    s = re.sub(r"^colorless\s+", "", s)
    s = re.sub(r"^(identifier|add on|custom),?\s*", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "asset"


def _label_from_filename(name: str) -> str:
    base = Path(name).stem
    for prefix in ("Colorless ", "Identifier, ", "Add on, ", "Custom, "):
        if base.startswith(prefix):
            base = base[len(prefix) :]
    return base.strip()


def _trim_and_resize(im: Image.Image, max_px: int) -> Image.Image:
    im = im.convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)
    w, h = im.size
    if max(w, h) > max_px:
        scale = max_px / max(w, h)
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    return im


def _save_png(im: Image.Image, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, format="PNG", optimize=True)


def _asset_entry(
    *,
    category: str,
    asset_id: str,
    label: str,
    rel_file: str,
    tintable: bool,
    tint_mode: str | None,
    width: int,
    height: int,
    tags: list[str] | None = None,
    text_editable: bool = False,
) -> dict:
    scale = min(1.0, (ARTBOARD * 0.75) / max(width, height, 1))
    entry = {
        "id": asset_id,
        "label": label,
        "file": rel_file,
        "category": category,
        "tintable": tintable,
        "width": width,
        "height": height,
        "default": {
            "x": ARTBOARD // 2,
            "y": ARTBOARD // 2 + 20,
            "scale": round(scale, 3),
            "rotation": 0,
        },
        "tags": tags or [],
    }
    if tintable and tint_mode:
        entry["tint_mode"] = tint_mode
    if text_editable:
        entry["text_editable"] = True
    return entry


def _sort_shape_entries(entries: list[dict]) -> None:
    priority = {asset_id: idx for idx, asset_id in enumerate(SHAPE_SORT_PRIORITY)}
    entries.sort(key=lambda e: (priority.get(e["id"], 999), e["label"].lower()))


def _class_icon_to_white_mask(im: Image.Image, *, bg_threshold: int = 36) -> Image.Image:
    """Drop black cell background; keep icon as a white alpha mask for tinting."""
    im = im.convert("RGBA")
    px = im.load()
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out_px = out.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a < 12:
                continue
            lum = (r + g + b) / 3
            if lum < bg_threshold:
                continue
            alpha = int(min(255, max(0, (lum - bg_threshold) / (255 - bg_threshold) * a)))
            if alpha < 8:
                continue
            out_px[x, y] = (255, 255, 255, alpha)
    return _trim_and_resize(out, 128)


def _ingest_folder(
    source: Path,
    folder_name: str,
    out_category: str,
    tintable: bool,
    tint_mode: str | None,
    manifest_key: str,
    entries: dict[str, list],
) -> None:
    src_dir = source / folder_name
    if not src_dir.is_dir():
        print(f"Skip missing folder: {src_dir}")
        return
    for src in sorted(src_dir.glob("*.png")):
        im = Image.open(src)
        im = _trim_and_resize(im, MAX_PX)
        asset_id = _slug(src.stem)
        entry_tint_mode = tint_mode
        if manifest_key == "addons" and asset_id in ADDON_TINT_OVERRIDES:
            entry_tint_mode = ADDON_TINT_OVERRIDES[asset_id]
        rel = f"{out_category}/{asset_id}.png"
        dest = OUT_DIR / rel
        _save_png(im, dest)
        entries[manifest_key].append(
            _asset_entry(
                category=manifest_key,
                asset_id=asset_id,
                label=_label_from_filename(src.name),
                rel_file=rel,
                tintable=tintable,
                tint_mode=entry_tint_mode,
                width=im.width,
                height=im.height,
                text_editable=asset_id in TEXT_EDITABLE_ASSETS,
            )
        )


def _slice_class_icons(source: Path, entries: dict[str, list]) -> None:
    jpg = source / "class icons.jpg"
    if not jpg.is_file():
        print(f"Skip class sheet: {jpg}")
        return
    im = Image.open(jpg).convert("RGBA")
    cols, rows = 3, 4
    cw, ch = im.width // cols, im.height // rows
    # Display labels in the builder (asset id → picker name).
    labels = {
        "warrior": "Monk",
        "mage": "Mage",
        "paladin": "Warrior",
        "druid": "Druid",
        "warlock": "Shaman",
        "death_knight": "Demon Hunter",
        "monk": "Priest",
        "priest": "Warlock",
        "evoker": "Paladin",
        "demon_hunter": "Death Knight",
        "rogue": "Rogue",
        "hunter": "Hunter",
    }
    for r in range(rows):
        for c in range(cols):
            class_id = CLASS_GRID[r][c]
            box = (c * cw, r * ch, (c + 1) * cw, (r + 1) * ch)
            tile = im.crop(box)
            tile = _class_icon_to_white_mask(tile)
            rel = f"classes/{class_id}.png"
            dest = OUT_DIR / rel
            _save_png(tile, dest)
            entry = _asset_entry(
                category="classes",
                asset_id=class_id,
                label=labels.get(class_id, class_id.replace("_", " ").title()),
                rel_file=rel,
                tintable=True,
                tint_mode="border",
                width=tile.width,
                height=tile.height,
                tags=["wow_class"],
            )
            entry["default"] = {
                "x": ARTBOARD - 90,
                "y": 90,
                "scale": 0.55,
                "rotation": 0,
            }
            entries["classes"].append(entry)


def _ingest_pptx_curated(project_root: Path, entries: dict[str, list]) -> None:
    allow_path = project_root / "config" / "icon_builder_allowlist.json"
    raw_dir = project_root / "assets" / "icon_library" / "source" / "pptx_raw"
    if not allow_path.is_file() or not raw_dir.is_dir():
        return
    allow = json.loads(allow_path.read_text(encoding="utf-8"))
    include = allow.get("include") or []
    if not include:
        return
    for name in include:
        src = raw_dir / name
        if not src.is_file():
            print(f"Allowlisted pptx image missing: {src}")
            continue
        try:
            im = Image.open(src)
        except OSError:
            print(f"Unreadable: {src}")
            continue
        im = _trim_and_resize(im, MAX_PX)
        asset_id = _slug(Path(name).stem)
        rel = f"pptx/{asset_id}.png"
        _save_png(im, OUT_DIR / rel)
        entries["pptx_curated"].append(
            _asset_entry(
                category="pptx_curated",
                asset_id=asset_id,
                label=_label_from_filename(name),
                rel_file=rel,
                tintable=False,
                tint_mode=None,
                width=im.width,
                height=im.height,
                tags=["briefing_graphic"],
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build icon builder web assets")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()

    if not args.source.is_dir():
        print(f"Source not found: {args.source}")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    entries: dict[str, list] = {
        "shapes": [],
        "identifiers": [],
        "addons": [],
        "custom_features": [],
        "classes": [],
        "tactical_ops": [],
        "pptx_curated": [],
    }

    for folder_name, (out_cat, tintable, tint_mode) in SOURCE_FOLDERS.items():
        _ingest_folder(args.source, folder_name, out_cat, tintable, tint_mode, out_cat, entries)

    _slice_class_icons(args.source, entries)
    _ingest_pptx_curated(PROJECT_ROOT, entries)
    _sort_shape_entries(entries["shapes"])

    manifest = {
        "version": 1,
        "artboard": ARTBOARD,
        "export_sizes": [64, 128, 256],
        "player_custom_icons_path": "assets/player_custom_icons/",
        "defaults": {
            "fill": PPTX_FRIENDLY_FILL,
            "border": "#000000",
            "shape_id": "friendly_generic_rectangle",
            "identifier_id": "infantry",
        },
        **entries,
    }

    manifest_path = OUT_DIR / "icon_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    total_assets = sum(len(v) for v in entries.values())
    total_bytes = sum(f.stat().st_size for f in OUT_DIR.rglob("*.png"))
    print(f"Wrote {total_assets} assets ({total_bytes / 1024 / 1024:.2f} MB) → {OUT_DIR}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
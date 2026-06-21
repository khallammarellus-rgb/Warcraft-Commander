#!/usr/bin/env python3
"""Open doc.kml + campaign_live.kml in Google Earth Pro for editable marker placement."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_world_globe import resolve_campaign_region_ids
from globe_placement import layer_by_id, load_globe_config
from build_kml_superoverlay import merge_variant_config
from campaign_live_io import resolve_campaign_live_path
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open doc.kml + campaign_live.kml for editable campaign folders"
    )
    parser.add_argument(
        "theater",
        nargs="?",
        help="Optional theater hint (e.g. kalimdor) — shown in instructions only",
    )
    parser.add_argument("--variant", default="wowcommanderalpha")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    base = load_globe_config(project_root)
    config = merge_variant_config(base, args.variant)
    variant_cfg = (base.get("world_variants", {}) or {}).get(args.variant, {})

    globe_rel = variant_cfg.get(
        "player_entry",
        variant_cfg.get("output", "03-kml/wowcommanderalpha/doc.kml"),
    )
    globe_path = (project_root / globe_rel).resolve()
    live_dir = globe_path.parent
    live_kml = (live_dir / "campaign_live.kml").resolve()
    if not live_kml.exists():
        live_path = resolve_campaign_live_path(live_dir)
        if live_path is None:
            raise SystemExit(
                f"Missing campaign_live.kml in {live_dir} — "
                "run: python3 scripts/build_world_globe.py --kml-only"
            )
        live_kml = live_path.resolve()

    # Open player globe last so Document LookAt (planet view) wins over stale KMZ camera.
    for path in (live_kml, globe_path):
        subprocess.run(["open", "-a", "Google Earth Pro", str(path)], check=False)

    theater_hint = ""
    if args.theater:
        needle = args.theater.lower()
        for rid in resolve_campaign_region_ids(config, variant_cfg):
            layer = layer_by_id(config, rid)
            label = layer.get("label", rid) if layer else rid
            if needle in rid.lower() or needle in label.lower():
                theater_hint = label
                break

    print(f"Opened {live_kml.name} + {globe_path.name} (starts at Quick View planet — Maelstrom 30,000 mi)")
    print("  EDIT in Places: 'Campaign Live (EDIT HERE)' → Campaign Package (live) or Quick View")
    if theater_hint:
        print(f"    → <continent> → {theater_hint} → Campaign Package → red-cell/blue-cell → tier")
    else:
        print("    → <continent> → <theater> → Campaign Package → red-cell/blue-cell → tier")
    print("  Do NOT add placemarks under Campaign Board NetworkLinks (read-only).")
    print("  After editing: File → Save. Turn export auto-syncs; or double-click")
    print("  scripts/Sync Campaign Board.command to refresh Campaign Board mid-game.")


if __name__ == "__main__":
    main()
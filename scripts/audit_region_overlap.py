#!/usr/bin/env python3
"""Report earth_placement bounding-box overlaps between enabled minimap layers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def layer_box(layer: dict) -> tuple[float, float, float, float] | None:
    ep = layer.get("earth_placement")
    if not ep or "center_lon" not in ep:
        return None
    west = float(ep["center_lon"]) - float(ep["span_lon"]) / 2
    east = float(ep["center_lon"]) + float(ep["span_lon"]) / 2
    south = float(ep["center_lat"]) - float(ep["span_lat"]) / 2
    north = float(ep["center_lat"]) + float(ep["span_lat"]) / 2
    return west, south, east, north


def overlap_area(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    aw, as_, ae, an = a
    bw, bs, be, bn = b
    ow = max(aw, bw)
    oe = min(ae, be)
    os_ = max(as_, bs)
    on = min(an, bn)
    if ow >= oe or os_ >= on:
        return 0.0
    return (oe - ow) * (on - os_)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit region earth_placement overlaps")
    parser.add_argument("--threshold-deg", type=float, default=2.0, help="Flag overlaps wider than this (lon or lat)")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    config_path = project_root / "config" / "globe.json"
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)

    layers = [
        layer
        for layer in config.get("layers", [])
        if layer.get("enabled") and layer.get("layer_type") == "minimap" and layer.get("earth_placement")
    ]
    boxes = {layer["id"]: layer_box(layer) for layer in layers}

    print(f"Enabled minimap regions: {len(layers)}\n")
    flagged = 0
    for i, la in enumerate(layers):
        for lb in layers[i + 1 :]:
            a, b = la["id"], lb["id"]
            ba, bb = boxes[a], boxes[b]
            if not ba or not bb:
                continue
            area = overlap_area(ba, bb)
            if area <= 0:
                continue
            aw, as_, ae, an = ba
            bw, bs, be, bn = bb
            ow = max(aw, bw)
            oe = min(ae, be)
            os_ = max(as_, bs)
            on = min(an, bn)
            lon_w = oe - ow
            lat_h = on - os_
            flag = lon_w >= args.threshold_deg or lat_h >= args.threshold_deg
            if flag:
                flagged += 1
            marker = "FLAG" if flag else "    "
            print(
                f"{marker} {a} vs {b}: lon [{ow:.2f},{oe:.2f}] ({lon_w:.1f}°) "
                f"lat [{os_:.2f},{on:.2f}] ({lat_h:.1f}°) area {area:.1f} deg²"
            )

    if flagged:
        print(f"\n{flagged} pair(s) exceed {args.threshold_deg}° threshold.")
    else:
        print("\nNo overlaps exceed threshold.")


if __name__ == "__main__":
    main()
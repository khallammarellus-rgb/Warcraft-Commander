#!/usr/bin/env python3
"""MGRS coordinate helpers."""

from __future__ import annotations


def mgrs_to_latlon(code: str) -> tuple[float, float]:
    try:
        import mgrs
    except ImportError as exc:
        raise SystemExit("MGRS placement requires: pip3 install mgrs packaging") from exc

    lat, lon = mgrs.MGRS().toLatLon(code.strip().encode())
    return float(lat), float(lon)
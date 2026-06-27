"""Detect wow.export minimap tiles that are uniform ocean (any blue shade, no land)."""

from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore[misc, assignment]

# Pixels with terrain detail — greens, browns, grays, saturated non-water hues.
def _has_land_color(r: int, g: int, b: int) -> bool:
    if g > r + 25 and g > b + 15 and g > 55:
        return True
    if r > 90 and g > 55 and b < min(r, g) - 20:
        return True
    if abs(r - g) < 25 and abs(g - b) < 25 and 70 < r < 210 and not _is_water_blue(r, g, b):
        return True
    if max(r, g, b) - min(r, g, b) > 50 and not _is_water_blue(r, g, b):
        return True
    if r > 160 and g > 160 and b > 160:
        return True
    return False


def _is_water_blue(r: int, g: int, b: int) -> bool:
    """Broad water detection: dark navy, ocean blue, sky blue, light blue."""
    if b >= max(r, g) - 12:
        return True
    if b > 90 and g > 70 and r < min(g, b) - 15:
        return True
    if r < 50 and g < 80 and b > 40:
        return True
    return False


def is_empty_ocean_tile(
    image: Image.Image,
    *,
    uniformity: float = 0.94,
    sample_size: int = 48,
    min_land_fraction: float = 0.003,
    quant_step: int = 24,
    max_uniform_buckets: int = 4,
) -> bool:
    """
    True when a tile is uniform water — any blue shade, no meaningful land.

    Keeps tiles that are mostly blue but contain coastlines, islands, or terrain.
    """
    rgba = image.convert("RGBA").resize((sample_size, sample_size))
    pixels = list(rgba.getdata())
    if not pixels:
        return True

    opaque = [(r, g, b) for r, g, b, a in pixels if a >= 200]
    if not opaque:
        return True

    total = len(opaque)
    land = sum(1 for r, g, b in opaque if _has_land_color(r, g, b))
    land_fraction = land / total
    if land_fraction >= min_land_fraction:
        return False

    blue = sum(1 for r, g, b in opaque if _is_water_blue(r, g, b))
    blue_fraction = blue / total
    if blue_fraction < uniformity:
        return False

    buckets = {(r // quant_step, g // quant_step, b // quant_step) for r, g, b in opaque}
    if len(buckets) <= max_uniform_buckets:
        return True

    # Soft gradients of the same water color family (still no land).
    if len(buckets) <= max_uniform_buckets + 3:
        non_blue = sum(1 for r, g, b in opaque if not _is_water_blue(r, g, b))
        if non_blue / total < 0.02:
            return True

    return False


def is_empty_ocean_file(path: Path, **kwargs) -> bool:
    if Image is None or not path.exists():
        return False
    with Image.open(path) as handle:
        return is_empty_ocean_tile(handle, **kwargs)
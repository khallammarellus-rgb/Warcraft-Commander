# Azeroth Explorer — release checklist

Use this when cutting a new **GitHub Release** zip for explorers (maps only, no Commander wargame).

## Before you start

- Commander globe build is current (`python3 scripts/build_world_globe.py --variant wowcommanderalpha --kml-only`)
- Tiles exist under `02-tiles/<region>/` for every enabled layer in `config/globe.json`

## Standard release (Pacific only)

1. Edit [`config/explorer_release.json`](../config/explorer_release.json):
   - Bump `explorer_version` (semver)
   - Update `changelog`
   - Set `released_at` to today
   - Keep `include_opposite_hemisphere: false` until extra worlds are ready
2. Build + package:
   ```bash
   python3 scripts/package_azeroth_explorer.py
   ```
   Or double-click **`scripts/Build Azeroth Explorer.command`**
3. Test locally: unzip `exports/azeroth-explorer-*.zip`, open `Azeroth Explorer.kml` in Google Earth Pro
4. GitHub Release:
   - Tag: `explorer-v3.0.0` (match `explorer_version`)
   - Upload the zip asset
   - Paste changelog from `explorer_release.json`

## Add an opposite-hemisphere landmass (e.g. Outland)

1. **Export** — wow.export minimap PNGs → `04-edited-exports/maps/outland/minimap/`
2. **Place** — confirm `mgrs_centers.outland` in `config/globe.json`; run `apply_geographic_placements.py` if nudged
3. **Build tiles** (first time for that zone):
   ```bash
   python3 scripts/build_world_globe.py --variant wowcommanderalpha --layers outland
   ```
4. **Enable** — set `layers[id=outland].enabled: true` in `config/globe.json`
5. **Manifest** — in `explorer_release.json`:
   - Bump version (e.g. `3.1.0`)
   - Set `include_opposite_hemisphere: true` (or add `"outland"` to `extra_regions`)
   - Update `changelog`
6. **Package** — `python3 scripts/package_azeroth_explorer.py`
7. **Verify** — Map layers → **Other worlds → Outland** loads in GEP; Quick View bookmark works
8. **GitHub Release** — new tag + zip

## Version scheme

| Release | Example version |
|---------|-----------------|
| Initial Pacific Explorer | `3.0.0` |
| + one extra world | `3.1.0` |
| + multiple worlds | `3.2.0` |
| Tile/placement fix only | `3.1.1` |

Major version aligns with `globe_version.id` in `config/globe.json` (currently `v3`).

## Do not commit to git

- `exports/azeroth-explorer-*.zip`
- `Azeroth Explorer/tiles/` (generated staging)
- Large tile trees under `02-tiles/`

Commit only: `config/explorer_release.json`, scripts, and docs.
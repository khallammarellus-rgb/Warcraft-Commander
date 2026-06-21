# Known Issues

Deferred items and resolved fixes tracked during the Commander Alpha rebuild (June 2026).

## Zoom-shift between overview and detail (fixed)

When zooming in or out, landmasses could appear to shift or resize at the handoff between the overview layer (z0 tiles in `doc.kml`) and the per-region detail layer (`detail.kml` via NetworkLink).

**Cause:** The padded full-export grid from `01-raw-export` was used as the geographic mosaic for `earth_placement` bounds. Land-only tiles from `04-edited-exports` occupy only part of that grid, so z0 stretched ocean padding along with land — wrong size/position at zoom-out even when detail bounds were correct.

**Fix (June 2026):** Layers with `earth_placement` now use the land tile extent from the tile source for both pyramid dimensions and KML georeferencing. Rebuild tiles after this change (`build_world_globe.py`, not `--kml-only`).

## 1200 mi ballooning — neighbor regions covering each other (mitigated)

**Symptom:** At 2000–4000 mi eye altitude, regions looked correct. At ~1200 mi, Northrend swallowed Dragon Isles and Kalimdor swallowed Khaz Algar.

**Cause:** Configured `earth_placement` bounding boxes overlapped heavily (Northrend 1.5× span engulfed Dragon Isles; Kalimdor and Khaz Algar share a large Pacific overlap). Overview z0 uses one PNG per region so land pixels sit in the correct portion of the frame; detail tiles paint their full `LatLonBox` in overlap zones, so the larger neighbor's tiles claim geography belonging to smaller neighbors. Per-tile LOD divisors worsened the tier transition around 1200–1800 mi.

**Fix (June 2026):**

- Reduced `northrend` `size_multiplier` from 1.5 to 0.85 — Northrend↔Dragon Isles lon overlap dropped from ~16.7° to ~0.4°.
- `detail_lod_model: "classic"` — region-level LOD bands for detail tiles (same model as overview z0).
- Span-based `drawOrder` — smaller regions (Dragon Isles, Khaz Algar) paint above larger neighbors in residual overlap zones.
- Audit script: `python3 scripts/audit_region_overlap.py` flags pairs with >2° overlap.

**Remaining:** Kalimdor↔Khaz Algar still has large configured box overlap (~25°); draw-order mitigates at detail zoom. Further span trimming would require Kalimdor or Khaz Algar size/center adjustments.

## Sweet-spot LOD profile (June 2026)

Tuned for stable handoff, progressive detail, and campaign altitude tiers:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `detail_start_miles` | 2000 | Overview z0 above; detail pyramid below |
| `roads_visible_miles` | 1000 | Roads discernible milestone |
| `tactical_miles` | 500 | Tactical terrain milestone |
| `quality_reference_miles` | 500 | Sharpness calibration reference |
| `intermediate_target_miles` | 1000 | Softer mid-zoom reference |
| `lod_overlap_fraction` | 0.12 | Smooth overview ↔ detail handoff |
| `overview_max_lod_factor` | 1.03 | Brief overlap before overview unloads |
| `detail_link_preload_factor` | 0.90 | Detail loads slightly before overview drops |
| `detail_lod_model` | classic | Unified region LOD (not per-tile divisor) |

Full z1–z7 pyramid retained (no `detail_emit_z` truncation) for smooth progressive LOD between 2000 mi handoff and 500 mi tactical zoom.

**Campaign Package** (inside each theater `campaign/<theater>.kml`, template at `campaign/Campaign Package/`):

- **red-cell** / **blue-cell** — faction unit folders, each with Strategic / Operational / Tactical tiers
- **white-cell** — referee markers plus **redcell-discovered** / **bluecell-discovered** for manual reveal

Tier folders are plain editable containers in Google Earth Pro (no `Region` on folders — GEP greys those out). Zoom-tier `Region`/`Lod` is applied to each placemark when you run `python3 scripts/sync_campaign_tier_lod.py` or export a turn KMZ.

**Google Earth Pro:** NetworkLink folders are **read-only** (Add → Placemark greyed out). Workaround (`campaign_places_mode: live_edit`):

1. **View / lazy load / refresh:** Campaign Board NetworkLinks in `doc.kml` (unchanged).
2. **Edit:** `campaign_live.kml` — inline folders with the same Region/Lod bands, fully editable.
3. After save in GEP: `python3 scripts/sync_campaign_live.py --push` then Refresh Campaign Board links.

Open both: `python3 scripts/open_theater_campaign.py kalimdor`

Place markers at Earth lon/lat from the stabilized map; imagery stability keeps markers on roads across zoom levels.

## Wargame turn packages (Discord / Gmail)

**Primary:** Pass small turn `.kmz` files via Discord (Gmail attachment as fallback). The full globe stays installed locally; only markers travel.

```bash
python3 scripts/package_wargame_client.py --instructions
python3 scripts/package_wargame_client.py --turn 12 --player Blue
python3 scripts/package_wargame_client.py --turn 12 --player Red --role red-cell --format double-blind
```

### Campaign Board vs Campaign Package

- **Campaign Board** (in `doc.kml` Places) — parent folder of per-theater NetworkLinks. Lazy-loads each `campaign/<theater>.kml` when you zoom near that landmass. **Refresh** reloads the linked file after you save edits on disk.
- **Campaign Package** (inside each theater file) — `red-cell` / `blue-cell` / `white-cell` with tier folders; white-cell has `redcell-discovered` / `bluecell-discovered` for referee reveal.

### Password / tamper protection

Google Earth Pro **cannot** password-lock folders. Security is honor-system on the shared master `campaign/*.kml`, or **filtered exports** (`--role`) so hidden units are not embedded in an opponent's turn KMZ.

### Blind play and proximity reveal

Set `campaign/campaign_meta.json` (templates in `Campaign Package/`):

| Format | Red sees | Blue sees |
|--------|----------|-------------|
| `no-blind` | all | all |
| `single-blind` | all | own + reveals |
| `double-blind` | own + reveals | own + reveals |

Export with `--role red-cell|blue-cell|white-cell`. Proximity reveal (default **1 km**): moved/new markers expose enemy units within `reveal_radius_km`. Manual reveal: referee places markers in `white-cell` → `redcell-discovered` or `bluecell-discovered`.

**Hosted mode (optional):** Set `campaign_deploy_mode: hosted` and `campaign_base_url` in `config/globe.json`, rebuild `doc.kml`, upload `campaign/*.kml` to HTTPS after each turn. GEP desktop polls via NetworkLink `onInterval` when `campaign_refresh_mode: interval`.

## Transparent bridge tiles

Transparent tiles between overview and detail LOD bands were considered to smooth the transition. **Rejected:** KML GroundOverlay / superoverlay tiles cannot be made transparent in Google Earth Pro in a way that bridges two LOD tiers cleanly.

**Status:** Out of scope — no transparent bridge tiles will be built.

## Navigation architecture (June 2026) — poster_lazy

**Player goal:** See where Kalimdor is at planet scale, zoom toward it confidently, roads at 600 mi, detail at 150 mi.

**Previous tiered mode problems:** 38 eager z0 overlays caused doubling, disappearing, and rough overview↔detail handoffs. Nothing at 6000 mi (visibility capped at 2500 mi).

**Current mode (`world_index.mode: poster_lazy`):**

1. **6000–3200 mi** — One *Azeroth Reference* poster (`world_poster/doc.kml`). Single navigation chart; no per-region stacking.
2. **Theater zoom** — Lazy `NetworkLink` per region → `region/doc.kml` (full z0–z7 pyramid). Only continents in the viewport load.
3. **No overview/detail split** — One progressive pyramid per region; no second handoff layer.

Rebuild: `python3 scripts/build_world_globe.py --variant wowcommanderalpha` (poster tiles required once).

## 6000 mi planet view — chaotic doubled continents (superseded by poster_lazy)

**Symptom:** At ~6000 mi eye altitude, every continent appears doubled, clipped, and massively oversized.

**Cause:** `size_multipliers` (e.g. Kalimdor 1.5×) inflate `earth_placement` spans once — the **same** bounds are used for z0 overview and the detail pyramid. They do **not** compound per zoom level, but at planet view all ~20 per-region z0 overlays load eagerly in `doc.kml` with heavily overlapping boxes, so neighbors stack in the same screen area.

**Fix (June 2026):** `overview_visibility_max_miles` lowered to 3500 — per-region z0 silhouettes appear only from theater altitude (~3500 mi) down to the 2000 mi detail handoff, not at 6000 mi. `overview_min_lod_factor` raised to 1.0 for a cleaner entry band.

**Tactical sizing:** Keep `size_multipliers` for detail zoom (roads at 1000 mi, tactical at 500 mi). Splitting overview vs detail bounds would reintroduce handoff jumps, so planet view is controlled via visibility, not separate per-tier scaling.

## Grid reference vs tile source

Tiles are read from `04-edited-exports` (ocean-trimmed) but grid anchoring uses matching paths under `01-raw-export` so geographic bounds align with the full export grid. `01-raw-export` is kept as a reference only and may be removed once placements are validated without it.
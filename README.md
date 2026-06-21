# WoW Commander Alpha Project

Build an interactive tiled globe of Azeroth for **Google Earth Pro** — wargaming, roleplay, and campaign markup.

**Azeroth Explorer** ships the maps only (no wargame layer). Run `scripts/Build Azeroth Explorer.command` and find the zip in `exports/`. See [docs/EXPLORER_RELEASE.md](docs/EXPLORER_RELEASE.md).

Tiles come from ocean-trimmed exports in `04-edited-exports`, anchored to full-grid reference data in `01-raw-export`. The active build variant is `wowcommanderalpha`.

See [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) for deferred items.

---

## What you build

1. Export minimap imagery from your WoW installation with **wow.export**.
2. Run the project build scripts to slice tiles and generate KML superoverlays.
3. Open the world index in **Google Earth Pro** and fly around Azeroth.

The map uses fantasy coordinates — it wraps the virtual globe like a decal, not real-world GPS. That keeps wargaming layouts simple.

---

## Folder layout

```
WoW Commander Alpha Project/
├── 01-raw-export/          Full wow.export grids (grid reference)
├── 04-edited-exports/      Ocean-trimmed PNGs — tile build source
├── 02-tiles/<region>/      Generated tile pyramids
├── 03-kml/wowcommanderalpha/
│   ├── doc.kml             World index — open this in Google Earth
│   ├── campaign/           Campaign markup layer
│   └── <region>/           overview.kml + detail.kml per region
├── config/globe.json       Placements, LOD, build variants
├── scripts/                Build and helper scripts
├── docs/                   Release notes and known issues
└── README.md
```

**Rule of thumb:** put tile sources in `04-edited-exports`, keep grid reference in `01-raw-export`, generate tiles into `02-tiles/<region>/`, then open `03-kml/wowcommanderalpha/doc.kml`.

---

## Build the globe

```bash
cd "~/WoW Commander Alpha Project"
python3 scripts/apply_geographic_placements.py
python3 scripts/build_world_globe.py --variant wowcommanderalpha --skip-poster
```

`apply_geographic_placements.py` refreshes MGRS-centered bounds in `config/globe.json`. The globe build reads `04-edited-exports` and maps each region's land extent to its `earth_placement` bounds.

### Verify your setup

```bash
bash scripts/verify_setup.sh
python3 scripts/check_images.py
```

---

## WoW Commander — campaign play

Install the full globe once (`03-kml/wowcommanderalpha/doc.kml`). Turns pass **markers only**, not map tiles.

### Player launcher

Double-click **`scripts/WOW Commander.command`** for setup, editor, sync, and turn export.

### Set up a new campaign

Choose **1 — Set up my campaign** in the player menu, or run `python3 scripts/setup_campaign.py`.

The wizard walks through continent, blind mode, cell assignment, faction, commander name, force size, and HQ placement. Faction icon styles load into **Unit palettes/** for the editor only — they never export with turns.

### Reset the board

Run `python3 scripts/sanitize_campaign_board.py` to clear theaters, session state, and turn exports while leaving map tiles untouched. Add `--dry-run` to preview or `--yes` to skip confirmation.

### Turn loop

1. Open the campaign editor from the player menu and edit in Google Earth Pro.
2. Save in GEP, then sync from the player menu.
3. Export a turn package: `python3 scripts/package_wargame_client.py --turn 12 --player YourName --role red-cell`
4. Share the `.kmz` with the other player; they open it on top of their local globe.

**Blind play:** configure in the setup wizard, or set `campaign_meta.json` from the double-blind template, then export per cell:

```bash
python3 scripts/package_wargame_client.py --turn 12 --player Red --role red-cell
python3 scripts/package_wargame_client.py --turn 12 --player Blue --role blue-cell
```

Proximity reveal defaults to **1 km** for moved or new markers. Use honor rules or filtered `--role` exports for blind play.

**Hosted mode:** set `campaign_deploy_mode: hosted` and `campaign_base_url` in `config/globe.json`, rebuild `doc.kml`, and publish campaign KML to your hosted URL after each turn.

---

## Azeroth Explorer

Explorer is a standalone maps-only zip for players who only want to fly around Azeroth.

```bash
python3 scripts/package_azeroth_explorer.py
```

Or double-click **`scripts/Build Azeroth Explorer.command`**. Open `Azeroth Explorer.kml` from the packaged folder in Google Earth Pro.

---

## Helper scripts

Run all commands from the project root.

| Script | Command | Purpose |
|--------|---------|---------|
| Setup campaign | `python3 scripts/setup_campaign.py` | Faction library, HQ, blind mode |
| Sanitize board | `python3 scripts/sanitize_campaign_board.py` | Reset theaters for a new game |
| Export turn KMZ | `python3 scripts/package_wargame_client.py --turn N` | Turn package (markers only) |
| Package Explorer | `python3 scripts/package_azeroth_explorer.py` | Maps-only release zip |
| Globe audit | `python3 scripts/audit_globe_performance.py` | NetworkLinks, tile weight, placemarks |
| Verify setup | `bash scripts/verify_setup.sh` | Check folders and Python |
| Check images | `python3 scripts/check_images.py` | List PNGs and file sizes |

Core build scripts use Python's standard library. The campaign setup wizard needs `pip install -r requirements.txt`.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Google Earth shows nothing | Tick the KML checkbox in Places; keep KML and tile folders together |
| Analyze script finds no files | Confirm wow.export filenames; naming varies by version |
| Slow or huge output | Start with a small test region before building the full globe |
| Zoom shift at LOD handoff | See [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) |

---

## Quick-start checklist

- [ ] Run `bash scripts/verify_setup.sh`
- [ ] Export a small test area with wow.export into `01-raw-export/`
- [ ] Run `python3 scripts/check_images.py`
- [ ] Run `python3 scripts/build_world_globe.py --variant wowcommanderalpha --skip-poster`
- [ ] Open `03-kml/wowcommanderalpha/doc.kml` in Google Earth Pro

---

## Credits

This project exports map imagery from World of Warcraft using **wow.export**. None of this work would be possible without the creator of wow.export.

## Legal notices

- All trademarks and images associated with **Blizzard Entertainment** and **World of Warcraft** remain the property of their respective owners. The publisher uses them here only to build and view fan maps; they are **not** presented as the publisher's original work.
- **Google Earth** products are used under their applicable licenses. The publisher uses them as a viewer only and does **not** claim Google Earth or related marks as the publisher's intellectual property.

## About the publisher

The publisher has no formal background in programming or software development. **Grok AI CLI Build** and **Cloudflare AI Plugins** were used to author the scripts, JSON configuration, and build steps that produce this project.
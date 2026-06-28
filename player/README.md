# WoW Commander — player install

Play on the hosted campaign board in **Google Earth Pro**.

**Globe:** v3 · Built 2026-06-28

---

## Download and play (3 steps)

1. Open **https://github.com/khallammarellus-rgb/Warcraft-Commander**
2. Click **Code → Download ZIP**
3. Unzip the folder, then open **`player/WoW Commander.kml`** in Google Earth Pro

Keep `player/kml/`, `player/tiles/`, and `WoW Commander.kml` together inside the `player/` folder.

**Do not** download **Source code** from old Releases (`player-v3` split zip) — use **Code → Download ZIP** on the main repo page.

## Portal (hosted campaign)

- Getting started: https://wow-commander-campaign.pages.dev/start/
- Table 01: https://wow-commander-campaign.pages.dev/games/table-01/

Campaign markers refresh from the portal (~60s). Right-click **Campaign Board** links → **Refresh** after turns update.

## Optional — Python player menu

Only needed for local setup, sync, or turn export — **not** for viewing the map or hosted portal uploads.

```bash
cd player
python3 -m pip install -r requirements.txt
```

Mac: double-click `scripts/WOW Commander.command`

## Map regions in this pack

- Kalimdor
- Eastern Kingdoms
- Nazjatar
- Siren Isle
- Founders Point
- Razorwind Shores
- The Maelstrom
- Tol Barad
- Wandering Isle
- Northrend
- Pandaria
- Broken Isles
- Zandalar
- Kul Tiras
- Dragon Isles
- Khaz Algar
- Kezan
- Isle of Conquest
- The Dread Chain
- Jorundall
- … and 14 more regions

---

## Credits

Map imagery via [wow.export](https://github.com/Kruithne/wow.export).

# WoW Commander player pack v3

**>>> DOWNLOAD THE ASSETS BELOW — NOT "Source code (zip)" <<<**

The green **Code → Download ZIP** on the main repo page does **not** include map tiles. Use only the `wowcommander-player-*` files under **Assets**.

---

## New player setup (you only need Google Earth Pro installed)

### 1. Install Python 3 (one-time)
- Download from [python.org/downloads](https://www.python.org/downloads/)
- Open Terminal and verify: `python3 --version`

### 2. Open the correct download page
- **This release:** https://github.com/khallammarellus-rgb/Warcraft-Commander/releases/tag/player-v3
- **Do not** use **Code → Download ZIP** on the main repo
- **Do not** download **Source code (zip)** here — no map tiles

### 3. Download these Assets (all of them — TWO required files)
Put every file in one folder (e.g. `~/Downloads/wow-commander/`):

**Required (both must finish downloading):**
- `wowcommander-player-v3_2026-06-26.zip` (~279 MB)
- `wowcommander-player-v3_2026-06-26.z01` (~1.8 GB) ← easy to miss!

**Helpful:** `join_player_pack.sh`, `HOW_TO_JOIN.txt`, `GETTING_STARTED.txt`

Verify before joining:
```bash
cd ~/Downloads/wow-commander
ls -lh wowcommander-player-v3_2026-06-26.zip wowcommander-player-v3_2026-06-26.z01
```

### 4. Join the split zip
**Easiest (Mac):**
```bash
bash join_player_pack.sh
```
**Manual (Mac Terminal):**
```bash
zip -FF wowcommander-player-v3_2026-06-26.zip --out wowcommander-player-joined.zip
```
If `zip` says it cannot find `.z01`, you are in the wrong folder or the 1.8 GB part was not downloaded.

**Windows:** Put both parts in one folder → **7-Zip → Extract Here**

### 5. Unzip the joined file
- **Mac:** `unzip wowcommander-player-joined.zip`
- **Windows:** Right-click → **Extract All**
- Keep `02-tiles/`, `03-kml/`, `scripts/`, and `config/` together

### 6. Install Python dependencies (one-time)
```bash
cd path/to/unzipped/folder
python3 -m pip install -r requirements.txt
```

### 7. Open the map in Google Earth Pro
- **File → Open** → `03-kml/wowcommanderalpha/doc_player.kml`
- Tick **WOW Commander Alpha (play)** in Places

### 8. Open your table on the portal
- [Getting started](https://wow-commander-campaign.pages.dev/start/)
- [Table 01](https://wow-commander-campaign.pages.dev/games/table-01/)

### 9. Optional — player menu
- **Mac:** double-click `scripts/WOW Commander.command`
- **Terminal:** `python3 scripts/player_menu.py`

### 10. Each turn
- Edit markers in Google Earth → **save**
- Upload KMZ on your table page when it is your turn
- Right-click **Campaign Board** links in GEP → **Refresh** after white cell merges

---

**Included:** 36,843 map tile PNGs, all KML, scripts, config, and faction assets — full local map install. Live campaign markers refresh from the portal.
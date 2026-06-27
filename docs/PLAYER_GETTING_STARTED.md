# WoW Commander — new player setup (start from zero)

You already have **Google Earth Pro**. Follow these steps in order.

## 1. Install Python 3 (one-time)

- **Mac:** Download and install from [python.org/downloads](https://www.python.org/downloads/) (check **“Add python.exe to PATH”** on Windows; on Mac the installer adds `python3`).
- Open **Terminal** (Mac) or **Command Prompt** (Windows).
- Verify: `python3 --version` (should show 3.10 or newer).

## 2. Open the correct GitHub download page

- Go to **[GitHub Releases → player-v3](https://github.com/khallammarellus-rgb/Warcraft-Commander/releases/tag/player-v3)**.
- **Do not** use the green **Code → Download ZIP** button on the main repo page.
- **Do not** download GitHub’s automatic **“Source code (zip)”** on the release page.
- Those files are developer snapshots — they **do not include map tiles**.

## 3. Download these Assets (all of them)

Under **Assets** on the release page, download every player-pack file:

- `wowcommander-player-v3_2026-06-26.zip`
- `wowcommander-player-v3_2026-06-26.z01`
- `HOW_TO_JOIN.txt` (optional reference)
- `GETTING_STARTED.txt` (this guide, plain text)

Put all downloaded files in **one folder** (for example `~/Downloads/wow-commander/`).

## 4. Join the split zip (Mac)

GitHub limits file size, so the pack is split into two parts. In Terminal:

```bash
cd ~/Downloads/wow-commander
zip -FF wowcommander-player-v3_2026-06-26.zip --out wowcommander-player-joined.zip
```

**Windows:** Put both part files in one folder → select all → **7-Zip → Extract Here**.

## 5. Unzip the joined file

- **Mac:** Double-click `wowcommander-player-joined.zip`, or in Terminal: `unzip wowcommander-player-joined.zip`
- **Windows:** Right-click → **Extract All…**

You should see folders such as `02-tiles/`, `03-kml/`, `scripts/`, and `config/`. **Keep this folder structure intact.**

## 6. Install Python dependencies (one-time)

In Terminal, from the unzipped folder:

```bash
cd path/to/unzipped/folder
python3 -m pip install -r requirements.txt
```

## 7. Open the map in Google Earth Pro

- In Google Earth Pro: **File → Open**
- Select: `03-kml/wowcommanderalpha/doc_player.kml`
- In the **Places** panel, tick the checkbox next to **WOW Commander Alpha (play)** so layers load.
- Wait for map tiles to appear (first load can take a minute).

Campaign markers refresh from the hosted portal (~60 seconds). Right-click **Campaign Board** links → **Refresh** after turns update.

## 8. Open your table on the portal

- Hub: [wow-commander-campaign.pages.dev](https://wow-commander-campaign.pages.dev/)
- Getting started: [wow-commander-campaign.pages.dev/start/](https://wow-commander-campaign.pages.dev/start/)
- **Table 01:** [wow-commander-campaign.pages.dev/games/table-01/](https://wow-commander-campaign.pages.dev/games/table-01/)

White cell will give you an **upload token** for your cell (red or blue).

## 9. Optional — player menu (setup, sync, export)

- **Mac:** Double-click `scripts/WOW Commander.command`
- **Terminal:** `python3 scripts/player_menu.py`

Use the menu to set up a campaign, sync after editing in Google Earth, or export a turn KMZ.

## 10. Turn loop (each turn)

- Edit markers in Google Earth Pro → **save** in GEP
- When it is your cell’s turn, **upload your KMZ** on your table page on the portal
- Right-click **Campaign Board** NetworkLinks in GEP → **Refresh** after white cell merges the turn

---

**What’s in the player pack?** 36,000+ map tile PNGs (`02-tiles/`), all KML, scripts, config, and faction assets — everything needed to run the map locally. Live campaign data comes from the portal, not from re-downloading the pack each turn.
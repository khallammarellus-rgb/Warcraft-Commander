#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
echo "Packaging WoW Commander player release (tiles + KML + scripts)…"
echo "This takes several minutes (~3 GB of map tiles)."
python3 scripts/package_player_release.py --split-mb 1800
echo ""
read -n 1 -s -r -p "Press any key to close..."
#!/bin/bash
# Shortcut — or double-click "WOW Commander.command" for the full menu.
cd "$(dirname "$0")/.." || exit 1
python3 scripts/player_menu.py --action export
echo ""
read -n 1 -s -r -p "Press any key to close..."
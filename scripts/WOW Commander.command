#!/bin/bash
cd "$(dirname "$0")/.." || exit 1

# One-stop player launcher — replaces hunting through multiple .command files.
printf '\033[8;40;90t' 2>/dev/null || true

# Launch retro install wizard (click crest); falls back to text menu if tkinter unavailable
python3 scripts/player_install_wizard.py 2>/dev/null || python3 scripts/player_menu.py
echo ""
read -n 1 -s -r -p "Press any key to close..."
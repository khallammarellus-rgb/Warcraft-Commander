#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
echo "Sync Azeroth Explorer → ../Azeroth Explorer Project"
python3 scripts/sync_explorer_project.py --push
echo ""
read -n 1 -s -r -p "Press any key to close..."
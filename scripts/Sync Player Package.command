#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
echo "Packaging player/ and pushing to GitHub (tiles in ~1 GB batches)…"
echo "This may take a while."
python3 scripts/sync_player_package.py --push
echo ""
read -n 1 -s -r -p "Press any key to close..."
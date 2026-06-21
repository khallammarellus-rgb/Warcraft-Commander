#!/bin/bash
cd "$(dirname "$0")/.." || exit 1

echo "Azeroth Explorer — build + package zip"
echo "======================================"
echo ""
python3 scripts/sync_explorer_project.py
echo ""
read -n 1 -s -r -p "Press any key to close..."
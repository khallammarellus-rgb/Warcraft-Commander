#!/bin/bash
cd "$(dirname "$0")/.." || exit 1

echo "Azeroth Explorer — build + package zip"
echo "======================================"
echo ""
python3 scripts/package_azeroth_explorer.py
python3 scripts/publish_github_pages.py
echo ""
read -n 1 -s -r -p "Press any key to close..."
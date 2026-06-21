#!/bin/bash
cd "$(dirname "$0")/.." || exit 1
python3 scripts/sanitize_campaign_board.py
echo ""
read -n 1 -s -r -p "Press any key to close..."
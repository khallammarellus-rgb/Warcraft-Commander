#!/bin/bash
cd "$(dirname "$0")/.." || exit 1

echo "WOW Commander — globe performance audit"
echo ""
python3 scripts/audit_globe_performance.py --variant wowcommanderalpha
echo ""
read -n 1 -s -r -p "Press any key to close..."
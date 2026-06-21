#!/bin/bash
cd "$(dirname "$0")/.." || exit 1

echo "Hosted campaign mode — Cloudflare Pages serves role-filtered KML views."
echo "Players refresh Campaign Board NetworkLinks in Google Earth Pro."
echo "After each turn: scripts/Deploy Pages.command (or organizer menu → p)"
echo ""
read -r -p "HTTPS base URL (no trailing slash): " BASE_URL
if [[ -z "$BASE_URL" ]]; then
  echo "Cancelled — no URL entered."
  read -n 1 -s -r -p "Press any key to close..."
  exit 1
fi

python3 scripts/configure_hosted_campaign.py --mode hosted --url "$BASE_URL" --rebuild
echo ""
read -n 1 -s -r -p "Press any key to close..."
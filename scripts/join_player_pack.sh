#!/bin/bash
# Join split wowcommander-player release parts (Mac/Linux).
# Run from the folder where you downloaded the GitHub Assets.

set -euo pipefail

ZIP_NAME="wowcommander-player-v3_2026-06-26.zip"
Z01_NAME="wowcommander-player-v3_2026-06-26.z01"
OUT_NAME="wowcommander-player-joined.zip"

cd "$(dirname "$0")/.." 2>/dev/null || true

# If run from Downloads, use current directory when assets are here.
if [[ -f "./${ZIP_NAME}" || -f "./${Z01_NAME}" ]]; then
  :
elif [[ -n "${1:-}" && -d "$1" ]]; then
  cd "$1"
else
  echo "Usage: drag this script into Terminal, or:"
  echo "  cd ~/Downloads/wow-commander && bash join_player_pack.sh"
  echo ""
  echo "Run from the folder containing BOTH:"
  echo "  ${ZIP_NAME}  (~279 MB)"
  echo "  ${Z01_NAME}  (~1.8 GB)"
  exit 1
fi

echo "Working directory: $(pwd)"
echo ""
ls -lh "./${ZIP_NAME}" "./${Z01_NAME}" 2>/dev/null || true
echo ""

missing=0
if [[ ! -f "./${ZIP_NAME}" ]]; then
  echo "MISSING: ${ZIP_NAME}"
  missing=1
fi
if [[ ! -f "./${Z01_NAME}" ]]; then
  echo "MISSING: ${Z01_NAME}  ← download this from GitHub Assets (1.8 GB)"
  missing=1
fi
if [[ "$missing" -ne 0 ]]; then
  echo ""
  echo "Go to: https://github.com/khallammarellus-rgb/Warcraft-Commander/releases/tag/player-v3"
  echo "Under Assets, download EVERY wowcommander-player file (not Source code)."
  exit 1
fi

echo "Joining parts…"
zip -FF "./${ZIP_NAME}" --out "./${OUT_NAME}"
echo ""
echo "Done: ${OUT_NAME}"
echo "Next: unzip ${OUT_NAME}"
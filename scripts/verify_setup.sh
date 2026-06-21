#!/bin/bash
# Verify that the WoW-Azeroth-Map project is ready to use.
# Run from the project root: bash scripts/verify_setup.sh

set -e

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "WoW Azeroth Map — Setup Check"
echo "=============================="
echo "Project folder: $PROJECT_ROOT"
echo ""

REQUIRED_DIRS=(
  "01-raw-export"
  "02-tiles"
  "03-kml"
  "docs"
  "scripts"
  "assets"
)

missing=0
for dir in "${REQUIRED_DIRS[@]}"; do
  if [ -d "$dir" ]; then
    echo "  [OK] $dir/"
  else
    echo "  [MISSING] $dir/"
    missing=$((missing + 1))
  fi
done

echo ""
if command -v python3 &>/dev/null; then
  echo "  [OK] python3 found: $(python3 --version)"
else
  echo "  [WARN] python3 not found — helper scripts need Python 3"
  missing=$((missing + 1))
fi

echo ""
if [ "$missing" -eq 0 ]; then
  echo "All checks passed. Next step: export a small test map with wow.export"
  echo "into 01-raw-export/, then run: python3 scripts/check_images.py"
else
  echo "$missing issue(s) found. Re-run project setup or create missing folders."
  exit 1
fi
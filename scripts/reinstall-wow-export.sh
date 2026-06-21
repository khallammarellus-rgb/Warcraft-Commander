#!/bin/bash
# Clean reinstall of wow.export on macOS.
# Fixes: EACCES permission denied on gpu_shader_cache.bin
#
# Why this happens: re-running the installer without deleting the old
# folder first. The old gpu_shader_cache.bin is read-only and cannot
# be overwritten.
#
# Usage:
#   bash scripts/reinstall-wow-export.sh
#   bash scripts/reinstall-wow-export.sh ~/Downloads/wow-export-osx-arm64-0.2.17/installer

set -e

INSTALLER="${1:-$HOME/Downloads/wow-export-osx-arm64-0.2.17/installer}"
APP_SUPPORT="$HOME/Library/Application Support/wow.export"
APP_CACHE="$HOME/Library/Caches/wow.export"
APP_LINK="/Applications/wow.export.app"

echo "=== wow.export clean reinstall ==="

# Stop running copies
if pgrep -x wow.export >/dev/null 2>&1; then
  echo "Closing wow.export..."
  killall wow.export 2>/dev/null || true
  sleep 2
fi
if pgrep -x installer >/dev/null 2>&1; then
  echo "Closing old installer..."
  killall installer 2>/dev/null || true
  sleep 1
fi

# Remove leftover install (this is the critical step)
echo "Removing old install folders..."
rm -rf "$APP_SUPPORT"
rm -rf "$APP_CACHE"
rm -f "$APP_LINK"

if [ ! -x "$INSTALLER" ]; then
  echo ""
  echo "ERROR: Installer not found at:"
  echo "  $INSTALLER"
  echo ""
  echo "Download wow.export, unzip it, then run:"
  echo "  bash scripts/reinstall-wow-export.sh /path/to/installer"
  exit 1
fi

echo "Running installer: $INSTALLER"
"$INSTALLER"

if [ -x "$APP_SUPPORT/wow.export.app/Contents/MacOS/wow.export" ]; then
  echo ""
  echo "SUCCESS: wow.export installed."
  echo "Launch from Applications or run:"
  echo "  open /Applications/wow.export.app"
else
  echo ""
  echo "Install may have failed. Check the installer window for errors."
  exit 1
fi
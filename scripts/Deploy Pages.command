#!/bin/bash
cd "$(dirname "$0")/.." || exit 1

echo "WoW Commander — Cloudflare Pages deploy"
echo "======================================="
echo ""
echo "1. Sync campaign if you edited in Google Earth:"
echo "   python3 scripts/sync_campaign_live.py --push"
echo ""
read -r -p "Continue with build + deploy? (y/n): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy](es)?$ ]]; then
  echo "Cancelled."
  read -n 1 -s -r -p "Press any key to close..."
  exit 0
fi

# Wrangler needs Node on PATH (Finder double-click has no system node).
if [[ -x portal/.tools/node/bin/node ]]; then
  export PATH="$(pwd)/portal/.tools/node/bin:$PATH"
elif ! command -v node >/dev/null 2>&1; then
  echo ""
  echo "Downloading portable Node.js for Cloudflare Wrangler..."
  NODE_VER="v22.14.0"
  ARCH="$(uname -m)"
  if [[ "$ARCH" == "arm64" ]]; then
    NODE_PKG="node-${NODE_VER}-darwin-arm64.tar.gz"
  else
    NODE_PKG="node-${NODE_VER}-darwin-x64.tar.gz"
  fi
  mkdir -p portal/.tools
  curl -fsSL "https://nodejs.org/dist/${NODE_VER}/${NODE_PKG}" \
    -o portal/.tools/node.tar.gz || exit 1
  tar -xzf portal/.tools/node.tar.gz -C portal/.tools
  EXTRACTED=(portal/.tools/node-"${NODE_VER}"-*)
  mv "${EXTRACTED[0]}" portal/.tools/node
  rm -f portal/.tools/node.tar.gz
  export PATH="$(pwd)/portal/.tools/node/bin:$PATH"
fi

if [[ ! -d portal/node_modules ]]; then
  echo ""
  echo "Installing Cloudflare Wrangler (first time only)..."
  (cd portal && npm install) || exit 1
fi

python3 scripts/publish_portal_site.py --deploy --all-games
echo ""
read -n 1 -s -r -p "Press any key to close..."
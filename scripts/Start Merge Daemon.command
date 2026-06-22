#!/bin/bash
cd "$(dirname "$0")/.."
if [[ -f portal/.deploy-secrets.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source portal/.deploy-secrets.env
  set +a
fi
export PORTAL_ORIGIN="${PORTAL_ORIGIN:-https://wow-commander-campaign.pages.dev}"
echo "Merge daemon polling $PORTAL_ORIGIN every 45s (Ctrl+C to stop)"
exec python3 scripts/merge_runner_daemon.py
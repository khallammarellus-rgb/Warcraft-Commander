#!/bin/bash
cd "$(dirname "$0")/.."
echo "Merge daemon polling ${PORTAL_ORIGIN:-https://wow-commander-campaign.pages.dev} every 45s (Ctrl+C to stop)"
exec ./scripts/run_merge_daemon.sh
#!/usr/bin/env bash
# Wrapper for merge_runner_daemon.py — sources portal/.deploy-secrets.env when present.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/portal/.deploy-secrets.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/portal/.deploy-secrets.env"
  set +a
fi

export PORTAL_ORIGIN="${PORTAL_ORIGIN:-https://wow-commander-campaign.pages.dev}"
exec python3 "$ROOT/scripts/merge_runner_daemon.py" "$@"
#!/usr/bin/env bash
# Install WoW Commander merge daemon as a macOS LaunchAgent (Option B backup runner).
#
#   ./scripts/install_merge_daemon.sh          # install + start
#   ./scripts/install_merge_daemon.sh --uninstall

set -euo pipefail

LABEL="com.wowcommander.merge-daemon"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS_FILE="$PROJECT_ROOT/portal/.deploy-secrets.env"
LOG_DIR="$HOME/Library/Logs"
STDOUT_LOG="$LOG_DIR/wow-commander-merge-daemon.log"
STDERR_LOG="$LOG_DIR/wow-commander-merge-daemon.err.log"

uninstall() {
  if launchctl list 2>/dev/null | grep -q "$LABEL"; then
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  fi
  rm -f "$PLIST"
  echo "Removed merge daemon LaunchAgent."
}

if [[ "${1:-}" == "--uninstall" ]]; then
  uninstall
  exit 0
fi

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "Missing $SECRETS_FILE — copy from portal/.deploy-secrets.env.example or run deploy setup first." >&2
  exit 1
fi

RUNNER="$PROJECT_ROOT/scripts/run_merge_daemon.sh"
chmod +x "$RUNNER"
mkdir -p "$(dirname "$PLIST")" "$LOG_DIR"

uninstall >/dev/null 2>&1 || true

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${RUNNER}</string>
    <string>--interval</string>
    <string>45</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${PROJECT_ROOT}</string>
  <key>StandardOutPath</key>
  <string>${STDOUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${STDERR_LOG}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>30</integer>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST"

echo "Merge daemon installed."
echo "  Plist:  $PLIST"
echo "  Logs:   $STDOUT_LOG"
echo "  Errors: $STDERR_LOG"
echo "  Stop:   launchctl bootout gui/$(id -u)/$LABEL"
echo "  Remove: $0 --uninstall"
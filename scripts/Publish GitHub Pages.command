#!/bin/bash
cd "$(dirname "$0")/.."
python3 scripts/publish_github_pages.py
echo ""
read -p "Press Enter to close…"
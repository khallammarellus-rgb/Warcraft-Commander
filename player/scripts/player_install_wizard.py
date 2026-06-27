#!/usr/bin/env python3
"""
WoW Commander player install wizard — retro desktop walkthrough.

  python3 scripts/player_install_wizard.py
  Double-click WOW Commander.command (launches menu; use installer from menu or run directly)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from player_install.retro_app import run_wizard


def main() -> int:
    run_wizard()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
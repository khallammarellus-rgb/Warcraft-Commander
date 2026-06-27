#!/usr/bin/env python3
"""
WOW Commander — one-stop player menu (casual-friendly).

Wraps existing scripts so players double-click one launcher instead of many .command files.

  python3 scripts/player_menu.py
  python3 scripts/player_menu.py --action setup
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_branding import warcraft_commander_crest
from campaign_session import load_session

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VARIANT = "wowcommanderalpha"
SCRIPTS = PROJECT_ROOT / "scripts"


def _run(cmd: list[str], *, cwd: Path | None = None) -> int:
    print()
    result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT)
    return result.returncode


def _pause() -> None:
    if sys.stdin.isatty():
        input("\nPress Enter to return to the menu...")


def _recommended_step(project_root: Path) -> str:
    session = load_session(project_root, variant=DEFAULT_VARIANT)
    if session is None:
        return "You have not run setup yet. Choose [1] Set up my campaign."
    commander = session.get("commander_name", "Commander")
    cell = session.get("player_cell", "your cell")
    theater = session.get("theater", "theater")
    return (
        f"Welcome back, {commander}. Cell: {cell} · Theater: {theater}.\n"
        "Typical turn: [2] Open editor → save in Google Earth → [3] Sync → [4] Export turn."
    )


def _print_header(project_root: Path) -> None:
    print(warcraft_commander_crest())
    print()
    print(_recommended_step(project_root))
    print()
    print("=" * 60)
    print("  WOW COMMANDER — PLAYER MENU")
    print("=" * 60)
    print("  1  Set up my campaign (first time or new game)")
    print("  2  Open Google Earth editor (place units)")
    print("  3  Sync after saving in Google Earth")
    print("  4  Export my turn (Discord / email)")
    print("  5  What should I do next?")
    print("  6  How to play (full instructions)")
    print("  —")
    print("  i  Install wizard (extract, shortcuts, system check)")
    print("  p  Package icon pack (share with opponent)")
    print("  m  Import icon pack")
    print("  o  Organizer tools (reset board, hosted mode, …)")
    print("  q  Quit")
    print("=" * 60)


def _print_play_guide(project_root: Path) -> None:
    session = load_session(project_root, variant=DEFAULT_VARIANT)
    print()
    print("QUICK PATH")
    print("──────────")
    if session is None:
        print("  1 → Set up campaign (map, cell, commander, HQ)")
        print("  2 → Open editor — add units under your cell folder")
        print("  3 → After File → Save in GEP, sync the campaign board")
        print("  4 → Export turn .kmz and upload to Discord")
        return

    print(f"  Commander: {session.get('commander_name')}")
    print(f"  Cell:      {session.get('player_cell')}  (place all markers here)")
    print(f"  Theater:   {session.get('theater')}")
    print(f"  Blind:     {session.get('game_format')}")
    print()
    print("  EACH TURN")
    print("  1. Open editor (menu 2)")
    print("  2. Edit under Campaign Live → your cell → tier folder")
    print("  3. File → Save in Google Earth Pro")
    print("  4. Sync (menu 3)")
    print("  5. Export turn (menu 4) → upload .kmz to Discord")
    print()
    print("  Icons: copy style from Unit palettes → paste on new placemarks.")
    print("  Do not add markers under Campaign Board NetworkLinks (read-only).")


def _action_setup() -> int:
    if sys.stdout.isatty():
        subprocess.run(
            ["printf", r"\033[8;52;110t"],
            cwd=PROJECT_ROOT,
            check=False,
        )
    return _run([sys.executable, str(SCRIPTS / "setup_campaign.py")])


def _action_open_editor() -> int:
    return _run([sys.executable, str(SCRIPTS / "open_theater_campaign.py")])


def _action_sync() -> int:
    print("Syncing your saved edits to the campaign board...")
    return _run([sys.executable, str(SCRIPTS / "sync_campaign_live.py"), "--push"])


def _action_export() -> int:
    turn_raw = input("Turn number (e.g. 1): ").strip()
    if not turn_raw.isdigit():
        print("Need a numeric turn number.")
        return 1
    turn = int(turn_raw)
    player = input("Your name (Enter = use commander from setup): ").strip()

    cmd = [
        sys.executable,
        str(SCRIPTS / "package_wargame_client.py"),
        "--turn",
        str(turn),
    ]
    if player:
        cmd.extend(["--player", player])

    code = _run(cmd)
    if code == 0:
        exports = PROJECT_ROOT / "exports"
        print(f"\nUpload the .kmz from: {exports}")
        if sys.platform == "darwin":
            subprocess.run(["open", str(exports)], check=False)
    return code


def _action_instructions() -> int:
    return _run([sys.executable, str(SCRIPTS / "package_wargame_client.py"), "--instructions"])


def _action_install_wizard() -> int:
    return _run([sys.executable, str(SCRIPTS / "player_install_wizard.py")])


def _action_package_icons() -> int:
    cell = input("Cell label for filename (e.g. blue-cell, Enter=shared): ").strip()
    cmd = [sys.executable, str(SCRIPTS / "package_icon_pack.py")]
    if cell:
        cmd.extend(["--cell", cell])
    return _run(cmd)


def _action_import_icons() -> int:
    path = input("Path to icon-pack .zip: ").strip()
    if not path:
        print("Cancelled.")
        return 1
    return _run([sys.executable, str(SCRIPTS / "import_icon_pack.py"), "--zip", path])


def _organizer_menu() -> None:
    while True:
        print()
        print("ORGANIZER TOOLS (not needed every turn)")
        print("  a  Audit globe performance")
        print("  h  Enable hosted mode (HTTPS campaign board)")
        print("  p  Publish to Cloudflare Pages (build + deploy)")
        print("  s  Sanitize campaign board (wipe markers — destructive)")
        print("  b  Back to player menu")
        choice = input("Choice: ").strip().lower()
        if choice in ("b", "back", ""):
            return
        if choice == "a":
            _run([sys.executable, str(SCRIPTS / "audit_globe_performance.py")])
            _pause()
        elif choice == "h":
            print()
            base = input("HTTPS base URL (no trailing slash): ").strip()
            if not base:
                print("Cancelled.")
                continue
            _run(
                [
                    sys.executable,
                    str(SCRIPTS / "configure_hosted_campaign.py"),
                    "--mode",
                    "hosted",
                    "--url",
                    base,
                    "--rebuild",
                ]
            )
            _pause()
        elif choice == "p":
            print()
            print("Sync campaign to disk first if you edited in Google Earth (menu 3).")
            confirm = input("Build portal/dist and deploy to Cloudflare Pages? (y/n): ").strip().lower()
            if confirm not in ("y", "yes"):
                print("Cancelled.")
                continue
            _run([sys.executable, str(SCRIPTS / "publish_portal_site.py"), "--deploy", "--all-games"])
            _pause()
        elif choice == "s":
            confirm = input("This wipes all markers and session. Type YES to confirm: ").strip()
            if confirm != "YES":
                print("Cancelled.")
                continue
            _run([sys.executable, str(SCRIPTS / "sanitize_campaign_board.py"), "--yes"])
            _pause()
        else:
            print("Unknown choice.")


ACTIONS = {
    "setup": _action_setup,
    "open": _action_open_editor,
    "editor": _action_open_editor,
    "sync": _action_sync,
    "export": _action_export,
    "guide": lambda: (_print_play_guide(PROJECT_ROOT), 0)[1],
    "instructions": _action_instructions,
    "install": _action_install_wizard,
    "package-icons": _action_package_icons,
    "import-icons": _action_import_icons,
    "organizer": lambda: (_organizer_menu(), 0)[1],
}


def _dispatch(action: str) -> int:
    key = action.strip().lower()
    if key not in ACTIONS:
        print(f"Unknown action: {action}")
        print(f"Valid: {', '.join(sorted(ACTIONS))}")
        return 1
    result = ACTIONS[key]()
    return result if isinstance(result, int) else 0


def _interactive_loop() -> int:
    while True:
        _print_header(PROJECT_ROOT)
        choice = input("Choice: ").strip().lower()
        if choice in ("q", "quit", "exit"):
            print("Good hunting, Commander.")
            return 0
        if choice == "1":
            _action_setup()
            _pause()
        elif choice == "2":
            _action_open_editor()
            _pause()
        elif choice == "3":
            _action_sync()
            _pause()
        elif choice == "4":
            _action_export()
            _pause()
        elif choice == "5":
            _print_play_guide(PROJECT_ROOT)
            _pause()
        elif choice == "6":
            _action_instructions()
            _pause()
        elif choice in ("i", "install"):
            _action_install_wizard()
            _pause()
        elif choice in ("p", "icons", "package-icons"):
            _action_package_icons()
            _pause()
        elif choice == "m":
            _action_import_icons()
            _pause()
        elif choice in ("o", "org", "organizer"):
            _organizer_menu()
        else:
            print("Pick 1–6, i/p/m, o for organizer, or q to quit.")


def main() -> int:
    parser = argparse.ArgumentParser(description="WOW Commander player menu")
    parser.add_argument(
        "--action",
        choices=sorted(ACTIONS),
        help="Run one action and exit (non-interactive)",
    )
    args = parser.parse_args()

    if args.action:
        return _dispatch(args.action)
    if not sys.stdin.isatty():
        _print_play_guide(PROJECT_ROOT)
        return 0
    return _interactive_loop()


if __name__ == "__main__":
    raise SystemExit(main())
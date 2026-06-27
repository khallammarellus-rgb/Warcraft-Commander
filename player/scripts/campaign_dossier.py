"""Roleplay immersion dossier written after campaign setup."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from campaign_branding import center_block, warcraft_commander_crest
from campaign_tactician_opord import append_gameplay_blocks
from faction_library import faction_by_id
from globe_placement import layer_by_id, load_globe_config
from package_wargame_client import campaign_dir_for_variant
from places_hierarchy import parent_label

DOSSIER_FILENAME = "commander_dossier.txt"

DOSSIER_SAVE_WARNING = """
╔══════════════════════════════════════════════════════════════════╗
║  SAVE THIS FILE — Keep for your records or post to Discord.      ║
║  White-cell may request a copy of your OPORD and force laydown.  ║
╚══════════════════════════════════════════════════════════════════╝
""".strip()


def _theater_label(project_root: Path, theater_id: str) -> str:
    config = load_globe_config(project_root)
    layer = layer_by_id(config, theater_id)
    if layer:
        return parent_label(config, theater_id)
    return theater_id


def _knowledge_display(session: dict) -> str:
    level = session.get("knowledge_level", "casual")
    if level == "tactician":
        return "Tactician"
    mode = session.get("opord_mode")
    if mode == "ai":
        return "Casual (AI-assisted OPORD)"
    if mode == "skip":
        return "Casual (OPORD skipped)"
    return "Casual"


def _operation_order_for_dossier(session: dict) -> str | None:
    opord = (session.get("operation_order") or "").strip()
    if not opord:
        return None
    level = session.get("knowledge_level")
    mode = session.get("opord_mode")
    if level == "tactician" or mode == "ai":
        return append_gameplay_blocks(opord)
    return opord


def build_commander_dossier(project_root: Path, session: dict) -> str:
    crest = warcraft_commander_crest()
    theater = _theater_label(project_root, session["theater"])
    factions = session.get("factions", [])
    faction_labels = []
    for fid in factions:
        entry = faction_by_id(project_root, fid)
        faction_labels.append(entry["label"] if entry else fid)

    lines = [
        DOSSIER_SAVE_WARNING,
        "",
        crest,
        "",
        center_block("FIELD COMMAND DOSSIER"),
        center_block("═" * 28),
        "",
        f"Recorded: {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')}",
        "",
        "DEMOGRAPHICS",
        "────────────",
        f"  Commander:         {session['commander_name']}",
        f"  Force:             {session['force_name']}",
        f"  Echelon:           {session['force_size'].title()}",
        f"  HQ:                {session['hq_name']}",
        f"  Cell:              {session['player_cell']}",
        f"  Theater:           {theater}",
        f"  Blind mode:        {session['game_format']}",
        f"  Factions:          {', '.join(faction_labels) if faction_labels else '(none)'}",
        f"  Executive Officer: {session.get('executive_officer', '(unknown)')}",
        f"  Experience:        {_knowledge_display(session)}",
    ]

    warn_o = (session.get("warn_o") or "").strip()
    if warn_o:
        lines.extend(["", "WARNING ORDER (FROM HIGHER)", "─────────────────────────", warn_o])

    opord = _operation_order_for_dossier(session)
    if opord:
        lines.extend(["", "OPERATION ORDER", "───────────────", opord])
    elif session.get("knowledge_level") == "casual" and session.get("opord_mode") == "skip":
        lines.extend(["", "OPERATION ORDER", "───────────────", "  (Not issued — casual play, OPORD skipped.)"])

    lines.extend(
        [
            "",
            center_block("For the Horde. For the Alliance. For Azeroth."),
            "",
        ]
    )
    return "\n".join(lines)


def write_commander_dossier(
    project_root: Path,
    session: dict,
    *,
    variant: str = "wowcommanderalpha",
) -> Path:
    path = campaign_dir_for_variant(project_root, variant) / DOSSIER_FILENAME
    path.write_text(build_commander_dossier(project_root, session) + "\n", encoding="utf-8")
    return path


def open_commander_dossier(path: Path) -> bool:
    """Open the dossier in the default editor/viewer (macOS open, else best effort)."""
    if not path.is_file():
        return False
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
            return True
        if sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(path)], check=False)
            return True
        if sys.platform == "win32":
            subprocess.run(["start", "", str(path)], shell=True, check=False)
            return True
    except OSError:
        return False
    return False
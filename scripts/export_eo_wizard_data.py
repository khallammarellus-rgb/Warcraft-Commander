#!/usr/bin/env python3
"""Export faction/theater data for the web Executive Officer wizard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_briefing import (
    KNOWLEDGE_LEVEL_INSTRUCTIONS,
    OPORD_MODE_INSTRUCTIONS,
    TUTORIAL_TEXT,
    WARN_O_INSTRUCTIONS_AI,
    WARN_O_INSTRUCTIONS_TACTICIAN,
)
from campaign_hq import FORCE_SIZES, FORCE_SPECS, force_size_preview
from campaign_tactician_opord import TACTICIAN_OPORD_INTRO, TACTICIAN_OPORD_SECTIONS
from faction_library import CATEGORIES, executive_officer, list_factions
from globe_placement import layer_by_id, load_globe_config
from places_hierarchy import core_parent_ids, parent_label
from portal_games import public_games_manifest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    config = load_globe_config(PROJECT_ROOT)
    theaters = []
    for parent_id in core_parent_ids(config):
        layer = layer_by_id(config, parent_id)
        if layer and layer.get("enabled", True):
            theaters.append({"id": parent_id, "label": parent_label(config, parent_id)})

    factions_by_category = {}
    executive_officers: dict[str, str] = {}
    for cat in CATEGORIES:
        entries = []
        for f in list_factions(PROJECT_ROOT, category=cat):
            entries.append({"id": f["id"], "label": f["label"]})
            executive_officers[f["id"]] = executive_officer(PROJECT_ROOT, f["id"])
        factions_by_category[cat] = entries

    tactician = [
        {
            "step_id": s.step_id,
            "title": s.title,
            "paragraph_name": s.paragraph_name,
            "briefing": s.briefing,
            "skeleton": s.skeleton,
        }
        for s in TACTICIAN_OPORD_SECTIONS
    ]

    data = {
        "theaters": theaters,
        "force_sizes": list(FORCE_SIZES),
        "force_specs": {
            size: {
                "strength": spec["strength"],
                "tier": spec["tier"],
                "preview": force_size_preview(size),
            }
            for size, spec in FORCE_SPECS.items()
        },
        "factions_by_category": factions_by_category,
        "executive_officers": executive_officers,
        "games": public_games_manifest(PROJECT_ROOT, base_url="https://wow-commander-campaign.pages.dev")["games"],
        "briefings": {
            "welcome": (
                "Commander — I am your Executive Officer. Together we will stand up your "
                "campaign on the Azeroth battle map. Answer each question; I will handle the rest."
            ),
            "knowledge_level": KNOWLEDGE_LEVEL_INSTRUCTIONS,
            "opord_mode": (
                "OPERATION ORDER APPROACH\n"
                "──────────────────────\n"
                "· Skip OPORD — jump straight into the fight; no orders required now.\n"
                "· Use AI — your Executive Officer drafts a five-paragraph OPORD here on the portal."
            ),
            "tutorial": TUTORIAL_TEXT,
            "xo_briefing_web": (
                "XO BRIEFING\n"
                "───────────\n\n"
                "1. OPEN THE CAMPAIGN\n"
                "   Open your player pack doc_player.kml in Google Earth Pro.\n"
                "   Edit markers in Campaign Live (EDIT HERE), then save in Google Earth Pro.\n\n"
                "2. SYNC YOUR BOARD\n"
                "   Hosted: right-click Campaign Board NetworkLinks → Refresh (~60s).\n"
                "   Local: run Sync Campaign Board after saving in GEP.\n\n"
                "3. SUBMIT YOUR TURN\n"
                "   When it is your cell's turn, upload your KMZ on your table page on this portal.\n"
                "   Use the upload token white-cell issued you.\n\n"
                "4. WHITE CELL & DISCORD\n"
                "   Screenshot your initial laydown to white-cell.\n"
                "   Message white-cell when recon or combat reveals something.\n\n"
                "5. TURN PHASES\n"
                "   Offensive: recon → move → attack (move and attack may be simultaneous)\n"
                "   Defensive: recon → move → reinforce\n\n"
                "6. COMBAT\n"
                "   Attacker rolls 1dN where N = attacking force count.\n"
                "   White-cell may modify rolls.\n\n"
                "7. DAMAGE TRACKING\n"
                "   Record damage in the placemark name. Delete the marker when destroyed.\n\n"
                "Contact white-cell on Discord for further guidance."
            ),
            "warn_o_ai": WARN_O_INSTRUCTIONS_AI,
            "warn_o_tactician": WARN_O_INSTRUCTIONS_TACTICIAN,
            "tactician_intro": TACTICIAN_OPORD_INTRO,
        },
        "tactician_sections": tactician,
        "hosted_portal_base": "https://wow-commander-campaign.pages.dev",
    }

    out = PROJECT_ROOT / "portal" / "public" / "data" / "eo-wizard.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
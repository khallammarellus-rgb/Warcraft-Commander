#!/usr/bin/env python3
"""
Campaign setup wizard — faction library, HQ placemark, blind mode, EO briefing.

  python3 scripts/setup_campaign.py
  python3 scripts/setup_campaign.py --plain
  python3 scripts/setup_campaign.py --cell red-cell
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_branding import WELCOME_BRIEFING, resolve_crest_image, warcraft_commander_crest
from campaign_terminal_image import recommended_terminal_size, resize_terminal
from campaign_briefing import (
    KNOWLEDGE_LEVEL_INSTRUCTIONS,
    OPORD_MODE_INSTRUCTIONS,
    TUTORIAL_TEXT,
    WARN_O_INSTRUCTIONS_AI,
    WARN_O_INSTRUCTIONS_TACTICIAN,
    opord_prompt,
    opord_step_briefing,
)
from campaign_tactician_opord import (
    TACTICIAN_OPORD_INTRO,
    TACTICIAN_OPORD_SECTIONS,
    TACTICIAN_OPORD_STEP_IDS,
    assemble_tactician_opord,
    is_tactician_opord_step,
    tactician_opord_sections_dict,
)
from campaign_dossier import open_commander_dossier, write_commander_dossier
from campaign_tactician_opord import append_gameplay_blocks
from campaign_hq import FORCE_SIZES, force_size_preview, hq_name, hq_tier, theater_center
from campaign_deploy import apply_session_deploy
from campaign_session import finalize_session
from campaign_setup_tui import WizardStep, run_tui
from campaign_visibility import meta_path
from package_wargame_client import campaign_dir_for_variant

OPORD_PROMPT_FILENAME = "opord_prompt.txt"
from faction_library import CATEGORIES, executive_officer, faction_by_id, list_factions
from globe_placement import layer_by_id, load_globe_config
from places_hierarchy import core_parent_ids, parent_label

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def step_visible(step_id: str, answers: dict) -> bool:
    """Whether a wizard step applies to the current answer set."""
    if step_id == "welcome":
        return True
    if step_id == "opord_mode":
        return answers.get("knowledge_level") == "casual"
    if step_id == "operation_order":
        return uses_ai_opord(answers)
    if step_id == "warn_o":
        level = answers.get("knowledge_level")
        if level == "casual" and answers.get("opord_mode") == "skip":
            return False
        return level in ("tactician", "casual")
    if is_tactician_opord_step(step_id):
        return answers.get("knowledge_level") == "tactician"
    if step_id == "campaign_base_url":
        return answers.get("deploy_mode") == "hosted"
    return True


def uses_ai_opord(answers: dict) -> bool:
    return answers.get("knowledge_level") == "casual" and answers.get("opord_mode") == "ai"


def _theater_choices(project_root: Path) -> list[tuple[str, str]]:
    config = load_globe_config(project_root)
    choices: list[tuple[str, str]] = []
    for parent_id in core_parent_ids(config):
        layer = layer_by_id(config, parent_id)
        if layer and layer.get("enabled", True):
            choices.append((parent_id, parent_label(config, parent_id)))
    return choices


def _build_steps(project_root: Path, *, prefill_cell: str | None = None) -> list[WizardStep]:
    theaters = _theater_choices(project_root)
    steps: list[WizardStep] = [
        WizardStep(
            step_id="welcome",
            phase="",
            title="Warcraft: Commander",
            briefing=WELCOME_BRIEFING,
            kind="choice",
            choices=[("begin", "Begin campaign setup")],
        ),
        WizardStep(
            step_id="theater",
            phase="Phase A",
            title="Campaign map",
            briefing=(
                "Pick the landmass where this battle takes place.\n"
                "Your HQ placemark will be placed at the center of this map."
            ),
            kind="choice",
            choices=theaters,
        ),
        WizardStep(
            step_id="game_format",
            phase="Phase A",
            title="Blind mode",
            briefing=(
                "Blind mode controls who sees enemy markers on turn export.\n\n"
                "· no-blind — both sides see everything\n"
                "· single-blind — red-cell sees all; blue-cell is filtered\n"
                "· double-blind — both sides receive filtered exports"
            ),
            kind="choice",
            choices=[
                ("no-blind", "no-blind"),
                ("single-blind", "single-blind"),
                ("double-blind", "double-blind"),
            ],
        ),
        WizardStep(
            step_id="deploy_mode",
            phase="Phase A",
            title="Campaign sync",
            briefing=(
                "How will players receive updated campaign markers between turns?\n\n"
                "· Local — campaign files stay on each machine; export .kmz turns via Discord\n"
                "· Hosted — Cloudflare Pages serves role-filtered views; players refresh NetworkLinks in GEP"
            ),
            kind="choice",
            choices=[
                ("local", "Local — Discord KMZ turn packages"),
                ("hosted", "Hosted — HTTPS campaign board (GM uploads KML)"),
            ],
        ),
        WizardStep(
            step_id="campaign_base_url",
            phase="Phase A",
            title="Hosted base URL",
            briefing=(
                "HTTPS URL for your Cloudflare Pages campaign portal.\n"
                "Example: https://wow-commander.pages.dev (no trailing slash).\n"
                "Players load <base>/view/<cell>/<theater>.kml; organizer master at <base>/campaign/<theater>.kml"
            ),
            kind="text",
            text_placeholder="https://your-host.example/wowcommander",
        ),
    ]

    if prefill_cell:
        steps.append(
            WizardStep(
                step_id="player_cell",
                phase="Phase A",
                title="Your cell",
                briefing=f"Cell pre-filled as {prefill_cell}. Confirm to continue.",
                kind="choice",
                choices=[(prefill_cell, prefill_cell)],
            )
        )
    else:
        steps.append(
            WizardStep(
                step_id="player_cell",
                phase="Phase A",
                title="Your cell",
                briefing=(
                    "Which cell are you?\n\n"
                    "Blind play filters by cell folder — not WoW faction.\n"
                    "Place all units under red-cell or blue-cell in the active theater."
                ),
                kind="choice",
                choices=[("red-cell", "red-cell"), ("blue-cell", "blue-cell")],
            )
        )

    steps.append(
        WizardStep(
            step_id="faction_menu",
            phase="Phase A",
            title="Choose faction category",
            briefing=(
                "Browse factions by category — Alliance, Horde, Antagonist, or Neutral.\n"
                "You can pick from any category (not only Alliance).\n"
                "Add as many factions as you need, then choose Done picking factions."
            ),
            kind="faction_menu",
            choices=[
                ("Alliance", "Browse Alliance factions"),
                ("Horde", "Browse Horde factions"),
                ("Antagonist", "Browse Antagonist factions"),
                ("Neutral", "Browse Neutral factions"),
                ("done", "Done picking factions"),
            ],
        )
    )
    steps.append(
        WizardStep(
            step_id="faction_pick",
            phase="Phase A",
            title="Pick a faction",
            briefing="Select a faction from this category, or go back to the category menu.",
            kind="faction_pick",
        )
    )

    steps.extend(
        [
            WizardStep(
                step_id="commander_name",
                phase="Phase B",
                title="Commander name",
                briefing="How shall the Executive Officer address you?",
                kind="text",
                text_placeholder="Commander name",
            ),
            WizardStep(
                step_id="force_name",
                phase="Phase B",
                title="Force name",
                briefing="Name of your command (e.g. Royal Forsaken Host).",
                kind="text",
                text_placeholder="Force name",
            ),
            WizardStep(
                step_id="force_size",
                phase="Phase B",
                title="Force size",
                briefing=(
                    "Force size sets HQ name, default strength, and tier folder.\n"
                    "Highlight each option on the right (↑↓) to preview that echelon."
                ),
                kind="choice",
                choices=[(s, s.title()) for s in FORCE_SIZES],
            ),
            WizardStep(
                step_id="knowledge_level",
                phase="Phase C",
                title="Experience level",
                briefing=KNOWLEDGE_LEVEL_INSTRUCTIONS,
                kind="choice",
                choices=[
                    ("tactician", "Tactician — EO guides my OPORD"),
                    ("casual", "Casual — keep it simple"),
                ],
            ),
            WizardStep(
                step_id="opord_mode",
                phase="Phase C",
                title="Operation order approach",
                briefing=OPORD_MODE_INSTRUCTIONS,
                kind="choice",
                choices=[
                    ("skip", "Skip OPORD for now"),
                    ("ai", "Use AI to draft my OPORD"),
                ],
            ),
            WizardStep(
                step_id="tutorial_completed",
                phase="Phase C",
                title="EO briefing",
                briefing=TUTORIAL_TEXT,
                kind="choice",
                choices=[("yes", "Walk me through the plan"), ("no", "Skip the talk")],
            ),
            WizardStep(
                step_id="warn_o",
                phase="Phase C",
                title="Warn O from white-cell",
                briefing=WARN_O_INSTRUCTIONS_AI,
                kind="text",
                text_placeholder="Paste Warn O from white-cell (leave empty to skip)",
                text_multiline=True,
            ),
            WizardStep(
                step_id="operation_order",
                phase="Phase C",
                title="Operation order (AI)",
                briefing="",
                kind="text",
                text_placeholder="Paste AI OPORD here (leave empty to skip)",
                text_multiline=True,
            ),
        ]
    )

    tactician_insert = next(
        i for i, s in enumerate(steps) if s.step_id == "operation_order"
    )
    tactician_steps: list[WizardStep] = []
    for index, section in enumerate(TACTICIAN_OPORD_SECTIONS):
        briefing = section.briefing if index > 0 else f"{TACTICIAN_OPORD_INTRO}\n\n{section.briefing}"
        tactician_steps.append(
            WizardStep(
                step_id=section.step_id,
                phase="Phase C · OPORD",
                title=section.title,
                briefing=briefing,
                kind="text",
                text_placeholder=f"Draft {section.paragraph_name} (Confirm when ready)",
                text_multiline=True,
                text_skeleton=section.skeleton,
            )
        )
    steps[tactician_insert:tactician_insert] = tactician_steps

    steps.extend(
        [
            WizardStep(
                step_id="review_confirm",
                phase="Review",
                title="Confirm your setup",
                briefing="Review your selections on the left, then confirm or change below.",
                kind="choice",
                choices=[
                    ("finalize", "Yes — I'm sure, finalize campaign setup"),
                    ("__edit__", "No — review and change a selection"),
                ],
            ),
            WizardStep(
                step_id="review_edit",
                phase="Review",
                title="What would you like to change?",
                briefing=(
                    "Pick any step to revisit. Your previous answer is restored when possible.\n"
                    "After you confirm the new choice, you return to the full review screen."
                ),
                kind="review_edit",
            ),
        ]
    )

    return steps


def faction_pick_choices_for_category(project_root: Path, category: str) -> list[tuple[str, str]]:
    factions = list_factions(project_root, category=category)
    return [(f["id"], f["label"]) for f in factions] + [
        ("__back__", "← Back to category menu (no pick)"),
    ]


def opord_prompt_for_answers(project_root: Path, answers: dict) -> str:
    factions = answers.get("factions") or []
    primary_id = factions[0] if factions else "humans"
    entry = faction_by_id(project_root, primary_id)
    faction_label_str = entry["label"] if entry else primary_id
    force_size = answers.get("force_size", "battalion")
    warn_o = answers.get("warn_o")
    return opord_prompt(
        force_size=force_size,
        faction_label=faction_label_str,
        warn_o=warn_o if warn_o else None,
    )


def faction_label(project_root: Path, faction_id: str) -> str:
    entry = faction_by_id(project_root, faction_id)
    return entry["label"] if entry else faction_id


def _display_value(project_root: Path, step_id: str, value, steps: list[WizardStep]) -> str:
    if step_id == "theater":
        config = load_globe_config(project_root)
        layer = layer_by_id(config, value)
        return layer.get("label", value) if layer else str(value)
    if step_id == "tutorial_completed":
        return "Walk through briefing" if value == "yes" else "Skipped briefing"
    if step_id == "knowledge_level":
        return "Tactician" if value == "tactician" else "Casual"
    if step_id == "opord_mode":
        return "Use AI" if value == "ai" else "Skip OPORD"
    if is_tactician_opord_step(step_id):
        if not value:
            return "(not drafted)"
        text = str(value).strip()
        return text[:60] + ("…" if len(text) > 60 else "")
    if step_id in ("warn_o", "operation_order"):
        if not value:
            return "(none)"
        text = str(value).strip()
        return text[:80] + ("…" if len(text) > 80 else "")
    if step_id == "force_size":
        return str(value).title()
    if step_id == "deploy_mode":
        return "Hosted (HTTPS refresh)" if value == "hosted" else "Local (Discord KMZ)"
    if step_id == "campaign_base_url":
        return str(value).strip() or "(missing)"
    return str(value)


def format_review_summary(
    project_root: Path,
    answers: dict,
    steps: list[WizardStep],
) -> str:
    lines = [
        "REVIEW YOUR CAMPAIGN SETUP",
        "══════════════════════════",
        "",
    ]
    factions = _collect_factions_from_answers(answers, steps)
    faction_labels = []
    for fid in factions:
        entry = faction_by_id(project_root, fid)
        faction_labels.append(entry["label"] if entry else fid)

    force_size = answers.get("force_size", "battalion")
    force_name = answers.get("force_name", "")
    hq = hq_name(force_size, force_name=force_name) if force_name else "(pending)"

    field_order = [
        ("theater", "Campaign map"),
        ("game_format", "Blind mode"),
        ("deploy_mode", "Campaign sync"),
        ("campaign_base_url", "Hosted URL"),
        ("player_cell", "Your cell"),
        ("commander_name", "Commander"),
        ("force_name", "Force name"),
        ("force_size", "Force size"),
        ("knowledge_level", "Experience"),
        ("opord_mode", "OPORD approach"),
        ("tutorial_completed", "EO briefing"),
        ("warn_o", "Warn O"),
    ]
    for section in TACTICIAN_OPORD_SECTIONS:
        field_order.append((section.step_id, f"OPORD {section.title}"))
    field_order.append(("operation_order", "Operation order (AI)"))
    for step_id, label in field_order:
        if step_id not in answers:
            continue
        if not step_visible(step_id, answers):
            continue
        lines.append(f"  {label + ':':<18} {_display_value(project_root, step_id, answers[step_id], steps)}")

    if faction_labels:
        lines.append(f"  {'Factions:':<18} {', '.join(faction_labels)}")
        primary = factions[0] if factions else None
        if primary:
            eo = executive_officer(project_root, primary)
            lines.append(f"  {'Executive Officer:':<18} {eo}")

    lines.extend(
        [
            "",
            f"  {'HQ placemark:':<18} {hq}",
            "  HQ location:      Center of chosen landmass",
            "",
            "Are you sure? Finalizing writes game_session.json, campaign_meta.json,",
            "commander_dossier.txt, injects HQ + org folders + OPORD placemarks, and rebuilds campaign_live.kml.",
            "",
            "  a — finalize (if 'Yes' is selected)",
            "  b — go back one step",
            "  Pick 'No — review and change' to edit any selection.",
        ]
    )
    return "\n".join(lines)


def _collect_factions_from_answers(answers: dict, steps: list[WizardStep]) -> list[str]:
    factions = answers.get("factions")
    if isinstance(factions, list):
        return list(factions)
    return []


def _answers_to_session(project_root: Path, answers: dict, steps: list[WizardStep]) -> dict:
    factions = _collect_factions_from_answers(answers, steps)
    if not factions:
        raise ValueError("Pick at least one faction")

    primary_id = factions[0]
    if len(factions) > 1:
        primary_id = factions[0]

    theater = answers["theater"]
    force_size = answers["force_size"]
    force_name = answers["force_name"]
    coords = theater_center(project_root, theater)

    primary = faction_by_id(project_root, primary_id)
    primary_label = primary["label"] if primary else primary_id

    tutorial = answers.get("tutorial_completed", "no")
    warn_o_text = answers.get("warn_o")
    if warn_o_text is not None and not str(warn_o_text).strip():
        warn_o_text = None
    knowledge_level = answers.get("knowledge_level", "casual")
    opord_mode = answers.get("opord_mode")
    opord_sections: dict[str, str | None] | None = None

    if knowledge_level == "tactician":
        opord_mode = None
        opord_sections = tactician_opord_sections_dict(answers)
        opord_text = assemble_tactician_opord(answers) or None
    else:
        opord_text = answers.get("operation_order")
        if opord_text is not None and not str(opord_text).strip():
            opord_text = None
        if opord_mode == "skip":
            warn_o_text = None
            opord_text = None
        elif opord_text:
            opord_text = append_gameplay_blocks(opord_text)

    deploy_mode = answers.get("deploy_mode", "local")
    base_url = (answers.get("campaign_base_url") or "").strip().rstrip("/")
    if deploy_mode != "hosted":
        base_url = ""

    return {
        "game_format": answers["game_format"],
        "campaign_deploy_mode": deploy_mode,
        "campaign_base_url": base_url,
        "theater": theater,
        "player_cell": answers["player_cell"],
        "commander_name": answers["commander_name"],
        "force_name": force_name,
        "force_size": force_size,
        "hq_name": hq_name(force_size, force_name=force_name),
        "hq_coords": [coords[0], coords[1]],
        "factions": factions,
        "primary_faction": primary_id,
        "executive_officer": executive_officer(project_root, primary_id),
        "knowledge_level": knowledge_level,
        "opord_mode": opord_mode,
        "tutorial_completed": tutorial == "yes",
        "warn_o": warn_o_text,
        "operation_order": opord_text,
        "opord_sections": opord_sections,
        "notes": answers.get("notes", {}),
    }


def _write_campaign_meta(project_root: Path, game_format: str, *, variant: str = "wowcommanderalpha") -> None:
    path = meta_path(campaign_dir_for_variant(project_root, variant))
    data = {"game_format": game_format, "reveal_radius_km": 1.0, "reveal_persistent": True}
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _print_summary(
    session: dict,
    *,
    dossier_path: Path | None = None,
    dossier_opened: bool = False,
) -> None:
    print("\n" + warcraft_commander_crest())
    print("\n" + "=" * 60)
    print("CAMPAIGN SETUP COMPLETE")
    print("=" * 60)
    print(f"  Map:        {session['theater']}")
    print(f"  Cell:       {session['player_cell']}")
    print(f"  Blind:      {session['game_format']}")
    print(f"  Commander:  {session['commander_name']}")
    print(f"  Force:      {session['force_name']}")
    print(f"  Factions:   {', '.join(session['factions'])}")
    print(f"  HQ:         {session['hq_name']}")
    print(f"  EO:         {session['executive_officer']}")
    knowledge = session.get("knowledge_level", "casual")
    org_note = (
        "Units + Operational Graphics per tier"
        if knowledge == "casual"
        else f"Echelon org tree in {session['force_size'].title()} tier"
    )
    print(f"\n  HQ path: Campaign Package → {session['player_cell']} → "
          f"{hq_tier(session['force_size'])} → {session['hq_name']}")
    print(f"  Org tree:  {org_note}")
    if session.get("operation_order") or session.get("warn_o"):
        print(f"  Orders:    Campaign Package → {session['player_cell']} → Orders/")
    print(f"  Palettes:  Unit palettes/ (editor only, not exported)")
    deploy = session.get("campaign_deploy_mode", "local")
    if deploy == "hosted" and session.get("campaign_base_url"):
        cell = session.get("player_cell", "red-cell")
        base = session["campaign_base_url"].rstrip("/")
        print(f"  Hosted:    {base}/view/{cell}/<theater>.kml (your cell)")
        print(f"             {base}/campaign/<theater>.kml (organizer master)")
        print("             Deploy: python3 scripts/publish_portal_site.py --deploy")
    else:
        print("  Sync:      Local — use WOW Commander.command (menu 3–4)")
    if dossier_path is not None:
        print(f"  Dossier:   {dossier_path}")
        if dossier_opened:
            print("             (opened — save for records or post to Discord)")
        else:
            print("             (open this file — save for records or post to Discord)")
    print("\n  NEXT STEPS")
    print("  Double-click scripts/WOW Commander.command — one menu for everything:")
    print("  2. Open editor — place units (copy style from Unit palettes → your cell)")
    print("  3. Save in Google Earth Pro → Sync")
    print("  4. Export turn (uses your cell + blind mode from session)")
    print("  4. Optional: Audit Globe Performance.command before heavy laydown")
    print("\n  Dossier saved — post to Discord or keep for records.")
    print("=" * 60 + "\n")


def _plain_prompt_step(step: WizardStep, answers: dict) -> None:
    title = step.title if step.step_id != "welcome" else ""
    phase = f"[{step.phase}] " if step.phase else ""
    print(f"\n{phase}{title}".rstrip())
    if step.step_id == "welcome":
        print(warcraft_commander_crest())
        print()
        print(step.briefing)
    elif step.step_id == "review_confirm":
        print(format_review_summary(PROJECT_ROOT, answers, _PLAIN_STEPS))
    elif step.step_id == "warn_o":
        if answers.get("knowledge_level") == "tactician":
            print(WARN_O_INSTRUCTIONS_TACTICIAN)
        else:
            print(WARN_O_INSTRUCTIONS_AI)
    elif step.step_id == "operation_order" and uses_ai_opord(answers):
        prompt = opord_prompt_for_answers(PROJECT_ROOT, answers)
        backup = campaign_dir_for_variant(PROJECT_ROOT, "wowcommanderalpha") / OPORD_PROMPT_FILENAME
        backup.write_text(prompt + "\n", encoding="utf-8")
        print(opord_step_briefing(prompt))
        print(f"\n  (Prompt also saved to {backup})")
    elif is_tactician_opord_step(step.step_id):
        print(step.briefing)
        warn_o = answers.get("warn_o")
        if warn_o and str(warn_o).strip():
            print("\n  Warn O reference (from higher):")
            print("  " + str(warn_o).strip().replace("\n", "\n  "))
    else:
        print(step.briefing)

    if step.kind == "faction_menu":
        for idx, (_val, label) in enumerate(step.choices, 1):
            print(f"  {idx}. {label}")
        picked = answers.get("factions", [])
        if picked:
            labels = [faction_label(PROJECT_ROOT, f) for f in picked]
            print(f"  (selected so far: {', '.join(labels)})")
        while True:
            raw = input("Choice number: ").strip()
            try:
                pick = int(raw) - 1
                if 0 <= pick < len(step.choices):
                    choice = step.choices[pick][0]
                    if choice == "done":
                        if not answers.get("factions"):
                            print("Pick at least one faction before continuing.")
                            continue
                        answers[step.step_id] = "done"
                    else:
                        answers["_faction_category"] = choice
                    break
            except ValueError:
                pass
            print("Invalid — try again.")
    elif step.kind == "faction_pick":
        category = answers.get("_faction_category", "Alliance")
        print(f"Category: {category}")
        pick_choices = faction_pick_choices_for_category(PROJECT_ROOT, category)
        for idx, (_val, label) in enumerate(pick_choices, 1):
            print(f"  {idx}. {label}")
        while True:
            raw = input("Choice number: ").strip()
            try:
                pick = int(raw) - 1
                if 0 <= pick < len(pick_choices):
                    choice = pick_choices[pick][0]
                    if choice != "__back__":
                        factions = answers.setdefault("factions", [])
                        if choice not in factions:
                            factions.append(choice)
                    break
            except ValueError:
                pass
            print("Invalid — try again.")
    elif step.kind == "choice":
        if step.step_id == "force_size":
            force_name = answers.get("force_name")
            print("  HQ examples per echelon:")
            for idx, (val, label) in enumerate(step.choices, 1):
                print(f"  {idx}. {label} — {force_size_preview(val, force_name=force_name)}")
        else:
            for idx, (_val, label) in enumerate(step.choices, 1):
                print(f"  {idx}. {label}")
        while True:
            raw = input("Choice number: ").strip()
            try:
                pick = int(raw) - 1
                if 0 <= pick < len(step.choices):
                    answers[step.step_id] = step.choices[pick][0]
                    break
            except ValueError:
                pass
            print("Invalid — try again.")
    elif step.kind == "review_edit":
        edit_choices: list[tuple[str, str]] = []
        for idx, s in enumerate(_PLAIN_STEPS):
            if s.step_id in ("review_confirm", "review_edit", "faction_pick"):
                continue
            if not step_visible(s.step_id, answers):
                continue
            edit_choices.append((str(idx), s.title))
        for n, (_val, title) in enumerate(edit_choices, 1):
            print(f"  {n}. Change: {title}")
        print(f"  {len(edit_choices) + 1}. Back to review (keep selections)")
        while True:
            raw = input("Choice number: ").strip()
            try:
                pick = int(raw) - 1
                if pick == len(edit_choices):
                    answers[step.step_id] = "back"
                    break
                if 0 <= pick < len(edit_choices):
                    answers[step.step_id] = edit_choices[pick][0]
                    break
            except ValueError:
                pass
            print("Invalid — try again.")
    elif step.kind == "text":
        if step.step_id == "warn_o":
            print("\n  (Leave empty if white-cell has not issued a Warn O yet.)")
        if step.step_id == "operation_order" and uses_ai_opord(answers):
            print("\n  (Copy the prompt above before pasting your OPORD back.)")
        existing = answers.get(step.step_id, "")
        optional = {step.step_id} | set(TACTICIAN_OPORD_STEP_IDS) | {"operation_order", "warn_o"}
        if is_tactician_opord_step(step.step_id) and step.text_multiline:
            print("\n  (Multi-line draft. Type a single . on its own line to finish.)")
            if existing:
                print(existing)
            elif step.text_skeleton:
                print(step.text_skeleton)
            lines: list[str] = []
            while True:
                line = input()
                if line.strip() == ".":
                    break
                lines.append(line)
            val = "\n".join(lines).strip()
            answers[step.step_id] = val or None
        else:
            hint = f" [{existing}]" if existing else ""
            val = input(f"{step.text_placeholder}{hint}: ").strip()
            if val or step.step_id in optional:
                answers[step.step_id] = val or None


_PLAIN_STEPS: list[WizardStep] = []


def _run_plain(steps: list[WizardStep], project_root: Path) -> dict:
    global _PLAIN_STEPS
    _PLAIN_STEPS = steps
    answers: dict = {}
    review_index = next(i for i, s in enumerate(steps) if s.step_id == "review_confirm")
    edit_index = next(i for i, s in enumerate(steps) if s.step_id == "review_edit")
    faction_menu_index = next(i for i, s in enumerate(steps) if s.step_id == "faction_menu")
    faction_pick_index = next(i for i, s in enumerate(steps) if s.step_id == "faction_pick")
    i = 0
    editing_from_review = False
    while i < len(steps):
        step = steps[i]
        if not step_visible(step.step_id, answers):
            i += 1
            continue
        if step.step_id == "faction_menu":
            _plain_prompt_step(step, answers)
            if answers.get("faction_menu") == "done":
                i = faction_pick_index + 1
            else:
                i = faction_pick_index
            continue
        if step.step_id == "faction_pick":
            _plain_prompt_step(step, answers)
            i = faction_menu_index
            continue
        if step.step_id == "review_edit":
            _plain_prompt_step(step, answers)
            target = answers.get("review_edit", "back")
            if target == "back":
                i = review_index
                continue
            i = int(target)
            editing_from_review = True
            continue

        _plain_prompt_step(step, answers)

        if editing_from_review:
            editing_from_review = False
            i = review_index
            continue

        if step.step_id == "review_confirm":
            choice = answers.get("review_confirm")
            if choice == "__edit__":
                i = edit_index
                continue
            if choice == "finalize":
                while True:
                    sure = input("\nFinalize campaign setup? (yes/no): ").strip().lower()
                    if sure in ("yes", "y"):
                        return answers
                    if sure in ("no", "n"):
                        i = edit_index
                        break
                    print("Please answer yes or no.")
                continue

        i += 1

    return answers


def _on_complete(answers: dict, steps: list[WizardStep]) -> None:
    session = _answers_to_session(PROJECT_ROOT, answers, steps)
    _write_campaign_meta(PROJECT_ROOT, session["game_format"])
    finalize_session(PROJECT_ROOT, session)
    try:
        deploy_result = apply_session_deploy(PROJECT_ROOT, session, rebuild=True)
        if deploy_result.get("rebuild_exit_code", 0) != 0:
            print(
                "Warning: doc.kml rebuild exited with errors — "
                "run: python3 scripts/build_world_globe.py --kml-only --variant wowcommanderalpha",
                file=sys.stderr,
            )
        if session.get("campaign_deploy_mode") == "hosted":
            from campaign_deploy import apply_hosted_post_setup

            post = apply_hosted_post_setup(PROJECT_ROOT, rebuild_views=True)
            if post.get("views_built"):
                print(f"Hosted views built under portal/dist ({post['views_built']} files).")
    except ValueError as exc:
        print(f"Deploy config not applied: {exc}", file=sys.stderr)
    dossier_path = write_commander_dossier(PROJECT_ROOT, session)
    opened = open_commander_dossier(dossier_path)
    _print_summary(session, dossier_path=dossier_path, dossier_opened=opened)


def main() -> int:
    parser = argparse.ArgumentParser(description="WoW Commander campaign setup wizard")
    parser.add_argument("--plain", action="store_true", help="Simple prompts (no Textual TUI)")
    parser.add_argument("--cell", choices=["red-cell", "blue-cell"], help="Pre-fill player cell")
    args = parser.parse_args()

    steps = _build_steps(PROJECT_ROOT, prefill_cell=args.cell)

    use_plain = args.plain or not sys.stdout.isatty() or os.environ.get("TEXTUAL") == "0"
    crest_image = resolve_crest_image(PROJECT_ROOT)

    if use_plain:
        try:
            answers = _run_plain(steps, PROJECT_ROOT)
            _on_complete(answers, steps)
        except (ValueError, KeyError) as exc:
            print(f"Setup failed: {exc}", file=sys.stderr)
            return 1
        return 0

    cols, rows = recommended_terminal_size(crest_image)
    resize_terminal(cols, rows)

    completed: dict = {}

    def handle_complete(answers: dict) -> None:
        nonlocal completed
        completed = answers
        try:
            _on_complete(answers, steps)
        except (ValueError, KeyError) as exc:
            print(f"Setup failed: {exc}", file=sys.stderr)

    result = run_tui(
        steps,
        handle_complete,
        review_formatter=lambda answers: format_review_summary(PROJECT_ROOT, answers, steps),
        faction_pick_builder=lambda cat: faction_pick_choices_for_category(PROJECT_ROOT, cat),
        faction_label_fn=lambda fid: faction_label(PROJECT_ROOT, fid),
        opord_prompt_fn=lambda answers: opord_prompt_for_answers(PROJECT_ROOT, answers),
        opord_prompt_backup=(
            campaign_dir_for_variant(PROJECT_ROOT, "wowcommanderalpha") / OPORD_PROMPT_FILENAME
        ),
        step_visible_fn=lambda step_id, answers: step_visible(step_id, answers),
        uses_ai_opord_fn=lambda answers: uses_ai_opord(answers),
        welcome_crest_fn=warcraft_commander_crest,
        crest_image_path=crest_image,
        eo_prefix_fn=lambda answers: (
            f"{executive_officer(PROJECT_ROOT, answers['factions'][0])}"
            if answers.get("factions")
            else ""
        ),
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
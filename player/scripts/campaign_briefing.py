"""Executive Officer briefing text for campaign setup."""

from __future__ import annotations

TUTORIAL_TEXT = """
EXECUTIVE OFFICER BRIEFING
──────────────────────────

1. OPEN THE CAMPAIGN
   Double-click scripts/Open Campaign Editor.command
   Edit in Campaign Live (EDIT HERE) → save in Google Earth Pro.

2. SYNC YOUR MARKERS
   After saving: scripts/Sync Campaign Board.command
   (or: python3 scripts/sync_campaign_live.py --push)

3. EXPORT YOUR TURN
   scripts/Export Turn.command with your cell role
   (red-cell or blue-cell) for blind play.

4. WHITE-CELL / DISCORD
   Screenshot your initial force laydown to white-cell always.
   Message white-cell for adjudication when recon or combat reveals something.

5. TURN PHASES
   Offensive: recon → move → attack (move and attack may be simultaneous)
   Defensive: recon → move → reinforce

6. COMBAT
   Attacker rolls 1dN where N = attacking force count.
   Example: 50 vs 100 → attacker rolls 1d50 damage.
   White-cell may modify rolls.

7. DAMAGE TRACKING
   Record damage in the placemark name via Properties.
   Delete the marker when the unit is destroyed.

Contact white-cell on Discord for further guidance.
""".strip()


OPORD_BODY_TEMPLATE = (
    "I need a military style five paragraph operational order for my "
    "{faction} {unit_size} force complete with tactical tasks, "
    "a commander's endstate, center of gravity, and critical vulnerability. "
    "This is for a wargame done in the context, landscape, and fanfiction "
    "of World of Warcraft Lore."
)


def opord_prompt(
    *,
    force_size: str,
    faction_label: str,
    warn_o: str | None = None,
) -> str:
    body = OPORD_BODY_TEMPLATE.format(faction=faction_label, unit_size=force_size)
    warn_o_text = (warn_o or "").strip()
    if warn_o_text:
        return f"This is the Warn O from higher. {warn_o_text}\n\n{body}"
    return body


KNOWLEDGE_LEVEL_INSTRUCTIONS = """
EXPERIENCE LEVEL
────────────────
· Tactician — your Executive Officer guides you paragraph-by-paragraph.
· Casual — simpler flow; you may skip the OPORD or let AI draft one for you.
""".strip()


OPORD_MODE_INSTRUCTIONS = """
OPERATION ORDER APPROACH
──────────────────────
· Skip OPORD — jump straight into the fight; no orders required now.
· Use AI — copy a prompt on the next steps and paste the AI draft back here.
""".strip()


WARN_O_INSTRUCTIONS_AI = """
WARN O FROM WHITE-CELL (optional)
─────────────────────────────────
Paste the Warn O (warning order) from white-cell / higher headquarters.

This will be included at the top of the AI prompt on the next step when you
copy it. Leave empty if you do not have a Warn O yet.
""".strip()


WARN_O_INSTRUCTIONS_TACTICIAN = """
WARN O FROM WHITE-CELL (optional)
─────────────────────────────────
Paste the Warn O (warning order) from white-cell / higher headquarters.

Your Executive Officer will guide you through each OPORD paragraph next.
If you paste a Warn O here, it will stay visible as a reference pane while
you draft each section. Leave empty if you do not have a Warn O yet.
""".strip()


OPORD_INSTRUCTIONS_AI = """
OPERATION ORDER (optional)
──────────────────────────
1. Copy the AI prompt below (Copy AI prompt button or press c).
   Also saved to campaign/opord_prompt.txt if clipboard is unavailable.
2. Paste it into your AI assistant.
3. Paste the AI's five-paragraph OPORD back in the text field.

Use Confirm when finished, or leave empty to skip.
""".strip()


def opord_step_briefing(prompt: str) -> str:
    """Briefing body for casual AI operation_order step — includes the copyable prompt."""
    return (
        f"{OPORD_INSTRUCTIONS_AI}\n\n"
        "AI PROMPT TO COPY\n"
        "─────────────────\n"
        f"{prompt}\n"
        "─────────────────"
    )
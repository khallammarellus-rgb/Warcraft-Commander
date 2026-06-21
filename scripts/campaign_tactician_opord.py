"""Executive Officer–guided five-paragraph OPORD for Tactician players."""

from __future__ import annotations

from dataclasses import dataclass

TACTICIAN_OPORD_INTRO = """
EXECUTIVE OFFICER — OPERATION ORDER
──────────────────────────────────
Commander, I will walk you through each paragraph of your operation order.
Use the Warn O from higher (if provided) as reference on the left while
you draft each section on the right.

Work one section at a time. Confirm when each paragraph is ready.
""".strip()


@dataclass(frozen=True)
class TacticianOpordSection:
    step_id: str
    title: str
    paragraph_name: str
    briefing: str
    skeleton: str


GAMEPLAY_ADMIN_BLOCK = """
GAMEPLAY — ADMINISTRATION
───────────────────────
Turn phases:
  · Offensive: recon → move → attack (move and attack may be simultaneous)
  · Defensive: recon → move → reinforce

Google Earth Pro:
  · Edit markers in Campaign Live (EDIT HERE), then save in Google Earth Pro.
  · Sync: scripts/Sync Campaign Board.command
  · Export your turn: scripts/Export Turn.command (red-cell or blue-cell)

Command scripts (project scripts/ folder):
  · Open Campaign Editor.command — open the live board
  · Sync Campaign Board.command — push your edits
  · Export Turn.command — blind export for your cell
  · Setup Campaign.command — re-run this wizard if needed

Damage: record in placemark name; delete marker when destroyed.
Combat: attacker rolls 1dN where N = attacking force count.
""".strip()


GAMEPLAY_SIGNAL_BLOCK = """
GAMEPLAY — SIGNAL
─────────────────
Submit turns and coordinate play on Discord with white-cell.

  · Screenshot your initial force laydown to white-cell always.
  · Message white-cell when recon or combat reveals enemy positions.
  · White-cell adjudicates fog-of-war, combat, and disputes.

Export your filtered turn KML after each move phase so opponents only
see what blind rules allow.
""".strip()


def _sections() -> tuple[TacticianOpordSection, ...]:
    return (
        TacticianOpordSection(
            step_id="opord_orientation",
            title="1 — Orientation",
            paragraph_name="Orientation",
            briefing=(
                "EXECUTIVE OFFICER\n"
                "─────────────────\n"
                "Orientation orients the reader to the area and time.\n\n"
                "In the most basic sense, state:\n"
                "  · Where the fight is (area of operations)\n"
                "  · When it takes place (time zone / date-time group)\n"
                "  · Who the key friendly and enemy forces are at a glance\n\n"
                "Keep it short — a few sentences that frame the battlespace."
            ),
            skeleton=(
                "Orientation\n"
                "───────────\n"
                "Area of operations:\n"
                "\n"
                "Time zone / date-time group:\n"
                "\n"
                "Key friendly forces:\n"
                "\n"
                "Key enemy forces:\n"
            ),
        ),
        TacticianOpordSection(
            step_id="opord_situation",
            title="2 — Situation",
            paragraph_name="Situation",
            briefing=(
                "EXECUTIVE OFFICER\n"
                "─────────────────\n"
                "Situation describes factors that affect your mission — enemy,\n"
                "friendlies, terrain, and civilians. Use the Warn O reference\n"
                "on the left if white-cell issued one.\n\n"
                "Cover each item below. Delete prompt lines you do not need."
            ),
            skeleton=(
                "Situation\n"
                "─────────\n"
                "Enemy:\n"
                "  Size:\n"
                "  Location:\n"
                "\n"
                "Adjacent units:\n"
                "\n"
                "Civil considerations:\n"
                "\n"
                "Friendly unit HQ location:\n"
                "\n"
                "All friendly units under command:\n"
            ),
        ),
        TacticianOpordSection(
            step_id="opord_mission",
            title="3 — Mission",
            paragraph_name="Mission",
            briefing=(
                "EXECUTIVE OFFICER\n"
                "─────────────────\n"
                "Mission is the task and purpose — who, what, when, where, why.\n\n"
                "Write a clear two-sentence mission statement:\n"
                "  · Sentence 1 — the task (what you will do)\n"
                "  · Sentence 2 — the purpose (why it matters)"
            ),
            skeleton=(
                "Mission\n"
                "───────\n"
                "Task:\n"
                "\n"
                "Purpose:\n"
                "\n"
                "(Combine into one two-sentence mission statement below)\n"
                "\n"
                "Mission statement:\n"
            ),
        ),
        TacticianOpordSection(
            step_id="opord_execution",
            title="4 — Execution",
            paragraph_name="Execution",
            briefing=(
                "EXECUTIVE OFFICER\n"
                "─────────────────\n"
                "Execution is how you will accomplish the mission.\n\n"
                "Include:\n"
                "  · Commander's intent — purpose, method, endstate\n"
                "  · Tactical tasks for each unit one echelon down\n"
                "    (platoons if you command a company, squads if platoon, etc.)"
            ),
            skeleton=(
                "Execution\n"
                "─────────\n"
                "Commander's intent:\n"
                "  Purpose:\n"
                "  Method:\n"
                "  Endstate:\n"
                "\n"
                "Tactical tasks (subordinate units):\n"
                "  Unit 1:\n"
                "  Unit 2:\n"
                "  Unit 3:\n"
            ),
        ),
        TacticianOpordSection(
            step_id="opord_admin",
            title="5 — Administration & Logistics",
            paragraph_name="Administration & Logistics",
            briefing=(
                "EXECUTIVE OFFICER\n"
                "─────────────────\n"
                "Administration and logistics covers sustainment of your force.\n\n"
                "Describe in roleplay terms:\n"
                "  · Equipment brought to the fight\n"
                "  · Vehicles (if any)\n"
                "  · Medical aid / healers available\n\n"
                "When you confirm, the wizard appends a Gameplay Admin block\n"
                "with turn rules, Google Earth workflow, and command scripts."
            ),
            skeleton=(
                "Administration & Logistics\n"
                "──────────────────────────\n"
                "Equipment:\n"
                "\n"
                "Vehicles:\n"
                "\n"
                "Medical aid:\n"
            ),
        ),
        TacticianOpordSection(
            step_id="opord_command",
            title="6 — Command & Signal",
            paragraph_name="Command & Signal",
            briefing=(
                "EXECUTIVE OFFICER\n"
                "─────────────────\n"
                "Command and signal identifies who commands whom and how\n"
                "forces communicate.\n\n"
                "In roleplay terms, address:\n"
                "  · Higher command (who you report to)\n"
                "  · Whether reinforcements can be requested\n"
                "  · How forces communicate on the battlefield\n\n"
                "When you confirm, the wizard appends a Gameplay Signal block\n"
                "covering Discord coordination and turn submission."
            ),
            skeleton=(
                "Command & Signal\n"
                "────────────────\n"
                "Higher command:\n"
                "\n"
                "Reinforcements:\n"
                "\n"
                "Communication (roleplay):\n"
            ),
        ),
    )


TACTICIAN_OPORD_SECTIONS: tuple[TacticianOpordSection, ...] = _sections()
TACTICIAN_OPORD_STEP_IDS: tuple[str, ...] = tuple(s.step_id for s in TACTICIAN_OPORD_SECTIONS)


def tactician_opord_section(step_id: str) -> TacticianOpordSection | None:
    for section in TACTICIAN_OPORD_SECTIONS:
        if section.step_id == step_id:
            return section
    return None


def is_tactician_opord_step(step_id: str) -> bool:
    return step_id in TACTICIAN_OPORD_STEP_IDS


def append_gameplay_blocks(opord_text: str) -> str:
    """Ensure gameplay admin and signal blocks are present in an operation order."""
    text = (opord_text or "").strip()
    has_admin = "GAMEPLAY — ADMINISTRATION" in text
    has_signal = "GAMEPLAY — SIGNAL" in text
    extras: list[str] = []
    if not has_admin:
        extras.append(GAMEPLAY_ADMIN_BLOCK)
    if not has_signal:
        extras.append(GAMEPLAY_SIGNAL_BLOCK)
    if not text:
        return "\n\n".join(extras).strip()
    if not extras:
        return text
    return f"{text}\n\n" + "\n\n".join(extras)


def assemble_tactician_opord(answers: dict) -> str:
    """Merge tactician section drafts into one operation order."""
    parts: list[str] = []
    for section in TACTICIAN_OPORD_SECTIONS:
        raw = (answers.get(section.step_id) or "").strip()
        if section.step_id == "opord_admin":
            if raw:
                parts.append(raw)
            parts.append(GAMEPLAY_ADMIN_BLOCK)
        elif section.step_id == "opord_command":
            if raw:
                parts.append(raw)
            parts.append(GAMEPLAY_SIGNAL_BLOCK)
        elif raw:
            parts.append(raw)
    return "\n\n".join(parts).strip()


def tactician_opord_sections_dict(answers: dict) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for section in TACTICIAN_OPORD_SECTIONS:
        val = answers.get(section.step_id)
        if val is not None and not str(val).strip():
            val = None
        out[section.step_id] = val
    return out
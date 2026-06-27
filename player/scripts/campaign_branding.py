"""ASCII crest, image paths, and centered text blocks for Warcraft: Commander."""

from __future__ import annotations

from pathlib import Path

DEFAULT_WIDTH = 72
BRANDING_DIR = "assets/branding"

# Drop a custom logo in assets/branding/ using any of these names (first match wins).
COMMANDER_LOGO_NAME = "CommanderLogo.png"

CUSTOM_CREST_NAMES = (
    COMMANDER_LOGO_NAME,
    "crest_custom.png",
    "crest_custom.jpg",
    "crest_custom.jpeg",
    "crest_custom.webp",
    "logo.png",
    "logo.jpg",
    "logo.jpeg",
    "logo.webp",
)
DEFAULT_CREST_NAME = "crest.jpg"

# Banner layout inspired by the classic World of Warcraft crest:
# WORLD above a roundel OF, WARCRAFT across the field, COMMANDER as subtitle.
_CREST_RAW = r"""
              ___________________________________________
         ____/                                           \____
    ____/         _______________________________           \____
   /_____________/                               \_____________\
                 |           W O R L D             |
                 |            .─────────.          |
                 |           /    O F    \         |
                 |            `─────────'          |
                 |      W  A  R  C  R  A  F  T      |
                 |             ·   ·   ·           |
                 |         C O M M A N D E R         |
                 \___________________________________/
""".strip("\n")


def branding_dir(project_root: Path) -> Path:
    return project_root / BRANDING_DIR


def resolve_commander_logo(project_root: Path) -> Path | None:
    """Primary app/installer logo (CommanderLogo.png)."""
    path = branding_dir(project_root) / COMMANDER_LOGO_NAME
    return path if path.is_file() else resolve_crest_image(project_root)


def resolve_crest_image(project_root: Path) -> Path | None:
    """Custom logo overrides ship default crest.jpg when present."""
    root = branding_dir(project_root)
    if not root.is_dir():
        return None
    for name in CUSTOM_CREST_NAMES:
        path = root / name
        if path.is_file():
            return path
    default = root / DEFAULT_CREST_NAME
    return default if default.is_file() else None


def center_line(line: str, width: int = DEFAULT_WIDTH) -> str:
    stripped = line.rstrip()
    if len(stripped) >= width:
        return stripped
    pad = (width - len(stripped)) // 2
    return " " * pad + stripped


def center_block(text: str, width: int = DEFAULT_WIDTH) -> str:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    block_width = max(len(line) for line in lines)
    centered_lines = []
    for line in lines:
        inner_pad = (block_width - len(line)) // 2
        centered_lines.append(" " * inner_pad + line)
    margin = max(0, (width - block_width) // 2)
    return "\n".join(" " * margin + line for line in centered_lines)


def warcraft_commander_crest(width: int = DEFAULT_WIDTH) -> str:
    return center_block(_CREST_RAW, width)


WELCOME_BRIEFING = """
Welcome, Commander.

You are about to stand up a Warcraft: Commander campaign — a tabletop-style
wargame on Google Earth Pro, set in the landscapes and lore of Azeroth.

Use the panel on the right to begin setup.
""".strip()
"""Install root detection and path helpers."""

from __future__ import annotations

import platform
import sys
from pathlib import Path

PLAYER_MARKERS = (
    "WoW Commander.kml",
    "03-kml/wowcommanderalpha/doc_player.kml",
    "player/WoW Commander.kml",
)

ICON_DIR_REL = Path("assets/player_custom_icons")
PLAYER_ICON_DIR_REL = Path("player/assets/player_custom_icons")
DEV_ICON_DIR_REL = Path("assets/player_custom_icons")

SPLIT_ZIP_HINTS = (
    "wowcommander-player",
    "Warcraft-Commander",
)


def scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def project_root_from_scripts() -> Path:
    return scripts_dir().parent


def detect_install_root(start: Path | None = None) -> Path | None:
    """Find an existing WoW Commander install walking up from start."""
    cur = (start or Path.cwd()).resolve()
    for _ in range(8):
        for marker in PLAYER_MARKERS:
            if (cur / marker).is_file():
                return cur
        if (cur / "player" / "WoW Commander.kml").is_file():
            return cur / "player"
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def resolve_paths(root: Path) -> dict[str, Path]:
    root = root.resolve()
    if (root / "player" / "WoW Commander.kml").is_file():
        play_root = root / "player"
        scripts = root / "scripts"
    else:
        play_root = root
        scripts = root / "scripts"

    entry_candidates = [
        play_root / "WoW Commander.kml",
        root / "03-kml/wowcommanderalpha/doc_player.kml",
        play_root / "03-kml/wowcommanderalpha/doc_player.kml",
    ]
    entry = next((p for p in entry_candidates if p.is_file()), entry_candidates[0])

    icons = play_root / "assets/player_custom_icons"
    if not icons.is_dir():
        icons = root / "assets/player_custom_icons"

    return {
        "root": root,
        "play_root": play_root,
        "scripts": scripts,
        "entry_kml": entry,
        "icons_dir": icons,
        "tiles": play_root / "tiles" if (play_root / "tiles").is_dir() else root / "02-tiles",
        "kml": play_root / "kml" if (play_root / "kml").is_dir() else root / "03-kml",
    }


def downloads_dir() -> Path:
    home = Path.home()
    if platform.system() == "Windows":
        return home / "Downloads"
    return home / "Downloads"


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_mac() -> bool:
    return platform.system() == "Darwin"


def python_cmd() -> str:
    return sys.executable or "python3"
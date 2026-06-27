"""Load portal game registry from config/portal_games.json."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_PATH = "config/portal_games.json"


def load_portal_games(project_root: Path) -> dict:
    path = project_root / CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    games = data.get("games")
    if not isinstance(games, list) or not games:
        raise ValueError(f"{path}: expected non-empty games array")
    return data


def game_by_id(project_root: Path, game_id: str) -> dict | None:
    data = load_portal_games(project_root)
    for game in data.get("games", []):
        if game.get("id") == game_id:
            return game
    return None


def public_games_manifest(project_root: Path, *, base_url: str = "") -> dict:
    """Sanitized manifest for dist/games.json (no secrets)."""
    data = load_portal_games(project_root)
    base = base_url.rstrip("/")
    games = []
    for game in data.get("games", []):
        prefix = str(game.get("path_prefix", "")).strip("/")
        games.append(
            {
                "id": game["id"],
                "label": game.get("label", game["id"]),
                "campaign_id": game.get("campaign_id", game["id"]),
                "path_prefix": prefix,
                "first_mover": game.get("first_mover", "blue-cell"),
                "campaign_base_url": f"{base}/{prefix}" if base else f"/{prefix}",
            }
        )
    return {
        "portal_label": data.get("portal_label", "WoW Commander Portal"),
        "games": games,
    }
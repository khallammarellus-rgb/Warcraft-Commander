"""Shared Azeroth Explorer release metadata helpers."""

from __future__ import annotations

import json
from pathlib import Path

WOW_EXPORT_URL = "https://github.com/Kruithne/wow.export"


def explorer_release_path(commander_root: Path) -> Path:
    pointer = commander_root / "config" / "explorer_project.json"
    if pointer.is_file():
        cfg = json.loads(pointer.read_text(encoding="utf-8"))
        explorer_root = (commander_root / cfg["path"]).resolve()
        path = explorer_root / "config" / "explorer_release.json"
        if path.is_file():
            return path
    return commander_root / "config" / "explorer_release.json"


def load_explorer_release(project_root: Path) -> dict:
    return json.loads(explorer_release_path(project_root).read_text(encoding="utf-8"))


def github_releases_url(release: dict) -> str:
    explicit = (release.get("github_releases_url") or "").strip()
    if explicit:
        return explicit
    repo = (release.get("github_repo") or "").strip()
    if repo:
        return f"https://github.com/{repo}/releases"
    return ""


def github_pages_url(release: dict) -> str:
    explicit = (release.get("github_pages_url") or "").strip()
    if explicit:
        return explicit
    repo = (release.get("github_repo") or "").strip()
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"
    return ""


def explorer_document_description(release: dict) -> str:
    gh = github_releases_url(release) or github_pages_url(release)
    if gh:
        updates = f"Updates can be found at {gh}."
    else:
        updates = "Updates will be posted on GitHub Releases."
    return (
        f"Explore Azeroth in Google Earth Pro. {updates} "
        f"Credit to the creator of wow.export ({WOW_EXPORT_URL}) for making this possible."
    )
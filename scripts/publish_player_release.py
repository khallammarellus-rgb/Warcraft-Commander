#!/usr/bin/env python3
"""
Create GitHub Release player-v3 and upload the packaged player zip (split parts).

Requires GITHUB_TOKEN (repo scope) or: gh auth login

  export GITHUB_TOKEN=ghp_...
  python3 scripts/publish_player_release.py
  python3 scripts/publish_player_release.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

COMMANDER_REPO = "khallammarellus-rgb/Warcraft-Commander"


def _load_release_config(project_root: Path) -> dict:
    path = project_root / "config" / "player_release.json"
    if not path.is_file():
        raise SystemExit(f"Missing {path} — run: python3 scripts/package_player_release.py --split-mb 1800")
    return json.loads(path.read_text(encoding="utf-8"))


def _asset_paths(project_root: Path, cfg: dict) -> list[Path]:
    parts_dir = project_root / cfg.get("parts_dir", "")
    if parts_dir.is_dir():
        assets = sorted(
            p
            for p in parts_dir.iterdir()
            if p.is_file() and p.name not in {".DS_Store"}
        )
        if assets:
            return assets
    zip_path = project_root / "exports" / cfg["asset_zip"]
    if zip_path.is_file():
        return [zip_path]
    raise SystemExit(f"No player pack found — expected {parts_dir} or {zip_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish player pack to GitHub Releases")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    cfg = _load_release_config(project_root)
    assets = _asset_paths(project_root, cfg)
    tag = cfg.get("release_tag", "player-v3")
    title = f"WoW Commander player pack {cfg.get('globe_version', 'v3')}"
    body = (
        ">>> DOWNLOAD: wowcommander-player assets below (not Source code) <<<\n\n"
        "1. Download every file under Assets (`.zip`, `.z01`, `HOW_TO_JOIN.txt`).\n"
        "2. Join split parts if needed (`zip -FF …`), then unzip.\n"
        "3. Open `03-kml/wowcommanderalpha/doc_player.kml` in Google Earth Pro.\n"
        "4. Table 01 portal: https://wow-commander-campaign.pages.dev/games/table-01/\n"
    )

    print(f"Release: {tag}")
    print(f"Assets ({len(assets)}):")
    for path in assets:
        print(f"  {path.relative_to(project_root)}  ({path.stat().st_size / (1024**3):.2f} GB)")

    if args.dry_run:
        return 0

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    gh = "gh"
    if token:
        env = {**os.environ, "GH_TOKEN": token}
    else:
        env = os.environ

    check = subprocess.run([gh, "auth", "status"], capture_output=True, text=True, env=env)
    if check.returncode != 0 and not token:
        print(check.stderr or check.stdout, file=sys.stderr)
        print(
            "\nAuthenticate first:\n"
            "  gh auth login\n"
            "or:\n"
            "  export GITHUB_TOKEN=ghp_... && python3 scripts/publish_player_release.py",
            file=sys.stderr,
        )
        return 1

    subprocess.run(
        [
            gh,
            "release",
            "create",
            tag,
            "--repo",
            COMMANDER_REPO,
            "--title",
            title,
            "--notes",
            body,
            *[str(p) for p in assets],
        ],
        check=True,
        env=env,
        cwd=project_root,
    )
    print(f"Published: https://github.com/{COMMANDER_REPO}/releases/tag/{tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
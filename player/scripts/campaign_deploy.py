"""Hosted vs local campaign deploy settings in config/globe.json."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from globe_placement import load_globe_config

DEPLOY_MODES = frozenset({"local", "hosted"})
GLOBE_CONFIG_PATH = "config/globe.json"
DEFAULT_VARIANT = "wowcommanderalpha"


def _variant_cfg(globe: dict, variant: str) -> dict:
    variants = globe.get("world_variants") or {}
    cfg = variants.get(variant)
    if not isinstance(cfg, dict):
        raise ValueError(f"Unknown world variant: {variant}")
    return cfg


def read_deploy_settings(project_root: Path, *, variant: str = DEFAULT_VARIANT) -> dict:
    globe_path = project_root / GLOBE_CONFIG_PATH
    globe = json.loads(globe_path.read_text(encoding="utf-8"))
    cfg = _variant_cfg(globe, variant)
    return {
        "campaign_deploy_mode": str(cfg.get("campaign_deploy_mode", "local")),
        "campaign_base_url": str(cfg.get("campaign_base_url", "")).rstrip("/"),
        "campaign_refresh_mode": str(cfg.get("campaign_refresh_mode", "manual")),
        "campaign_hosted_views": bool(cfg.get("campaign_hosted_views", True)),
    }


def write_deploy_settings(
    project_root: Path,
    *,
    variant: str = DEFAULT_VARIANT,
    deploy_mode: str,
    base_url: str = "",
) -> dict:
    deploy_mode = deploy_mode.strip().lower()
    if deploy_mode not in DEPLOY_MODES:
        raise ValueError(f"deploy_mode must be one of {sorted(DEPLOY_MODES)}")

    base_url = base_url.strip().rstrip("/")
    if deploy_mode == "hosted":
        if not base_url:
            raise ValueError("Hosted mode requires campaign_base_url (HTTPS, no trailing slash).")
        if not base_url.lower().startswith("https://"):
            raise ValueError("campaign_base_url must start with https://")

    globe_path = project_root / GLOBE_CONFIG_PATH
    globe = json.loads(globe_path.read_text(encoding="utf-8"))
    variants = globe.setdefault("world_variants", {})
    cfg = variants.setdefault(variant, {})
    cfg["campaign_deploy_mode"] = deploy_mode
    cfg["campaign_base_url"] = base_url
    if deploy_mode == "hosted":
        cfg["campaign_refresh_mode"] = "interval"
        cfg["campaign_hosted_views"] = True
    else:
        cfg["campaign_refresh_mode"] = "manual"
        cfg.pop("campaign_hosted_views", None)
    globe_path.write_text(json.dumps(globe, indent=2) + "\n", encoding="utf-8")

    return {
        "campaign_deploy_mode": deploy_mode,
        "campaign_base_url": base_url,
        "campaign_refresh_mode": cfg.get("campaign_refresh_mode", "manual"),
        "campaign_hosted_views": bool(cfg.get("campaign_hosted_views", False)),
    }


def rebuild_world_kml(project_root: Path, *, variant: str = DEFAULT_VARIANT) -> int:
    script = project_root / "scripts" / "build_world_globe.py"
    result = subprocess.run(
        [sys.executable, str(script), "--kml-only", "--variant", variant],
        cwd=project_root,
        check=False,
    )
    return result.returncode


def apply_session_deploy(
    project_root: Path,
    session: dict,
    *,
    variant: str = DEFAULT_VARIANT,
    rebuild: bool = True,
) -> dict:
    """Persist deploy fields from session and optionally rebuild doc.kml."""
    deploy_mode = str(session.get("campaign_deploy_mode", "local"))
    base_url = str(session.get("campaign_base_url", ""))
    written = write_deploy_settings(
        project_root,
        variant=variant,
        deploy_mode=deploy_mode,
        base_url=base_url,
    )
    if rebuild:
        code = rebuild_world_kml(project_root, variant=variant)
        written["rebuild_exit_code"] = code
    return written


def hosted_upload_hint(base_url: str, theater_id: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/campaign/{theater_id}.kml"


def hosted_view_hint(base_url: str, cell: str, theater_id: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/view/{cell}/{theater_id}.kml"


def apply_hosted_post_setup(
    project_root: Path,
    *,
    variant: str = DEFAULT_VARIANT,
    rebuild_views: bool = True,
    cell: str | None = None,
) -> dict:
    """Patch doc_player.kml for role views and optionally rebuild portal/dist."""
    deploy = read_deploy_settings(project_root, variant=variant)
    if deploy.get("campaign_deploy_mode") != "hosted":
        return {"patched": 0, "views_built": 0}

    base_url = deploy.get("campaign_base_url", "")
    if not base_url:
        return {"patched": 0, "views_built": 0, "error": "missing campaign_base_url"}

    from campaign_hosted_views import patch_player_kml_for_hosted_role, write_hosted_views
    from campaign_session import load_session

    globe = load_globe_config(project_root)
    variant_cfg = (globe.get("world_variants", {}) or {}).get(variant, {})
    player_rel = variant_cfg.get(
        "player_entry",
        "03-kml/wowcommanderalpha/doc_player.kml",
    )
    player_path = project_root / player_rel
    use_views = bool(variant_cfg.get("campaign_hosted_views", True))

    session = load_session(project_root, variant=variant)
    player_cell = cell or (session.get("player_cell") if session else None)

    patched = 0
    if player_cell and player_path.exists():
        patched = patch_player_kml_for_hosted_role(
            player_path,
            base_url=base_url,
            player_cell=player_cell,
            use_views=use_views,
        )

    views_built = 0
    if rebuild_views:
        out_dir = project_root / "portal" / "dist"
        game_format = session.get("game_format") if session else None
        written = write_hosted_views(
            project_root,
            out_dir,
            variant=variant,
            game_format=game_format,
        )
        views_built = len(written)

    return {
        "patched": patched,
        "views_built": views_built,
        "player_cell": player_cell,
    }
#!/usr/bin/env python3
"""
Build and optionally deploy the Cloudflare Pages campaign portal.

Copies portal/public/ into portal/dist/, then writes role-filtered KML views:
  dist/campaign/<theater>.kml
  dist/view/{red-cell,blue-cell,white-cell}/<theater>.kml

  python3 scripts/publish_portal_site.py
  python3 scripts/publish_portal_site.py --deploy
  python3 scripts/publish_portal_site.py --deploy --project-name my-campaign
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_deploy import (
    apply_hosted_post_setup,
    read_deploy_settings,
    rebuild_world_kml,
    write_deploy_settings,
)
from campaign_hosted_views import write_hosted_views
from campaign_session import load_session


def _copy_public(project_root: Path, out_dir: Path) -> int:
    public_dir = project_root / "portal" / "public"
    if not public_dir.is_dir():
        raise SystemExit(f"Missing {public_dir}")
    if out_dir.exists():
        shutil.rmtree(out_dir)
    shutil.copytree(public_dir, out_dir)
    return len(list(out_dir.rglob("*")))


def build_portal_dist(
    project_root: Path,
    *,
    variant: str = "wowcommanderalpha",
    out_dir: Path | None = None,
) -> Path:
    out = out_dir or (project_root / "portal" / "dist")
    out.mkdir(parents=True, exist_ok=True)

    _copy_public(project_root, out)

    session = load_session(project_root, variant=variant)
    game_format = session.get("game_format") if session else None
    written = write_hosted_views(
        project_root,
        out,
        variant=variant,
        game_format=game_format,
    )
    print(f"Wrote {len(written)} campaign/view KML file(s) under {out}")
    return out


def _portal_wrangler(project_root: Path) -> Path | None:
    portal_dir = project_root / "portal"
    wrangler = portal_dir / "node_modules" / ".bin" / "wrangler"
    if wrangler.exists():
        return wrangler
    bundled_node = portal_dir / ".tools" / "node" / "bin" / "node"
    if bundled_node.exists():
        print("Wrangler missing — run: cd portal && npm install", file=sys.stderr)
    else:
        print(
            "Wrangler not installed — install Node.js, then: cd portal && npm install",
            file=sys.stderr,
        )
    return None


def _pages_project_name(project_root: Path, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    toml = project_root / "portal" / "wrangler.toml"
    if toml.exists():
        for line in toml.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("name = "):
                name = stripped.split("=", 1)[1].strip().strip('"').strip("'")
                if name:
                    return name
    return "wow-commander-campaign"


def production_pages_url(project_name: str) -> str:
    return f"https://{project_name}.pages.dev"


def deploy_pages(
    project_root: Path,
    *,
    out_dir: Path,
    project_name: str | None = None,
) -> tuple[int, str]:
    portal_dir = project_root / "portal"
    wrangler = _portal_wrangler(project_root)
    if wrangler is None:
        return 1, ""

    resolved_project = _pages_project_name(project_root, project_name)
    cmd = [str(wrangler), "pages", "deploy", str(out_dir), "--project-name", resolved_project]

    env = None
    bundled_bin = portal_dir / ".tools" / "node" / "bin"
    if bundled_bin.is_dir():
        env = dict(**os.environ)
        env["PATH"] = f"{bundled_bin}:{env.get('PATH', '')}"

    print("Deploying to Cloudflare Pages...")
    result = subprocess.run(
        cmd, cwd=portal_dir, check=False, env=env, capture_output=True, text=True
    )
    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    if result.returncode == 0:
        if result.stdout:
            print(result.stdout.rstrip())
        return 0, combined

    if "Project not found" in combined:
        print(f"Creating Pages project '{resolved_project}'...")
        create = subprocess.run(
            [
                str(wrangler),
                "pages",
                "project",
                "create",
                resolved_project,
                "--production-branch",
                "main",
            ],
            cwd=portal_dir,
            check=False,
            env=env,
        )
        if create.returncode == 0:
            retry = subprocess.run(
                cmd, cwd=portal_dir, check=False, env=env, capture_output=True, text=True
            )
            retry_out = f"{retry.stdout or ''}\n{retry.stderr or ''}"
            if retry.returncode == 0 and retry.stdout:
                print(retry.stdout.rstrip())
            if retry.returncode != 0 and retry_out.strip():
                print(retry_out.rstrip(), file=sys.stderr)
            return retry.returncode, retry_out

    if combined.strip():
        print(combined.rstrip(), file=sys.stderr)
    return result.returncode, combined


def _ensure_hosted_after_deploy(
    project_root: Path,
    *,
    variant: str,
    base_url: str,
    deploy_settings: dict,
) -> None:
    """Turn on hosted mode and refresh player KML after a successful Pages deploy."""
    current_base = deploy_settings.get("campaign_base_url", "")
    current_mode = deploy_settings.get("campaign_deploy_mode", "local")
    if current_mode == "hosted" and current_base == base_url:
        post = apply_hosted_post_setup(project_root, variant=variant, rebuild_views=False)
        if post.get("patched"):
            print(f"Patched doc_player.kml → view/{post.get('player_cell')}/ ({post['patched']} link(s))")
        return

    print()
    print("Enabling hosted mode for Google Earth...")
    write_deploy_settings(
        project_root,
        variant=variant,
        deploy_mode="hosted",
        base_url=base_url,
    )
    code = rebuild_world_kml(project_root, variant=variant)
    if code != 0:
        print(
            f"Warning: doc.kml rebuild exited {code} — "
            f"run: python3 scripts/build_world_globe.py --kml-only --variant {variant}",
            file=sys.stderr,
        )
    post = apply_hosted_post_setup(project_root, variant=variant, rebuild_views=False)
    if post.get("patched"):
        print(f"Patched doc_player.kml → view/{post.get('player_cell')}/ ({post['patched']} link(s))")


def _print_deploy_success(base_url: str) -> None:
    print()
    print("=" * 60)
    print("  DEPLOY SUCCESS")
    print("=" * 60)
    print(f"  Site:     {base_url}")
    print(f"  Red view: {base_url}/view/red-cell/kalimdor.kml")
    print(f"  Master:   {base_url}/campaign/kalimdor.kml")
    print()
    print("  In Google Earth Pro: reopen doc_player.kml, then right-click")
    print("  Campaign Board links → Refresh after future deploys.")
    print("=" * 60)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and deploy WoW Commander campaign portal")
    parser.add_argument("--variant", default="wowcommanderalpha")
    parser.add_argument("--out", type=Path, default=None, help="Output dir (default: portal/dist)")
    parser.add_argument("--deploy", action="store_true", help="Run wrangler pages deploy after build")
    parser.add_argument("--no-deploy", action="store_true", help="Build only (npm run build)")
    parser.add_argument("--project-name", default=None, help="Cloudflare Pages project name")
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    deploy_settings = read_deploy_settings(project_root, variant=args.variant)

    out_dir = build_portal_dist(project_root, variant=args.variant, out_dir=args.out)

    deploy = args.deploy and not args.no_deploy
    if not deploy:
        base = deploy_settings.get("campaign_base_url", "")
        if base:
            print(f"Preview URLs at: {base.rstrip('/')}/view/red-cell/kalimdor.kml")
        else:
            print("Built portal/dist only. Deploy with: python3 scripts/publish_portal_site.py --deploy")
        return 0

    code, _wrangler_out = deploy_pages(
        project_root, out_dir=out_dir, project_name=args.project_name
    )
    if code != 0:
        return code

    project = _pages_project_name(project_root, args.project_name)
    base_url = production_pages_url(project)
    _ensure_hosted_after_deploy(
        project_root,
        variant=args.variant,
        base_url=base_url,
        deploy_settings=deploy_settings,
    )
    _print_deploy_success(base_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
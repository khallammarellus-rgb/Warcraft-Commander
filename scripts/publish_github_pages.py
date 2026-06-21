#!/usr/bin/env python3
"""
Generate docs/index.html for GitHub Pages (Azeroth Explorer landing page).

  python3 scripts/publish_github_pages.py

Enable Pages: repo Settings → Pages → Deploy from branch → main → /docs
"""

from __future__ import annotations

import html
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_kml_superoverlay import merge_variant_config
from explorer_release import (
    github_pages_url,
    github_releases_url,
    load_explorer_release,
)
from globe_placement import layer_by_id, load_globe_config
from places_hierarchy import opposite_hemisphere_ids, split_pacific_and_opposite

SOURCE_VARIANT = "wowcommanderalpha"


def enabled_region_labels(project_root: Path, release: dict) -> tuple[list[str], list[str]]:
    base = load_globe_config(project_root)
    config = merge_variant_config(base, SOURCE_VARIANT)
    ids = [
        layer["id"]
        for layer in config.get("layers", [])
        if layer.get("enabled")
        and layer.get("layer_type") == "minimap"
        and (layer.get("earth_placement") or layer.get("poster_placement"))
    ]
    opposite = opposite_hemisphere_ids(config)
    if not release.get("include_opposite_hemisphere"):
        ids = [rid for rid in ids if rid not in opposite]
    pacific, other = split_pacific_and_opposite(ids, config)

    def labels(region_ids: list[str]) -> list[str]:
        out = []
        for rid in region_ids:
            layer = layer_by_id(config, rid)
            if layer:
                out.append(layer.get("label", rid))
        return out

    return labels(pacific), labels(other)


def render_page(project_root: Path) -> str:
    release = load_explorer_release(project_root)
    version = release.get("explorer_version", "?")
    label = release.get("label", "Azeroth Explorer")
    globe_version = release.get("globe_version", "?")
    released_at = release.get("released_at") or date.today().isoformat()
    changelog = release.get("changelog", "")
    releases_url = github_releases_url(release)
    pages_url = github_pages_url(release)
    pacific_labels, other_labels = enabled_region_labels(project_root, release)

    download_href = releases_url or "#download"
    download_note = (
        "Download the latest zip from GitHub Releases."
        if releases_url
        else "Set <code>github_repo</code> in <code>config/explorer_release.json</code>, then re-run this script."
    )
    zip_name = f"azeroth-explorer-{version}.zip"

    pacific_items = "".join(f"<li>{html.escape(name)}</li>" for name in pacific_labels)
    other_block = ""
    if other_labels:
        other_items = "".join(f"<li>{html.escape(name)}</li>" for name in other_labels)
        other_block = f"""
    <section>
      <h2>Other worlds</h2>
      <ul>{other_items}</ul>
    </section>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Azeroth Explorer — Google Earth maps</title>
  <meta name="description" content="Fly around World of Warcraft's Azeroth in Google Earth Pro. Maps only — no wargame markers.">
  <style>
    :root {{
      --bg: #0b1020;
      --panel: #151d2e;
      --panel-2: #1c2740;
      --text: #edf2f7;
      --muted: #93a4bd;
      --accent: #d4af37;
      --link: #7ec8ff;
      --ok: #5fd38d;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
      background:
        radial-gradient(ellipse 80% 50% at 50% -10%, #1a2a4a 0%, transparent 60%),
        var(--bg);
      color: var(--text);
      line-height: 1.6;
    }}
    main {{
      max-width: 44rem;
      margin: 0 auto;
      padding: 2.5rem 1.25rem 4rem;
    }}
    .badge {{
      display: inline-block;
      font-size: 0.75rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--accent);
      border: 1px solid rgba(212, 175, 55, 0.35);
      border-radius: 999px;
      padding: 0.2rem 0.65rem;
      margin-bottom: 0.75rem;
    }}
    h1 {{
      font-size: clamp(1.75rem, 5vw, 2.25rem);
      font-weight: 700;
      margin: 0 0 0.5rem;
      color: var(--text);
    }}
    .lead {{ color: var(--muted); margin: 0 0 1.75rem; font-size: 1.05rem; }}
    section {{
      background: var(--panel);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 12px;
      padding: 1.1rem 1.25rem;
      margin-bottom: 1rem;
    }}
    h2 {{ font-size: 1rem; margin: 0 0 0.75rem; color: var(--accent); }}
    p {{ margin: 0 0 0.75rem; }}
    p:last-child {{ margin-bottom: 0; }}
    a {{ color: var(--link); }}
    ul, ol {{ margin: 0.5rem 0 0; padding-left: 1.25rem; }}
    li {{ margin-bottom: 0.3rem; }}
    .cta {{
      display: inline-block;
      margin-top: 0.5rem;
      background: linear-gradient(180deg, #e8c547 0%, #b8922a 100%);
      color: #1a1205;
      font-weight: 600;
      text-decoration: none;
      padding: 0.65rem 1.1rem;
      border-radius: 8px;
    }}
    .cta:hover {{ filter: brightness(1.05); }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1rem;
      font-size: 0.9rem;
      color: var(--muted);
      margin-bottom: 1.5rem;
    }}
    .meta strong {{ color: var(--text); font-weight: 600; }}
    code {{
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
      font-size: 0.85em;
      background: var(--panel-2);
      padding: 0.12rem 0.35rem;
      border-radius: 4px;
    }}
    .credit {{ font-size: 0.92rem; color: var(--muted); }}
    .regions {{
      columns: 2;
      column-gap: 1.5rem;
    }}
    @media (max-width: 520px) {{
      .regions {{ columns: 1; }}
    }}
    footer {{
      margin-top: 2rem;
      font-size: 0.85rem;
      color: var(--muted);
      text-align: center;
    }}
  </style>
</head>
<body>
  <main>
    <div class="badge">Maps only · Google Earth Pro</div>
    <h1>Azeroth Explorer</h1>
    <p class="lead">Explore World of Warcraft's Azeroth on a virtual globe. No wargame markers, no scripts, no live updates — just the map.</p>

    <div class="meta">
      <span><strong>Version</strong> {html.escape(version)}</span>
      <span><strong>Release</strong> {html.escape(label)}</span>
      <span><strong>Globe</strong> {html.escape(globe_version)}</span>
      <span><strong>Built</strong> {html.escape(released_at)}</span>
    </div>

    <section id="download">
      <h2>Download</h2>
      <p>{download_note}</p>
      <p>Look for <code>{html.escape(zip_name)}</code> on the latest release.</p>
      <a class="cta" href="{html.escape(download_href)}">Get the map zip</a>
    </section>

    <section>
      <h2>Install &amp; open</h2>
      <ol>
        <li>Install <a href="https://www.google.com/earth/versions/">Google Earth Pro</a> (free).</li>
        <li>Unzip the download and keep <code>Azeroth Explorer.kml</code>, <code>kml/</code>, and <code>tiles/</code> together.</li>
        <li>In Google Earth Pro: <strong>File → Open</strong> → select <code>Azeroth Explorer.kml</code>.</li>
        <li>Use <strong>Map layers → Quick View</strong> to fly between theaters. Zoom in near each landmass — tiles load as you approach.</li>
      </ol>
    </section>

    <section>
      <h2>Pacific theater (this release)</h2>
      <ul class="regions">{pacific_items}</ul>
    </section>
{other_block}

    <section>
      <h2>Changelog</h2>
      <p>{html.escape(changelog)}</p>
    </section>

    <section>
      <h2>Credits</h2>
      <p class="credit">
        Map imagery is exported from World of Warcraft using
        <a href="https://github.com/Kruithne/wow.export">wow.export</a> — this project would not be possible without it.
      </p>
      <p class="credit">
        Looking for the wargame campaign board? That is <strong>WoW Commander Alpha</strong>, a separate build in the same repo.
      </p>
    </section>

    <footer>
      {"Site: " + html.escape(pages_url) if pages_url else "Configure <code>github_repo</code> in explorer_release.json for release links."}
    </footer>
  </main>
</body>
</html>
"""


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    docs_dir = project_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / ".nojekyll").write_text("", encoding="utf-8")
    out = docs_dir / "index.html"
    out.write_text(render_page(project_root), encoding="utf-8")
    release = load_explorer_release(project_root)
    print(f"Wrote {out}")
    repo = (release.get("github_repo") or "").strip()
    if repo:
        print(f"  Releases: {github_releases_url(release)}")
        print(f"  Pages URL: {github_pages_url(release)}")
    else:
        print("  Set github_repo in config/explorer_release.json (e.g. yourname/wow-commander-alpha)")
        print("  Then: GitHub repo → Settings → Pages → Deploy from branch → main → /docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
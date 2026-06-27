"""Custom unit icon paths for campaign KML and turn KMZ packages."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

ICON_HREF_RE = re.compile(r"player_custom_icons/([^\"'<>\s]+)", re.I)
ICON_HREF_FULL_RE = re.compile(r"assets/player_custom_icons/([^\"'<>\s]+)", re.I)
KMZ_ICON_DIR = "assets/player_custom_icons"


def icons_dir(project_root: Path) -> Path:
    for rel in (
        "player/assets/player_custom_icons",
        "assets/player_custom_icons",
    ):
        path = project_root / rel
        if path.is_dir():
            return path
    return project_root / "assets/player_custom_icons"


def collect_icon_names_from_text(text: str) -> set[str]:
    return {m.group(1).strip() for m in ICON_HREF_RE.finditer(text or "")}


def collect_icon_names_from_paths(paths: list[Path]) -> set[str]:
    names: set[str] = set()
    for path in paths:
        try:
            names |= collect_icon_names_from_text(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    return names


def resolve_icon_file(project_root: Path, filename: str) -> Path | None:
    safe = Path(filename).name
    if safe != filename or not safe.lower().endswith(".png"):
        return None
    for rel in (
        "player/assets/player_custom_icons",
        "assets/player_custom_icons",
    ):
        src = project_root / rel / safe
        if src.is_file():
            return src
    return None


def embed_icons_in_kmz(
    archive: zipfile.ZipFile,
    kml_xml_chunks: list[str],
    project_root: Path,
) -> tuple[list[str], list[str]]:
    """Add referenced PNGs into an open ZipFile. Returns (embedded, missing)."""
    names = set()
    for xml in kml_xml_chunks:
        names |= collect_icon_names_from_text(xml)

    embedded: list[str] = []
    missing: list[str] = []
    existing = set(archive.namelist())

    for name in sorted(names):
        arc_path = f"{KMZ_ICON_DIR}/{name}"
        if arc_path in existing:
            embedded.append(name)
            continue
        src = resolve_icon_file(project_root, name)
        if not src:
            missing.append(name)
            continue
        archive.writestr(arc_path, src.read_bytes())
        embedded.append(name)

    return embedded, missing


def extract_icons_from_kmz(kmz_path: Path) -> dict[str, bytes]:
    """Read assets/player_custom_icons/*.png from a turn KMZ."""
    found: dict[str, bytes] = {}
    with zipfile.ZipFile(kmz_path, "r") as zf:
        for name in zf.namelist():
            norm = name.replace("\\", "/").lstrip("/")
            marker = f"{KMZ_ICON_DIR}/"
            if marker not in norm.lower():
                continue
            idx = norm.lower().index(marker)
            rel = norm[idx + len(marker) :]
            filename = Path(rel).name
            if not filename.lower().endswith(".png"):
                continue
            found[filename] = zf.read(name)
    return found


def portal_icon_url(portal_base: str, game_id: str, filename: str) -> str:
    base = portal_base.rstrip("/")
    safe = Path(filename).name
    return f"{base}/api/games/{game_id}/icons/{safe}"


def rewrite_icon_hrefs_to_portal(xml: str, portal_base: str, game_id: str) -> str:
    """Point local player_custom_icons hrefs at the portal icon API."""

    def repl(match: re.Match[str]) -> str:
        return portal_icon_url(portal_base, game_id, match.group(1))

    return ICON_HREF_FULL_RE.sub(repl, xml)


def upload_icons_to_r2(
    project_root: Path,
    game_id: str,
    kmz_path: Path,
    *,
    bucket: str = "wow-commander-turns",
) -> dict:
    """Upload embedded PNGs from a turn KMZ to R2 (merge pipeline backup path)."""
    import subprocess
    import tempfile

    icons = extract_icons_from_kmz(kmz_path)
    if not icons:
        return {"uploaded": 0, "bytes": 0, "files": []}

    wrangler = project_root / "portal" / "node_modules" / ".bin" / "wrangler"
    if not wrangler.exists():
        return {"uploaded": 0, "bytes": 0, "files": [], "error": "wrangler not installed"}

    uploaded: list[str] = []
    total_bytes = 0
    portal_cwd = project_root / "portal"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        for name, data in icons.items():
            local = tmp / name
            local.write_bytes(data)
            key = f"{bucket}/games/{game_id}/icons/{name}"
            rc = subprocess.call(
                [
                    str(wrangler),
                    "r2",
                    "object",
                    "put",
                    key,
                    "--file",
                    str(local),
                    "--content-type",
                    "image/png",
                    "--remote",
                ],
                cwd=portal_cwd,
            )
            if rc == 0:
                uploaded.append(name)
                total_bytes += len(data)

    return {"uploaded": len(uploaded), "bytes": total_bytes, "files": uploaded}
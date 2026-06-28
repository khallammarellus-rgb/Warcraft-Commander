"""System and install health checks."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from player_install.core import detect_install_root, resolve_paths

GE_DOWNLOAD_URL = "https://www.google.com/earth/versions/#download-pro"


def check_python() -> dict:
    ver = sys.version_info
    ok = ver.major >= 3 and ver.minor >= 10
    return {
        "id": "python",
        "label": "Python 3.10+",
        "ok": ok,
        "detail": f"{sys.version.split()[0]} ({sys.executable})",
        "blocking": False,
    }


def check_google_earth() -> dict:
    system = platform.system()
    found = False
    detail = "Not detected — install from Google Earth versions page"
    if system == "Darwin":
        app = Path("/Applications/Google Earth Pro.app")
        found = app.is_dir()
        if found:
            detail = str(app)
    elif system == "Windows":
        candidates = [
            Path(r"C:\Program Files\Google\Google Earth Pro\client\googleearth.exe"),
            Path(r"C:\Program Files (x86)\Google\Google Earth Pro\client\googleearth.exe"),
        ]
        for path in candidates:
            if path.is_file():
                found = True
                detail = str(path)
                break
        if not found and shutil.which("googleearth"):
            found = True
            detail = shutil.which("googleearth") or ""
    else:
        if shutil.which("google-earth-pro") or shutil.which("googleearth"):
            found = True
            detail = shutil.which("google-earth-pro") or shutil.which("googleearth") or ""
    return {
        "id": "google_earth",
        "label": "Google Earth Pro",
        "ok": found,
        "detail": detail,
        "blocking": False,
        "url": GE_DOWNLOAD_URL,
    }


def check_expansion_packs(root: Path | None, project_root: Path | None = None) -> dict:
    if not root:
        return {
            "id": "expansions",
            "label": "Expansion packs",
            "ok": False,
            "detail": "No install folder — cannot scan Subterranean / Other Worlds",
            "blocking": False,
        }
    try:
        from player_install.expansions import check_expansion_packs, format_expansion_summary

        rows = check_expansion_packs(root, project_root)
        if not rows:
            return {
                "id": "expansions",
                "label": "Expansion packs",
                "ok": True,
                "detail": "No expansion manifest in config",
                "blocking": False,
            }
        installed = sum(1 for r in rows if r["installed"])
        detail = format_expansion_summary(rows)
        return {
            "id": "expansions",
            "label": "Expansion packs",
            "ok": installed == len(rows),
            "detail": detail,
            "blocking": False,
            "rows": rows,
        }
    except Exception as exc:
        return {
            "id": "expansions",
            "label": "Expansion packs",
            "ok": False,
            "detail": f"Scan failed: {exc}",
            "blocking": False,
        }


def check_install_layout(root: Path | None) -> dict:
    if not root:
        return {
            "id": "layout",
            "label": "Install folder",
            "ok": False,
            "detail": "No install detected — point wizard at your unzipped player folder",
            "blocking": False,
        }
    paths = resolve_paths(root)
    entry_ok = paths["entry_kml"].is_file()
    tiles_ok = paths["tiles"].is_dir()
    kml_ok = paths["kml"].is_dir() or (paths["root"] / "03-kml").is_dir()
    ok = entry_ok and tiles_ok
    parts = []
    if entry_ok:
        parts.append(f"entry: {paths['entry_kml'].name}")
    else:
        parts.append("missing entry KML")
    if tiles_ok:
        count = sum(1 for _ in paths["tiles"].rglob("*") if _.is_file())
        parts.append(f"tiles: {count:,} files")
    else:
        parts.append("missing tiles/")
    if not kml_ok:
        parts.append("missing kml/")
    return {
        "id": "layout",
        "label": "Install layout",
        "ok": ok,
        "detail": " · ".join(parts),
        "blocking": not entry_ok,
        "paths": paths,
    }


def find_release_zips(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    zips: list[Path] = []
    for path in folder.iterdir():
        if not path.is_file():
            continue
        name = path.name.lower()
        if path.suffix.lower() == ".zip" and any(h in name for h in ("wowcommander", "warcraft-commander")):
            zips.append(path)
    return sorted(zips, key=lambda p: p.stat().st_mtime, reverse=True)


def find_split_zip_parts(folder: Path) -> dict | None:
    if not folder.is_dir():
        return None
    zip_main = None
    parts: list[Path] = []
    for path in folder.iterdir():
        if not path.is_file():
            continue
        lower = path.name.lower()
        if not lower.startswith("wowcommander-player"):
            continue
        if lower.endswith(".zip") and not re.search(r"\.z\d\d$", lower):
            zip_main = path
        elif re.search(r"\.z\d\d$", lower):
            parts.append(path)
    if zip_main and parts:
        return {"main": zip_main, "parts": sorted(parts), "folder": folder}
    return None


def scan_duplicate_installs(search_roots: list[Path]) -> list[dict]:
    seen: dict[str, Path] = {}
    dupes: list[dict] = []
    for base in search_roots:
        if not base.is_dir():
            continue
        for marker in ("WoW Commander.kml", "03-kml/wowcommanderalpha/doc_player.kml"):
            for hit in base.rglob(marker.split("/")[-1] if "/" not in marker else marker):
                if marker.endswith("doc_player.kml") and "doc_player.kml" not in str(hit):
                    continue
                key = str(hit.resolve())
                parent = detect_install_root(hit.parent) or hit.parent
                if key in seen:
                    continue
                seen[key] = parent
    roots = list({str(p.resolve()): p for p in seen.values()}.values())
    if len(roots) <= 1:
        return []
    newest = max(roots, key=lambda p: p.stat().st_mtime if p.exists() else 0)
    for path in roots:
        if path.resolve() == newest.resolve():
            continue
        dupes.append({"path": path, "newest": newest})
    return dupes


def opened_from_zip_warning(path: Path) -> str | None:
    s = str(path)
    if ".zip/" in s or ".zip\\" in s:
        return "This path is still inside a zip archive. Extract fully before opening KML files."
    return None
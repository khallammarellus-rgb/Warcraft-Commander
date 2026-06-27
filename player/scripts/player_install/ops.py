"""Install operations — extract, clean, shortcuts, icon import."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import zipfile
from pathlib import Path

from player_install.core import downloads_dir, is_mac, is_windows, python_cmd, resolve_paths

CACHE_DIR_NAMES = (".cache", "__pycache__", ".pytest_cache")
ARTIFACT_GLOBS = ("*.pyc", ".DS_Store")


def join_split_zip(main_zip: Path, out_zip: Path) -> tuple[bool, str]:
    if shutil.which("zip"):
        try:
            subprocess.run(
                ["zip", "-FF", str(main_zip), "--out", str(out_zip)],
                check=True,
                capture_output=True,
                text=True,
            )
            return True, f"Joined → {out_zip}"
        except subprocess.CalledProcessError as exc:
            return False, exc.stderr or str(exc)
    return False, "zip command not found — use 7-Zip on Windows (see HOW_TO_JOIN.txt)"


def extract_zip(zip_path: Path, dest: Path) -> tuple[bool, str]:
    try:
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(dest)
        return True, f"Extracted to {dest}"
    except zipfile.BadZipFile:
        return False, f"Bad zip (split archive?): {zip_path.name}"
    except Exception as exc:
        return False, str(exc)


def clean_install_artifacts(root: Path, *, keep_icons: bool = True) -> list[str]:
    removed: list[str] = []
    paths = resolve_paths(root)
    icons = paths["icons_dir"]
    for rel in ("02-tiles", "tiles", "03-kml", "kml", "player/cache"):
        target = paths["root"] / rel
        if target.is_dir() and rel not in ("assets",):
            shutil.rmtree(target, ignore_errors=True)
            removed.append(str(target))
    for pattern in ARTIFACT_GLOBS:
        for hit in paths["root"].rglob(pattern):
            if keep_icons and icons in hit.parents:
                continue
            try:
                hit.unlink()
                removed.append(str(hit))
            except OSError:
                pass
    return removed


def import_pngs_from_folder(src: Path, icons_dir: Path) -> list[str]:
    icons_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    if not src.is_dir():
        return copied
    for path in sorted(src.rglob("*.png")):
        if path.stat().st_size < 32:
            continue
        dest = icons_dir / path.name
        shutil.copy2(path, dest)
        copied.append(path.name)
    return copied


def scan_downloads_for_icons() -> list[Path]:
    dl = downloads_dir()
    found: list[Path] = []
    if not dl.is_dir():
        return found
    for path in dl.glob("*.png"):
        if path.stat().st_size > 200:
            found.append(path)
    return sorted(found, key=lambda p: p.stat().st_mtime, reverse=True)[:40]


def open_entry_kml(entry: Path) -> tuple[bool, str]:
    if not entry.is_file():
        return False, f"Missing {entry}"
    system = platform.system()
    try:
        if is_mac():
            subprocess.Popen(["open", str(entry)])
            return True, "Opened in default app (Google Earth Pro)"
        if is_windows():
            os.startfile(str(entry))  # type: ignore[attr-defined]
            return True, "Opened entry KML"
        subprocess.Popen(["xdg-open", str(entry)])
        return True, "Opened entry KML"
    except Exception as exc:
        return False, str(exc)


def launch_player_menu(scripts_dir: Path) -> tuple[bool, str]:
    menu = scripts_dir / "player_menu.py"
    if not menu.is_file():
        return False, f"Missing {menu}"
    try:
        subprocess.Popen([python_cmd(), str(menu)], cwd=str(scripts_dir.parent))
        return True, "Player menu launched"
    except Exception as exc:
        return False, str(exc)


def create_desktop_shortcut(entry_kml: Path, scripts_dir: Path) -> tuple[bool, str]:
    del entry_kml
    project_root = scripts_dir.parent
    launcher = scripts_dir / "create_app_launcher.py"
    if not launcher.is_file():
        launcher = project_root / "scripts" / "create_app_launcher.py"
    if not launcher.is_file():
        return False, "create_app_launcher.py not found"
    try:
        result = subprocess.run(
            [python_cmd(), str(launcher)],
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
        msg = (result.stdout or result.stderr).strip()
        if result.returncode == 0:
            return True, msg or "Desktop launcher created"
        return False, msg or f"exit {result.returncode}"
    except Exception as exc:
        return False, str(exc)
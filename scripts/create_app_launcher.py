#!/usr/bin/env python3
"""
Create a desktop launcher with CommanderLogo icon (Mac .app or Windows .lnk).

  python3 scripts/create_app_launcher.py
  python3 scripts/create_app_launcher.py --desktop-only
"""

from __future__ import annotations

import argparse
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_branding import resolve_commander_logo
from player_install.core import is_mac, is_windows, project_root_from_scripts

APP_NAME = "Warcraft Commander"


def _logo_path(project_root: Path) -> Path:
    logo = resolve_commander_logo(project_root)
    if not logo or not logo.is_file():
        raise SystemExit(
            f"Missing assets/branding/CommanderLogo.png in {project_root}"
        )
    return logo


def _write_ico(png: Path, ico: Path) -> None:
    from PIL import Image

    img = Image.open(png).convert("RGBA")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(ico, format="ICO", sizes=sizes)


def _build_icns(png: Path, icns: Path) -> bool:
    if not is_mac() or not shutil.which("iconutil") or not shutil.which("sips"):
        return False
    iconset = icns.with_suffix(".iconset")
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir()
    spec = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for size, name in spec:
        out = iconset / name
        subprocess.run(["sips", "-z", str(size), str(size), str(png), "--out", str(out)], check=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)], check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    return icns.is_file()


def create_mac_app(project_root: Path, *, desktop: bool = True) -> Path:
    logo = _logo_path(project_root)
    scripts = project_root / "scripts"
    launcher = scripts / "WOW Commander.command"
    if not launcher.is_file():
        raise SystemExit(f"Missing {launcher}")

    app_name = f"{APP_NAME}.app"
    dest_parent = Path.home() / "Desktop" if desktop else project_root
    app_path = dest_parent / app_name
    if app_path.exists():
        shutil.rmtree(app_path)

    contents = app_path / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True)
    resources.mkdir(parents=True)

    shutil.copy2(logo, resources / "CommanderLogo.png")
    icns = resources / "CommanderLogo.icns"
    if not _build_icns(logo, icns):
        shutil.copy2(logo, resources / "AppIcon.icns.png")

    shell = macos / APP_NAME
    shell.write_text(
        f"""#!/bin/bash
cd "{project_root}"
exec "{launcher}"
""",
        encoding="utf-8",
    )
    shell.chmod(0o755)

    info = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "dev.wowcommander.launcher",
        "CFBundleVersion": "1.0",
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": APP_NAME,
        "CFBundleIconFile": "CommanderLogo.icns" if icns.is_file() else "CommanderLogo.png",
        "LSMinimumSystemVersion": "10.13",
    }
    with (contents / "Info.plist").open("wb") as fh:
        plistlib.dump(info, fh)

    return app_path


def create_windows_shortcut(project_root: Path, *, desktop: bool = True) -> Path:
    logo = _logo_path(project_root)
    scripts = project_root / "scripts"
    cmd = scripts / "WOW Commander.cmd"
    if not cmd.is_file():
        raise SystemExit(f"Missing {cmd}")

    branding = project_root / "assets" / "branding"
    branding.mkdir(parents=True, exist_ok=True)
    ico = branding / "CommanderLogo.ico"
    _write_ico(logo, ico)

    dest = (Path.home() / "Desktop" if desktop else project_root) / f"{APP_NAME}.lnk"
    ps = f"""
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{dest}")
$Shortcut.TargetPath = "{cmd}"
$Shortcut.WorkingDirectory = "{project_root}"
$Shortcut.IconLocation = "{ico},0"
$Shortcut.Description = "Warcraft: Commander — install wizard and player menu"
$Shortcut.Save()
"""
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return dest


def create_launcher(project_root: Path, *, desktop: bool = True) -> Path:
    if is_mac():
        return create_mac_app(project_root, desktop=desktop)
    if is_windows():
        return create_windows_shortcut(project_root, desktop=desktop)
    cmd = project_root / "scripts" / "WOW Commander.command"
    dest = Path.home() / "Desktop" / "WOW Commander.command"
    shutil.copy2(cmd, dest)
    dest.chmod(0o755)
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description="Create branded desktop launcher")
    parser.add_argument("--desktop-only", action="store_true", default=True)
    parser.add_argument("--in-project", action="store_true", help="Place .app in project root")
    args = parser.parse_args()
    root = project_root_from_scripts()
    path = create_launcher(root, desktop=not args.in_project)
    print(f"Created launcher: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
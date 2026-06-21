"""System clipboard helpers — Textual OSC-52 does not work in macOS Terminal."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def copy_to_system_clipboard(text: str) -> bool:
    """Copy text to the OS clipboard. Returns True on success."""
    encoded = text.encode("utf-8")

    if sys.platform == "darwin":
        try:
            subprocess.run(["pbcopy"], input=encoded, check=True, timeout=5)
            return True
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        try:
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e", f'set the clipboard to "{escaped}"'],
                check=True,
                timeout=5,
            )
            return True
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    if sys.platform.startswith("linux"):
        for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
            try:
                subprocess.run(cmd, input=encoded, check=True, timeout=5)
                return True
            except (FileNotFoundError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                continue

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["clip"],
                input=encoded,
                check=True,
                timeout=5,
                shell=True,
            )
            return True
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False

    return False


def write_clipboard_fallback(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return path
"""Expansion pack scan helpers for the install wizard."""

from __future__ import annotations

import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parent.parent
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from expansions import scan_pack_status  # noqa: E402


def check_expansion_packs(install_root: Path, project_root: Path | None = None) -> list[dict]:
    """Per-pack status rows for wizard display."""
    return scan_pack_status(install_root.resolve(), project_root)


def format_expansion_summary(rows: list[dict]) -> str:
    lines: list[str] = []
    for row in rows:
        if row["installed"]:
            status = "installed"
        elif row["partial"]:
            status = f"partial ({row['layers_present']}/{row['layers_total']})"
        else:
            status = "not installed"
        lines.append(f"{row['label']}: {status}")
        missing = row.get("missing_ids") or []
        if missing and len(missing) <= 6:
            lines.append(f"  missing: {', '.join(missing)}")
        elif missing:
            lines.append(f"  missing: {len(missing)} zone(s)")
    return "\n".join(lines)
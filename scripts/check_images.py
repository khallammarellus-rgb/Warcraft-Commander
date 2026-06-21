#!/usr/bin/env python3
"""
Simple helper for beginners: List PNG files in 01-raw-export and show their sizes.
No extra libraries needed (uses only Python standard library).

Usage:
    python scripts/check_images.py
"""

import os
from pathlib import Path

def main():
    # Works whether you run from the project root or anywhere else
    project_root = Path(__file__).resolve().parent.parent
    export_dir = project_root / "01-raw-export"
    if not export_dir.exists():
        print("Folder 01-raw-export does not exist yet. Create it and put your PNGs inside.")
        return

    images = list(export_dir.glob("**/*.png")) + list(export_dir.glob("**/*.PNG"))
    if not images:
        print("No PNG images found in 01-raw-export (or its subfolders).")
        return

    print(f"Found {len(images)} PNG image(s):\n")
    for img in sorted(images):
        size = img.stat().st_size / (1024 * 1024)  # MB
        rel_path = img.relative_to(export_dir)
        print(f"  {rel_path}  ({size:.2f} MB)")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
WoW Map Tile Analyzer and Renamer for MapTiler

This script scans your 01-raw-export folder for PNG files exported from wow.export.
It tries to detect the naming pattern like "MapName_XX_YY.png" where XX and YY are tile coordinates.

It will:
- Determine the grid size (how many tiles wide and tall)
- Rename (copy) the files to a standard "tile_XX_YY.png" format with zero-based indices
- Output the grid dimensions you should use in MapTiler

Usage (in terminal, from project root):
    python3 scripts/analyze_and_rename_tiles.py

Requirements: Python 3 (standard library only, no extra packages)

After running:
- Look for "renamed_tiles" subfolder in 01-raw-export
- In MapTiler, when loading images:
  - Load the renamed folder
  - Set "Pixels only"
  - Set the number of horizontal tiles = COLUMNS (width)
  - Set vertical tiles = ROWS (height)
  - Proceed to Google Earth KML output

Note: The script assumes lower Y number is the "top" row. If the map appears flipped in Google Earth, you can flip it in MapTiler or re-run with Y inversion (edit script if needed).
"""

import os
import re
import shutil
from pathlib import Path
from collections import defaultdict

def main():
    # Works whether you run from the project root or anywhere else
    project_root = Path(__file__).resolve().parent.parent
    export_dir = project_root / "01-raw-export"
    
    if not export_dir.exists():
        print(f"ERROR: {export_dir} does not exist. Create it and put your exported PNGs inside.")
        return

    print(f"Scanning {export_dir} for PNG files...")
    
    # Common pattern: MapName_XX_YY.png or similar. Adjust regex if your files differ.
    # Examples seen: Kalimdor_00_00.png , Azeroth_5_12.png , etc.
    pattern = re.compile(r'(\w+)[_-](\d+)[_-](\d+)\.png', re.IGNORECASE)
    
    files_by_map = defaultdict(list)
    
    for png_file in export_dir.rglob("*.png"):
        match = pattern.search(png_file.name)
        if match:
            map_name = match.group(1)
            x = int(match.group(2))
            y = int(match.group(3))
            files_by_map[map_name].append((x, y, png_file))
        else:
            # Fallback: try any two numbers in name
            nums = re.findall(r'(\d+)', png_file.name)
            if len(nums) >= 2:
                map_name = "unknown_map"
                x = int(nums[0])
                y = int(nums[1])
                files_by_map[map_name].append((x, y, png_file))
    
    if not files_by_map:
        print("No PNG files with recognizable X_Y pattern found.")
        print("Please check your export filenames and adjust the regex in this script if needed.")
        print("Example expected: Kalimdor_23_45.png")
        # List some files for user
        some_files = list(export_dir.rglob("*.png"))[:5]
        if some_files:
            print("\nSample filenames found:")
            for f in some_files:
                print(f"  {f.name}")
        return
    
    renamed_base = export_dir / "renamed_for_maptiler"
    renamed_base.mkdir(exist_ok=True)
    
    for map_name, file_list in files_by_map.items():
        xs = [x for x, y, f in file_list]
        ys = [y for x, y, f in file_list]
        
        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        
        cols = max_x - min_x + 1
        rows = max_y - min_y + 1
        
        print(f"\n=== Map: {map_name} ===")
        print(f"Detected grid: {cols} columns (horizontal) x {rows} rows (vertical)")
        print(f"X range: {min_x} to {max_x}")
        print(f"Y range: {min_y} to {max_y}")
        print(f"Total tiles: {len(file_list)}")
        
        map_renamed_dir = renamed_base / map_name
        map_renamed_dir.mkdir(exist_ok=True)
        
        for x, y, src in file_list:
            new_x = x - min_x
            new_y = y - min_y
            new_name = f"tile_{new_x:02d}_{new_y:02d}.png"
            dst = map_renamed_dir / new_name
            shutil.copy2(src, dst)
        
        print(f"Renamed/copied {len(file_list)} files to: {map_renamed_dir}")
        print(f"  -> Use these in MapTiler: Horizontal tiles = {cols}, Vertical tiles = {rows}")
    
    print("\n=== Next Steps ===")
    print("1. In MapTiler: New project -> Load images from the 'renamed_for_maptiler' folder (or subfolder).")
    print("2. Select 'Pixels only / No georeferencing needed'")
    print("3. When asked for grid layout, enter the COLUMNS x ROWS from above.")
    print("4. Choose 'Google Earth KML' output.")
    print("5. Generate and open the KML in Google Earth Pro.")
    print("\nIf the map appears upside down, you can flip vertically in MapTiler before generating KML.")
    print("Run this script again after new exports.")

if __name__ == "__main__":
    main()

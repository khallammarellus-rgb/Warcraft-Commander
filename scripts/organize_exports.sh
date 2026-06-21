#!/bin/bash
# Helper script to organize wow.export PNGs into subfolders
# Run from the project root: bash scripts/organize_exports.sh

echo "Organizing raw exports..."

mkdir -p 01-raw-export/kalimdor
mkdir -p 01-raw-export/eastern-kingdoms
mkdir -p 01-raw-export/outland
mkdir -p 01-raw-export/northrend
mkdir -p 01-raw-export/misc

# Move files based on common WoW map names (add more as needed)
mv 01-raw-export/*[Kk]alimdor* 01-raw-export/kalimdor/ 2>/dev/null || true
mv 01-raw-export/*[Ee]astern* 01-raw-export/eastern-kingdoms/ 2>/dev/null || true
mv 01-raw-export/*[Oo]utland* 01-raw-export/outland/ 2>/dev/null || true
mv 01-raw-export/*[Nn]orthrend* 01-raw-export/northrend/ 2>/dev/null || true

echo "Done! Check the subfolders inside 01-raw-export/"
ls 01-raw-export/

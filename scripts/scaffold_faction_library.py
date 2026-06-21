#!/usr/bin/env python3
"""One-time scaffold for assets/faction_library/. Safe to re-run (skips existing files)."""

from __future__ import annotations

import json
from pathlib import Path

LIBRARY_ROOT = Path(__file__).resolve().parent.parent / "assets" / "faction_library"

FACTIONS: dict[str, list[dict]] = {
    "Alliance": [
        {"id": "humans", "label": "Humans", "officer": "Executive Officer Bolvar Fordragon"},
        {"id": "night_elves", "label": "Night Elves", "officer": "Executive Officer Tyrande Whisperwind"},
        {"id": "dwarves", "label": "Dwarves", "officer": "Executive Officer Muradin Bronzebeard"},
        {"id": "gnomes_mechagnome", "label": "Gnomes / Mechagnome", "officer": "Executive Officer Gelbin Mekkatorque"},
        {"id": "draenei_lightforged", "label": "Draenei / Lightforged", "officer": "Executive Officer Yrel"},
        {"id": "void_elves", "label": "Void Elves", "officer": "Executive Officer Alleria Windrunner"},
        {"id": "worgen_gilneans", "label": "Gilneans (Worgen)", "officer": "Executive Officer Genn Greymane"},
        {"id": "kul_tiran", "label": "Kul Tiran", "officer": "Executive Officer Katherine Proudmoore"},
    ],
    "Horde": [
        {"id": "orc_maghar", "label": "Orc / Mag'har", "officer": "Executive Officer Eitrigg"},
        {"id": "forsaken", "label": "Forsaken", "officer": "Executive Officer Nathanos Blightcaller"},
        {"id": "tauren_highmountain", "label": "Tauren / Highmountain", "officer": "Executive Officer Baine Bloodhoof"},
        {"id": "troll_zandalari", "label": "Troll / Zandalari", "officer": "Executive Officer Rokhan"},
        {"id": "blood_elf", "label": "Blood Elf", "officer": "Executive Officer Lor'themar Theron"},
        {"id": "goblin", "label": "Goblin", "officer": "Executive Officer Trade Prince Gallywix"},
        {"id": "nightborne", "label": "Nightborne", "officer": "Executive Officer Thalyssra"},
        {"id": "vulpera", "label": "Vulpera", "officer": "Executive Officer Nisha"},
    ],
    "Antagonist": [
        {"id": "scourge", "label": "Scourge", "officer": "Executive Officer Kel'Thuzad"},
        {"id": "demons", "label": "Demons", "officer": "Executive Officer Mannoroth"},
        {"id": "nerubians", "label": "Nerubians", "officer": "Executive Officer Anub'arak"},
        {"id": "eldritch", "label": "Eldritch", "officer": "Executive Officer Vol'jaz"},
        {"id": "twilight_cult", "label": "Twilight Cult", "officer": "Executive Officer Cho'gall"},
        {"id": "naga", "label": "Naga", "officer": "Executive Officer Lady Naz'jar"},
    ],
    "Neutral": [
        {"id": "dracthyr", "label": "Dracthyr", "officer": "Executive Officer Scalecommander Emberthal"},
        {"id": "earthen", "label": "Earthen", "officer": "Executive Officer Speaker Brinthe"},
        {"id": "pandaren", "label": "Pandaren", "officer": "Executive Officer Chen Stormstout"},
        {"id": "haranir", "label": "Haranir", "officer": "Executive Officer Haranir Quartermaster"},
        {"id": "dragonkin", "label": "Dragonkin", "officer": "Executive Officer Kalecgos"},
        {"id": "elementals", "label": "Elementals", "officer": "Executive Officer Ragnaros"},
        {"id": "pirates", "label": "Pirates", "officer": "Executive Officer Fleet Master Seahorn"},
    ],
}

PALETTE_KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{label} palette</name>
    <Style id="faction-icon">
      <IconStyle>
        <Icon>
          <href>http://maps.google.com/mapfiles/kml/paddle/red-circle.png</href>
        </Icon>
      </IconStyle>
      <LabelStyle>
        <scale>0.9</scale>
      </LabelStyle>
    </Style>
    <Placemark>
      <name>{label} style sample</name>
      <description>Copy this placemark's icon style when adding units under your cell folder.</description>
      <styleUrl>#faction-icon</styleUrl>
      <Point>
        <coordinates>0,0,0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>
"""


def main() -> None:
    manifest_entries: list[dict] = []
    created = 0

    for category, factions in FACTIONS.items():
        for entry in factions:
            faction_id = entry["id"]
            label = entry["label"]
            folder = LIBRARY_ROOT / category / faction_id
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "icons").mkdir(exist_ok=True)

            officers_path = folder / "officers.json"
            if not officers_path.exists():
                officers_path.write_text(
                    json.dumps({"executive_officer": entry["officer"]}, indent=2) + "\n",
                    encoding="utf-8",
                )
                created += 1

            palette_path = folder / "palette.kml"
            if not palette_path.exists():
                palette_path.write_text(PALETTE_KML.format(label=label), encoding="utf-8")
                created += 1

            manifest_entries.append(
                {
                    "id": faction_id,
                    "label": label,
                    "category": category,
                    "path": f"{category}/{faction_id}",
                }
            )

    manifest = {"version": 1, "factions": manifest_entries}
    manifest_path = LIBRARY_ROOT / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Faction library: {len(manifest_entries)} factions, {created} new file(s) → {LIBRARY_ROOT}")


if __name__ == "__main__":
    main()
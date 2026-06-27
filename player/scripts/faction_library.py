"""On-disk WoW faction library — loaded on demand, never bulk-imported into KML."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from campaign_tier_lod import KML_NS

LIBRARY_DIR_NAME = "faction_library"
UNIT_PALETTES_FOLDER = "Unit palettes"

CATEGORIES = ("Alliance", "Horde", "Antagonist", "Neutral")


def library_root(project_root: Path) -> Path:
    return project_root / "assets" / LIBRARY_DIR_NAME


def load_manifest(project_root: Path) -> dict:
    path = library_root(project_root) / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path} — run: python3 scripts/scaffold_faction_library.py"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def list_factions(project_root: Path, *, category: str | None = None) -> list[dict]:
    manifest = load_manifest(project_root)
    factions = manifest.get("factions", [])
    if category:
        factions = [f for f in factions if f.get("category") == category]
    return sorted(factions, key=lambda f: (f.get("category", ""), f.get("label", "")))


def faction_by_id(project_root: Path, faction_id: str) -> dict | None:
    for entry in load_manifest(project_root).get("factions", []):
        if entry.get("id") == faction_id:
            return entry
    return None


def faction_folder(project_root: Path, faction_id: str) -> Path | None:
    entry = faction_by_id(project_root, faction_id)
    if entry is None:
        return None
    return library_root(project_root) / entry["path"]


def load_officers(project_root: Path, faction_id: str) -> dict:
    folder = faction_folder(project_root, faction_id)
    if folder is None:
        return {}
    path = folder / "officers.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def executive_officer(project_root: Path, faction_id: str) -> str:
    data = load_officers(project_root, faction_id)
    return data.get("executive_officer", "Executive Officer")


def load_palette_document(project_root: Path, faction_id: str) -> ET.Element | None:
    folder = faction_folder(project_root, faction_id)
    if folder is None:
        return None
    path = folder / "palette.kml"
    if not path.exists():
        return None
    root = ET.parse(path).getroot()
    return root.find(f"{{{KML_NS}}}Document")


def palette_style_id(project_root: Path, faction_id: str) -> str:
    """Return namespaced style id for embedding in campaign_live (unique per faction)."""
    return f"faction-{faction_id}-icon"


def build_palette_folder(project_root: Path, faction_id: str) -> ET.Element | None:
    """Build a KML Folder with styles + sample placemark for Unit palettes/."""
    entry = faction_by_id(project_root, faction_id)
    doc = load_palette_document(project_root, faction_id)
    if entry is None or doc is None:
        return None

    folder = ET.Element(f"{{{KML_NS}}}Folder")
    ET.SubElement(folder, f"{{{KML_NS}}}name").text = entry["label"]
    ET.SubElement(folder, f"{{{KML_NS}}}description").text = (
        f"Icon style reference for {entry['label']}. "
        "Copy placemark style when adding units under your red-cell or blue-cell folder."
    )
    ET.SubElement(folder, f"{{{KML_NS}}}open").text = "0"

    style_id = palette_style_id(project_root, faction_id)
    for style in doc.findall(f"{{{KML_NS}}}Style"):
        style_copy = ET.Element(f"{{{KML_NS}}}Style")
        src_id = style.get("id", "faction-icon")
        style_copy.set("id", style_id if src_id == "faction-icon" else f"{faction_id}-{src_id}")
        for child in style:
            style_copy.append(copy.deepcopy(child))
        folder.append(style_copy)

    for pm in doc.findall(f"{{{KML_NS}}}Placemark"):
        pm_copy = copy.deepcopy(pm)
        url_el = pm_copy.find(f"{{{KML_NS}}}styleUrl")
        if url_el is not None and (url_el.text or "").strip() == "#faction-icon":
            url_el.text = f"#{style_id}"
        folder.append(pm_copy)

    return folder
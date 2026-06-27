#!/usr/bin/env python3
"""
Merge a player cell folder from a turn submission into the master theater KML.

Used by the game-repo GitHub Action when players upload turn .kmz files.

  python3 scripts/merge_campaign_submission.py \\
    --master 03-kml/wowcommanderalpha/campaign/kalimdor.kml \\
    --submission submissions/red-cell/turn03.kmz \\
    --cell red-cell

  python3 scripts/merge_campaign_submission.py \\
    --master campaign/kalimdor.kml \\
    --submission turn.kml \\
    --cell blue-cell --theater kalimdor
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_tier_lod import CAMPAIGN_PACKAGE_NAME, KML_NS, migrate_to_campaign_package
from campaign_visibility import VIEWER_ROLES

ET.register_namespace("", KML_NS)


def _kml(tag: str) -> str:
    return f"{{{KML_NS}}}{tag}"


def _folder_named(parent: ET.Element, name: str) -> ET.Element | None:
    for child in parent.findall(_kml("Folder")):
        name_el = child.find(_kml("name"))
        if name_el is not None and (name_el.text or "").strip() == name:
            return child
    return None


def _folder_depth(root: ET.Element, target: ET.Element, depth: int = 0) -> int | None:
    if root is target:
        return depth
    for child in root:
        if child.tag != _kml("Folder"):
            continue
        found = _folder_depth(child, target, depth + 1)
        if found is not None:
            return found
    return None


def _find_campaign_package(root: ET.Element, theater_id: str | None = None) -> ET.Element | None:
    document = root.find(_kml("Document"))
    if document is None:
        return None
    package = _folder_named(document, CAMPAIGN_PACKAGE_NAME)
    if package is not None:
        return package

    if theater_id:
        tid = theater_id.strip().lower()
        deepest: tuple[int, ET.Element] | None = None
        for folder in document.findall(f".//{_kml('Folder')}"):
            name_el = folder.find(_kml("name"))
            if name_el is None or (name_el.text or "").strip().lower() != tid:
                continue
            depth = _folder_depth(document, folder)
            if depth is None:
                continue
            if deepest is None or depth > deepest[0]:
                deepest = (depth, folder)
        if deepest is not None:
            theater_folder = deepest[1]
            theater_name = (theater_folder.find(_kml("name")).text or "").strip()
            search_root = _folder_named(theater_folder, theater_name) or theater_folder
            package = _folder_named(search_root, CAMPAIGN_PACKAGE_NAME)
            if package is not None:
                return package

    for folder in document.findall(f".//{_kml('Folder')}"):
        name_el = folder.find(_kml("name"))
        if name_el is not None and (name_el.text or "") == CAMPAIGN_PACKAGE_NAME:
            return folder
    return None


def _extract_theater_kml_from_kmz(path: Path, theater_id: str | None) -> str:
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        candidates = [n for n in names if n.endswith(".kml") and "doc.kml" not in n.lower()]
        if theater_id:
            preferred = [n for n in candidates if Path(n).stem == theater_id]
            if preferred:
                return zf.read(preferred[0]).decode("utf-8")
        campaign_hits = [n for n in candidates if n.startswith("campaign/")]
        if len(campaign_hits) == 1:
            return zf.read(campaign_hits[0]).decode("utf-8")
        if len(candidates) == 1:
            return zf.read(candidates[0]).decode("utf-8")
        doc_hits = [n for n in names if n.lower().endswith("doc.kml")]
        if len(doc_hits) == 1 and not candidates:
            return zf.read(doc_hits[0]).decode("utf-8")
        raise ValueError(
            f"Cannot pick theater KML from {path.name} — "
            f"pass --theater or use a single campaign/*.kml inside the KMZ"
        )


def _normalize_submission_root(root: ET.Element, theater_id: str | None) -> ET.Element:
    """Unwrap Campaign Live (doc.kml) exports to a theater-level document for merge."""
    document = root.find(_kml("Document"))
    if document is None:
        return root
    if _folder_named(document, CAMPAIGN_PACKAGE_NAME) is not None:
        return root

    pkg = _find_campaign_package(root, theater_id)
    if pkg is None:
        return root

    import copy

    new_root = ET.Element(root.tag)
    new_doc = ET.SubElement(new_root, _kml("Document"))
    label = (theater_id or "Theater").replace("_", " ").title()
    ET.SubElement(new_doc, _kml("name")).text = label
    ET.SubElement(new_doc, _kml("description")).text = (
        f"Turn state for {label}. Use Campaign Package → red-cell or blue-cell → "
        "one tier per marker (Strategic / Operational / Tactical)."
    )
    new_doc.append(copy.deepcopy(pkg))
    return new_root


def _load_submission_xml(path: Path, theater_id: str | None) -> ET.Element:
    suffix = path.suffix.lower()
    if suffix == ".kmz":
        xml_text = _extract_theater_kml_from_kmz(path, theater_id)
        root = ET.fromstring(xml_text)
    else:
        root = ET.parse(path).getroot()
    return _normalize_submission_root(root, theater_id)


def merge_cell_folder(
    master_path: Path,
    submission_path: Path,
    *,
    cell: str,
    theater_id: str | None = None,
    dry_run: bool = False,
) -> bool:
    if cell not in VIEWER_ROLES:
        raise ValueError(f"cell must be one of {sorted(VIEWER_ROLES)}")

    master_root = ET.parse(master_path).getroot()
    sub_root = _load_submission_xml(submission_path, theater_id)

    migrate_to_campaign_package(master_root)
    migrate_to_campaign_package(sub_root)

    master_pkg = _find_campaign_package(master_root, theater_id)
    sub_pkg = _find_campaign_package(sub_root, theater_id)
    if master_pkg is None:
        raise ValueError(f"No Campaign Package in master: {master_path}")
    if sub_pkg is None:
        raise ValueError(f"No Campaign Package in submission: {submission_path}")

    sub_cell = _folder_named(sub_pkg, cell)
    if sub_cell is None:
        raise ValueError(f"Submission has no {cell} folder")

    master_cell = _folder_named(master_pkg, cell)
    if master_cell is not None:
        master_pkg.remove(master_cell)

    import copy

    master_pkg.append(copy.deepcopy(sub_cell))

    if dry_run:
        print(f"Would merge {cell} from {submission_path.name} → {master_path.name}")
        return True

    tree = ET.ElementTree(master_root)
    ET.indent(tree, space="  ")
    tree.write(master_path, encoding="utf-8", xml_declaration=True)
    print(f"Merged {cell} from {submission_path.name} → {master_path}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge player cell folder into master theater KML")
    parser.add_argument("--master", type=Path, required=True, help="Master theater .kml path")
    parser.add_argument("--submission", type=Path, required=True, help="Turn .kml or .kmz submission")
    parser.add_argument("--cell", required=True, choices=sorted(VIEWER_ROLES))
    parser.add_argument("--theater", default=None, help="Theater id when KMZ has multiple campaign/*.kml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.master.exists():
        print(f"Master not found: {args.master}", file=sys.stderr)
        return 1
    if not args.submission.exists():
        print(f"Submission not found: {args.submission}", file=sys.stderr)
        return 1

    try:
        merge_cell_folder(
            args.master,
            args.submission,
            cell=args.cell,
            theater_id=args.theater,
            dry_run=args.dry_run,
        )
    except (ValueError, ET.ParseError, zipfile.BadZipFile) as exc:
        print(f"Merge failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
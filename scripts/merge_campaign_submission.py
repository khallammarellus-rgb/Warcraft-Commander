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


def _find_campaign_package(root: ET.Element) -> ET.Element | None:
    document = root.find(_kml("Document"))
    if document is None:
        return None
    package = _folder_named(document, CAMPAIGN_PACKAGE_NAME)
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
        raise ValueError(
            f"Cannot pick theater KML from {path.name} — "
            f"pass --theater or use a single campaign/*.kml inside the KMZ"
        )


def _load_submission_xml(path: Path, theater_id: str | None) -> ET.Element:
    suffix = path.suffix.lower()
    if suffix == ".kmz":
        xml_text = _extract_theater_kml_from_kmz(path, theater_id)
        return ET.fromstring(xml_text)
    return ET.parse(path).getroot()


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

    master_pkg = _find_campaign_package(master_root)
    sub_pkg = _find_campaign_package(sub_root)
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
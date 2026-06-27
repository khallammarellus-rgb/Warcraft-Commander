#!/usr/bin/env python3
"""Export Google Slides rules deck to local PNGs for the portal (no hotlink breakage)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PRESENTATION_ID = "1dzkJsTt4ir9y-wJLGA4Zm-jIzHHsuaIZnjjj-vIOwz4"
SOURCE_URL = f"https://docs.google.com/presentation/d/{PRESENTATION_ID}/edit"
SKIP_TITLES = {
    "age of conquest introduction",
    "age of conquest rules",
}


def _slug(title: str, index: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
    return f"{index:02d}-{base or 'slide'}.png"


def _page_title(page) -> str:
    lines = [ln.strip() for ln in page.get_text().split("\n") if ln.strip()]
    return lines[0] if lines else "Slide"


def export_rules_slides(project_root: Path) -> dict:
    try:
        import fitz  # pymupdf
    except ImportError as exc:
        raise SystemExit(
            "pymupdf required: pip3 install pymupdf"
        ) from exc

    out_dir = project_root / "portal" / "public" / "assets" / "rules-slides"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.png"):
        old.unlink()

    pdf_path = out_dir / "_source.pdf"
    url = f"https://docs.google.com/presentation/d/{PRESENTATION_ID}/export/pdf"
    subprocess.run(
        ["curl", "-fsSL", url, "-o", str(pdf_path)],
        check=True,
    )

    doc = fitz.open(pdf_path)
    slides_meta = []
    export_index = 0

    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        title = _page_title(page)
        if title.lower() in SKIP_TITLES:
            continue
        export_index += 1
        filename = _slug(title, export_index)
        dest = out_dir / filename
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        pix.save(dest)
        slides_meta.append({
            "file": f"/assets/rules-slides/{filename}",
            "title": title,
            "pdf_page": page_num + 1,
        })

    pdf_path.unlink(missing_ok=True)

    payload = {
        "presentation_id": PRESENTATION_ID,
        "title": "WoW Commander Rules",
        "source_url": SOURCE_URL,
        "slide_count": len(slides_meta),
        "slides": slides_meta,
    }
    data_path = project_root / "portal" / "public" / "data" / "rules-slides.json"
    data_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    payload = export_rules_slides(project_root)
    print(f"Exported {payload['slide_count']} rules slide(s) to portal/public/assets/rules-slides/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
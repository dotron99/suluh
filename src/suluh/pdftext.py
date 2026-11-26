"""Plain-text extraction from PDFs, with a light section splitter."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

HEADINGS = [
    "abstract", "introduction", "background", "related work", "literature review",
    "theoretical framework", "method", "methods", "methodology", "materials and methods",
    "data", "results", "findings", "discussion", "limitations", "conclusion",
    "conclusions", "acknowledgements", "acknowledgments", "references", "bibliography",
]
_HEAD_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?|[IVX]+\.)?\s*(" + "|".join(re.escape(h) for h in HEADINGS) + r")\s*:?\s*$",
    re.I,
)


def extract(path: str | Path, max_pages: int | None = None) -> dict:
    """Return {'title', 'text', 'pages'} from a PDF. Never raises on bad pages."""
    reader = PdfReader(str(path))
    meta_title = None
    try:
        if reader.metadata and reader.metadata.title:
            meta_title = str(reader.metadata.title).strip() or None
    except Exception:
        meta_title = None
    pages = []
    for i, page in enumerate(reader.pages):
        if max_pages is not None and i >= max_pages:
            break
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n".join(pages)
    title = meta_title
    if not title or len(title) < 8 or title.lower().startswith(("microsoft word", "untitled")):
        title = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) > 15), None)
    return {"title": title, "text": text, "pages": len(reader.pages)}


def split_sections(text: str) -> list[dict]:
    """Best-effort split on common academic headings. Falls back to one block."""
    sections: list[dict] = []
    heading, buf = "Front matter", []
    for line in text.splitlines():
        m = _HEAD_RE.match(line)
        if m:
            body = re.sub(r"\s+", " ", " ".join(buf)).strip()
            if body:
                sections.append({"heading": heading, "level": 1, "text": body})
            heading, buf = m.group(1).strip().title(), []
        else:
            buf.append(line)
    body = re.sub(r"\s+", " ", " ".join(buf)).strip()
    if body:
        sections.append({"heading": heading, "level": 1, "text": body})
    return sections

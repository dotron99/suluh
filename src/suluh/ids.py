"""Recognise what kind of identifier the user handed us."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
ARXIV_NEW_RE = re.compile(r"^(?:arxiv:)?(\d{4}\.\d{4,5})(v\d+)?$", re.I)
ARXIV_OLD_RE = re.compile(r"^(?:arxiv:)?([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?$", re.I)
ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:v\d+)?(?:\.pdf)?$", re.I)
PMCID_RE = re.compile(r"^(?:pmcid:)?(PMC\d+)$", re.I)


@dataclass
class Ident:
    kind: str  # doi | arxiv | pmcid | url | pdf
    value: str


def clean_doi(doi: str) -> str:
    doi = doi.strip()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return doi.rstrip(".,;)]}").lower()


def classify(raw: str) -> Ident:
    s = raw.strip()
    if s.lower().endswith(".pdf") and Path(s).expanduser().exists():
        return Ident("pdf", str(Path(s).expanduser().resolve()))
    m = ARXIV_URL_RE.search(s)
    if m:
        return Ident("arxiv", m.group(1))
    if re.match(r"^(https?://)?(dx\.)?doi\.org/", s, re.I) or s.lower().startswith("doi:"):
        return Ident("doi", clean_doi(s))
    if re.match(r"^10\.\d{4,9}/\S+$", s):
        return Ident("doi", clean_doi(s))
    for rx in (ARXIV_NEW_RE, ARXIV_OLD_RE):
        m = rx.match(s)
        if m:
            return Ident("arxiv", m.group(1))
    m = PMCID_RE.match(s)
    if m:
        return Ident("pmcid", m.group(1).upper())
    m = re.search(r"(PMC\d+)", s)
    if m and ("ncbi.nlm.nih.gov" in s or "europepmc.org" in s):
        return Ident("pmcid", m.group(1).upper())
    if re.match(r"^https?://", s, re.I):
        return Ident("url", s)
    if Path(s).expanduser().exists():
        return Ident("pdf", str(Path(s).expanduser().resolve()))
    raise ValueError(
        f"Could not recognise '{raw}'. Use a DOI, arXiv id, PMCID, URL or a path to a PDF."
    )


def find_doi(text: str) -> str | None:
    m = DOI_RE.search(text or "")
    return clean_doi(m.group(1)) if m else None

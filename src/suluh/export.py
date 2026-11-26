"""BibTeX and RIS export."""

from __future__ import annotations

from typing import Iterable

BIB_TYPES = {
    "journal-article": "article", "article": "article",
    "proceedings-article": "inproceedings", "book-chapter": "incollection",
    "book": "book", "dissertation": "phdthesis", "preprint": "misc",
    "posted-content": "misc", "report": "techreport",
}
RIS_TYPES = {
    "article": "JOUR", "inproceedings": "CONF", "incollection": "CHAP",
    "book": "BOOK", "phdthesis": "THES", "techreport": "RPRT", "misc": "GEN",
}


def _bib_escape(s: str) -> str:
    s = str(s)
    for a, b in (("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"), ("_", r"\_")):
        s = s.replace(a, b)
    return s


def _authors(p: dict, sep: str) -> str:
    names = []
    for a in p.get("authors") or []:
        fam, giv = a.get("family") or "", a.get("given") or ""
        names.append(f"{fam}, {giv}".strip(", ") if giv else fam)
    return sep.join(n for n in names if n)


def bib_type(p: dict) -> str:
    return BIB_TYPES.get((p.get("type") or "").lower(), "misc" if p.get("arxiv") else "article")


def bibtex(papers: Iterable[dict]) -> str:
    out = []
    for p in papers:
        t = bib_type(p)
        venue_key = {"article": "journal", "inproceedings": "booktitle",
                     "incollection": "booktitle"}.get(t, "howpublished")
        fields = [
            ("title", p.get("title") and "{" + _bib_escape(p["title"]) + "}"),
            ("author", _bib_escape(_authors(p, " and ")) or None),
            ("year", p.get("year")),
            (venue_key, p.get("venue") and _bib_escape(p["venue"])),
            ("volume", p.get("volume")),
            ("number", p.get("issue")),
            ("pages", p.get("pages") and str(p["pages"]).replace("-", "--")),
            ("publisher", p.get("publisher") and _bib_escape(p["publisher"])),
            ("doi", p.get("doi")),
            ("eprint", p.get("arxiv")),
            ("archiveprefix", "arXiv" if p.get("arxiv") else None),
            ("url", p.get("url")),
        ]
        body = ",\n".join(f"  {k} = {{{v}}}" for k, v in fields if v not in (None, ""))
        out.append(f"@{t}{{{p['id']},\n{body}\n}}\n")
    return "\n".join(out)


def ris(papers: Iterable[dict]) -> str:
    out = []
    for p in papers:
        lines = [f"TY  - {RIS_TYPES.get(bib_type(p), 'GEN')}"]
        for a in p.get("authors") or []:
            fam, giv = a.get("family") or "", a.get("given") or ""
            lines.append(f"AU  - {fam}, {giv}".rstrip(", "))
        for tag, key in (("TI", "title"), ("PY", "year"), ("T2", "venue"), ("VL", "volume"),
                         ("IS", "issue"), ("DO", "doi"), ("UR", "url"), ("AB", "abstract"),
                         ("PB", "publisher")):
            if p.get(key):
                lines.append(f"{tag}  - {p[key]}")
        if p.get("pages"):
            sp, _, ep = str(p["pages"]).partition("-")
            lines.append(f"SP  - {sp}")
            if ep:
                lines.append(f"EP  - {ep}")
        lines.append(f"ID  - {p['id']}")
        lines.append("ER  - ")
        out.append("\n".join(lines))
    return "\n\n".join(out) + "\n"

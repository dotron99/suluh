"""Remote metadata sources. All of them are free and legal.

Crossref, OpenAlex, arXiv, Europe PMC, Unpaywall, Semantic Scholar and CORE.
No shadow libraries are used, and none ever will be.
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from . import __version__
from .config import Config

TIMEOUT = 30.0
ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"


def log(msg: str) -> None:
    # stderr only: stdout is reserved for the MCP stdio protocol.
    print(msg, file=sys.stderr)


def make_client(cfg: Config) -> httpx.Client:
    ua = f"suluh/{__version__} (+https://github.com/dotron99/suluh"
    ua += f"; mailto:{cfg.email})" if cfg.email else ")"
    return httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": ua})


def empty_record() -> dict[str, Any]:
    return {
        "title": None, "authors": [], "year": None, "venue": None, "doi": None,
        "arxiv": None, "pmcid": None, "pmid": None, "url": None, "abstract": None,
        "type": None, "citations": None, "oa_status": None, "oa_url": None,
        "source": None,
    }


def split_name(full: str) -> dict[str, str]:
    full = (full or "").strip()
    if "," in full:
        fam, giv = full.split(",", 1)
        return {"family": fam.strip(), "given": giv.strip()}
    parts = full.split()
    if len(parts) <= 1:
        return {"family": full, "given": ""}
    return {"family": parts[-1], "given": " ".join(parts[:-1])}


def _strip_tags(s: str | None) -> str | None:
    if not s:
        return s
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _get(client: httpx.Client, url: str, **kw) -> httpx.Response | None:
    try:
        r = client.get(url, **kw)
    except httpx.HTTPError as e:
        log(f"  network error for {url.split('?')[0]}: {e.__class__.__name__}")
        return None
    if r.status_code != 200:
        log(f"  {url.split('?')[0]} returned HTTP {r.status_code}")
        return None
    return r


# ---------------------------------------------------------------- Crossref
def crossref_work(client: httpx.Client, cfg: Config, doi: str) -> dict | None:
    params = {"mailto": cfg.email} if cfg.email else None
    r = _get(client, f"https://api.crossref.org/works/{doi}", params=params)
    if not r:
        return None
    m = r.json().get("message", {})
    rec = empty_record()
    rec["source"] = "crossref"
    rec["doi"] = (m.get("DOI") or doi).lower()
    rec["title"] = _strip_tags((m.get("title") or [None])[0])
    rec["authors"] = [
        {"family": a.get("family") or a.get("name", ""), "given": a.get("given", "")}
        for a in m.get("author", [])
    ]
    for key in ("published-print", "published-online", "issued", "created"):
        dp = (m.get(key) or {}).get("date-parts")
        if dp and dp[0] and dp[0][0]:
            rec["year"] = int(dp[0][0])
            break
    rec["venue"] = (m.get("container-title") or [None])[0]
    rec["abstract"] = _strip_tags(m.get("abstract"))
    rec["type"] = m.get("type")
    rec["citations"] = m.get("is-referenced-by-count")
    rec["url"] = m.get("URL")
    rec["volume"] = m.get("volume")
    rec["issue"] = m.get("issue")
    rec["pages"] = m.get("page")
    rec["publisher"] = m.get("publisher")
    return rec


# ---------------------------------------------------------------- OpenAlex
def _openalex_abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    pos: list[tuple[int, str]] = []
    for word, idxs in inv.items():
        pos.extend((i, word) for i in idxs)
    return " ".join(w for _, w in sorted(pos)) or None


def openalex_record(w: dict) -> dict:
    rec = empty_record()
    rec["source"] = "openalex"
    doi = w.get("doi")
    rec["doi"] = doi.replace("https://doi.org/", "").lower() if doi else None
    rec["title"] = w.get("display_name") or w.get("title")
    rec["authors"] = [
        split_name((a.get("author") or {}).get("display_name", ""))
        for a in w.get("authorships", [])
    ]
    rec["year"] = w.get("publication_year")
    loc = w.get("primary_location") or {}
    rec["venue"] = (loc.get("source") or {}).get("display_name")
    rec["abstract"] = _openalex_abstract(w.get("abstract_inverted_index"))
    rec["type"] = w.get("type")
    rec["citations"] = w.get("cited_by_count")
    oa = w.get("open_access") or {}
    rec["oa_status"] = oa.get("oa_status")
    rec["oa_url"] = oa.get("oa_url")
    rec["openalex"] = w.get("id")
    ids = w.get("ids") or {}
    if ids.get("pmcid"):
        tail = ids["pmcid"].rstrip("/").split("/")[-1].upper()
        rec["pmcid"] = tail if tail.startswith("PMC") else f"PMC{tail}"
    if ids.get("pmid"):
        rec["pmid"] = ids["pmid"].rstrip("/").split("/")[-1]
    bib = w.get("biblio") or {}
    rec["volume"] = bib.get("volume")
    rec["issue"] = bib.get("issue")
    if bib.get("first_page"):
        rec["pages"] = bib["first_page"] + (f"-{bib['last_page']}" if bib.get("last_page") else "")
    return rec


def _oa_params(cfg: Config, extra: dict | None = None) -> dict:
    p = dict(extra or {})
    if cfg.email:
        p["mailto"] = cfg.email
    if cfg.openalex_key:
        p["api_key"] = cfg.openalex_key
    return p


def openalex_work(client: httpx.Client, cfg: Config, doi: str) -> dict | None:
    r = _get(client, f"https://api.openalex.org/works/doi:{doi}", params=_oa_params(cfg))
    return openalex_record(r.json()) if r else None


def openalex_search(client: httpx.Client, cfg: Config, query: str, limit: int = 10) -> list[dict]:
    r = _get(client, "https://api.openalex.org/works",
             params=_oa_params(cfg, {"search": query, "per-page": limit}))
    return [openalex_record(w) for w in r.json().get("results", [])] if r else []


# ---------------------------------------------------------------- arXiv
def _arxiv_entries(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for e in root.findall(f"{ATOM}entry"):
        raw_id = (e.findtext(f"{ATOM}id") or "").strip()
        if "/abs/" not in raw_id:
            continue  # arXiv returns an error entry for unknown ids
        aid = re.sub(r"v\d+$", "", raw_id.split("/abs/")[-1])
        rec = empty_record()
        rec["source"] = "arxiv"
        rec["arxiv"] = aid
        rec["title"] = re.sub(r"\s+", " ", e.findtext(f"{ATOM}title") or "").strip()
        rec["abstract"] = re.sub(r"\s+", " ", e.findtext(f"{ATOM}summary") or "").strip()
        rec["authors"] = [split_name(a.findtext(f"{ATOM}name") or "")
                          for a in e.findall(f"{ATOM}author")]
        pub = e.findtext(f"{ATOM}published") or ""
        rec["year"] = int(pub[:4]) if pub[:4].isdigit() else None
        rec["venue"] = (e.findtext(f"{ARXIV_NS}journal_ref") or "").strip() or "arXiv"
        doi = e.findtext(f"{ARXIV_NS}doi")
        rec["doi"] = doi.strip().lower() if doi else None
        rec["type"] = "preprint"
        rec["url"] = f"https://arxiv.org/abs/{aid}"
        rec["oa_status"] = "green"
        rec["oa_url"] = f"https://arxiv.org/pdf/{aid}"
        out.append(rec)
    return out


def arxiv_work(client: httpx.Client, aid: str) -> dict | None:
    r = _get(client, "https://export.arxiv.org/api/query", params={"id_list": aid})
    if not r:
        return None
    entries = _arxiv_entries(r.text)
    return entries[0] if entries else None


def arxiv_search(client: httpx.Client, query: str, limit: int = 10) -> list[dict]:
    r = _get(client, "https://export.arxiv.org/api/query",
             params={"search_query": f"all:{query}", "max_results": limit})
    return _arxiv_entries(r.text) if r else []


# ---------------------------------------------------------------- Europe PMC
def _epmc_record(h: dict) -> dict:
    rec = empty_record()
    rec["source"] = "europepmc"
    rec["title"] = _strip_tags(h.get("title"))
    rec["doi"] = (h.get("doi") or "").lower() or None
    rec["pmcid"] = h.get("pmcid")
    rec["pmid"] = h.get("pmid")
    y = h.get("pubYear")
    rec["year"] = int(y) if y and str(y).isdigit() else None
    rec["venue"] = h.get("journalTitle") or (h.get("journalInfo") or {}).get("journal", {}).get("title")
    rec["citations"] = h.get("citedByCount")
    rec["abstract"] = _strip_tags(h.get("abstractText"))
    al = (h.get("authorList") or {}).get("author")
    if al:
        rec["authors"] = [{"family": a.get("lastName") or a.get("fullName", ""),
                           "given": a.get("firstName", "")} for a in al]
    elif h.get("authorString"):
        # Europe PMC writes "Family AB, Other CD": the initials come last.
        rec["authors"] = []
        for n in h["authorString"].rstrip(".").split(","):
            parts = n.strip().split()
            if not parts:
                continue
            if len(parts) > 1 and parts[-1].isupper() and len(parts[-1]) <= 3:
                rec["authors"].append({"family": " ".join(parts[:-1]), "given": parts[-1]})
            else:
                rec["authors"].append({"family": n.strip(), "given": ""})
    rec["oa_status"] = "open" if h.get("isOpenAccess") == "Y" else "closed"
    if rec["pmcid"]:
        rec["url"] = f"https://europepmc.org/article/PMC/{rec['pmcid']}"
    rec["type"] = "journal-article"
    return rec


def europepmc_search(client: httpx.Client, query: str, limit: int = 10,
                     result_type: str = "lite") -> list[dict]:
    r = _get(client, "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
             params={"query": query, "format": "json", "pageSize": limit,
                     "resultType": result_type})
    if not r:
        return []
    return [_epmc_record(h) for h in r.json().get("resultList", {}).get("result", [])]


def europepmc_by_pmcid(client: httpx.Client, pmcid: str) -> dict | None:
    hits = europepmc_search(client, f"PMCID:{pmcid}", 1, result_type="core")
    return hits[0] if hits else None


def europepmc_fulltext_xml(client: httpx.Client, pmcid: str) -> str | None:
    r = _get(client, f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML")
    return r.text if r else None


def _itertext(el: ET.Element) -> str:
    return re.sub(r"\s+", " ", "".join(el.itertext())).strip()


def jats_sections(xml_text: str) -> list[dict]:
    """Split JATS full text into sections of plain paragraphs."""
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    sections: list[dict] = []
    abstract = root.find(".//front//abstract")
    if abstract is not None:
        text = _itertext(abstract)
        if text:
            sections.append({"heading": "Abstract", "level": 1, "text": text})
    body = root.find(".//body")
    if body is None:
        return sections

    def walk(sec: ET.Element, level: int, prefix: str) -> None:
        title = (sec.findtext("title") or "").strip()
        heading = f"{prefix} > {title}" if prefix and title else (title or prefix or "Body")
        paras = [_itertext(p) for p in sec.findall("p")]
        paras = [p for p in paras if p]
        if paras:
            sections.append({"heading": heading, "level": level, "text": "\n\n".join(paras)})
        for sub in sec.findall("sec"):
            walk(sub, level + 1, heading)

    loose = [_itertext(p) for p in body.findall("p")]
    loose = [p for p in loose if p]
    if loose:
        sections.append({"heading": "Body", "level": 1, "text": "\n\n".join(loose)})
    for sec in body.findall("sec"):
        walk(sec, 1, "")
    return sections


# ---------------------------------------------------------------- Unpaywall
def unpaywall(client: httpx.Client, cfg: Config, doi: str) -> dict | None:
    if not cfg.email:
        log("  Unpaywall skipped: set SULUH_EMAIL (or `suluh config email you@example.org`).")
        return None
    r = _get(client, f"https://api.unpaywall.org/v2/{doi}", params={"email": cfg.email})
    if not r:
        return None
    d = r.json()
    best = d.get("best_oa_location") or {}
    return {
        "is_oa": d.get("is_oa"),
        "oa_status": d.get("oa_status"),
        "pdf_url": best.get("url_for_pdf"),
        "landing_url": best.get("url"),
        "licence": best.get("license"),
    }


# ---------------------------------------------------------------- Semantic Scholar
S2_FIELDS = "title,year,venue,externalIds,citationCount,isOpenAccess,openAccessPdf,authors,abstract"


def s2_search(client: httpx.Client, cfg: Config, query: str, limit: int = 10) -> list[dict]:
    headers = {"x-api-key": cfg.s2_key} if cfg.s2_key else None
    r = _get(client, "https://api.semanticscholar.org/graph/v1/paper/search",
             params={"query": query, "limit": limit, "fields": S2_FIELDS}, headers=headers)
    if not r:
        return []
    out = []
    for p in r.json().get("data", []) or []:
        rec = empty_record()
        rec["source"] = "semanticscholar"
        ext = p.get("externalIds") or {}
        rec["title"] = p.get("title")
        rec["year"] = p.get("year")
        rec["venue"] = p.get("venue") or None
        rec["doi"] = (ext.get("DOI") or "").lower() or None
        rec["arxiv"] = ext.get("ArXiv")
        rec["pmcid"] = f"PMC{ext['PubMedCentral']}" if ext.get("PubMedCentral") else None
        rec["citations"] = p.get("citationCount")
        rec["oa_status"] = "open" if p.get("isOpenAccess") else "closed"
        rec["oa_url"] = (p.get("openAccessPdf") or {}).get("url") or None
        rec["authors"] = [split_name(a.get("name", "")) for a in p.get("authors", [])]
        rec["abstract"] = p.get("abstract")
        out.append(rec)
    return out


# ---------------------------------------------------------------- CORE
def core_search(client: httpx.Client, cfg: Config, query: str, limit: int = 10) -> list[dict]:
    if not cfg.core_key:
        return []
    r = _get(client, "https://api.core.ac.uk/v3/search/works",
             params={"q": query, "limit": limit},
             headers={"Authorization": f"Bearer {cfg.core_key}"})
    if not r:
        return []
    out = []
    for w in r.json().get("results", []):
        rec = empty_record()
        rec["source"] = "core"
        rec["title"] = w.get("title")
        rec["year"] = w.get("yearPublished")
        rec["doi"] = (w.get("doi") or "").lower() or None
        rec["venue"] = (w.get("publisher") or None)
        rec["authors"] = [split_name(a.get("name", "")) for a in w.get("authors", [])]
        rec["citations"] = w.get("citationCount")
        rec["oa_status"] = "open" if w.get("downloadUrl") else None
        rec["oa_url"] = w.get("downloadUrl")
        rec["abstract"] = w.get("abstract")
        out.append(rec)
    return out


SEARCHERS = ("openalex", "semanticscholar", "arxiv", "europepmc", "core")


def find_remote(cfg: Config, query: str, sources: list[str] | None = None,
                limit: int = 10, client: httpx.Client | None = None) -> list[dict]:
    """Search remote sources and merge duplicates by DOI (or title)."""
    sources = sources or ["openalex"]
    own = client is None
    client = client or make_client(cfg)
    results: list[dict] = []
    try:
        for s in sources:
            if s == "openalex":
                results += openalex_search(client, cfg, query, limit)
            elif s == "semanticscholar":
                results += s2_search(client, cfg, query, limit)
            elif s == "arxiv":
                results += arxiv_search(client, query, limit)
            elif s == "europepmc":
                results += europepmc_search(client, query, limit)
            elif s == "core":
                if not cfg.core_key:
                    log("  CORE skipped: set SULUH_CORE_KEY to use it.")
                results += core_search(client, cfg, query, limit)
            else:
                raise ValueError(f"Unknown source '{s}'. Choose from: {', '.join(SEARCHERS)}")
    finally:
        if own:
            client.close()
    merged: dict[str, dict] = {}
    for rec in results:
        key = rec.get("doi") or re.sub(r"\W+", "", (rec.get("title") or "").lower())[:80]
        if not key:
            continue
        if key in merged:
            base = merged[key]
            for k, v in rec.items():
                if base.get(k) in (None, "", []) and v not in (None, "", []):
                    base[k] = v
            base["source"] = f"{base['source']}+{rec['source']}"
        else:
            merged[key] = dict(rec)
    return list(merged.values())

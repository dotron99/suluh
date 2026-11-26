"""Turn an identifier or a PDF into a paper folder."""

from __future__ import annotations

import re
import shutil
import tempfile
import time
from pathlib import Path

import httpx

from . import pdftext, sources
from .config import Config
from .ids import classify, clean_doi, find_doi
from .library import Library, sha256
from .sources import log

KEEP = ("title", "authors", "year", "venue", "doi", "arxiv", "pmcid", "pmid", "url",
        "abstract", "type", "citations", "oa_status", "oa_url", "volume", "issue",
        "pages", "publisher", "openalex")


def merge(*recs: dict | None) -> dict:
    """Earlier records win; later ones only fill gaps."""
    out: dict = {}
    for r in recs:
        if not r:
            continue
        for k in KEEP:
            v = r.get(k)
            if out.get(k) in (None, "", []) and v not in (None, "", []):
                out[k] = v
    out["sources"] = [r["source"] for r in recs if r and r.get("source")]
    return out


def _download_pdf(client: httpx.Client, url: str, dest: Path) -> bool:
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        log(f"  could not download PDF: {e.__class__.__name__}")
        return False
    ctype = r.headers.get("content-type", "")
    if r.status_code != 200 or not (r.content[:5] == b"%PDF-" or "pdf" in ctype):
        log(f"  PDF link did not return a PDF (HTTP {r.status_code}); skipped")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return True


def _attach_pdf_text(rec: dict, pdf: Path) -> None:
    try:
        info = pdftext.extract(pdf)
    except Exception as e:  # damaged or encrypted PDFs
        log(f"  could not read PDF text: {e.__class__.__name__}")
        return
    if not rec.get("sections"):
        rec["sections"] = pdftext.split_sections(info["text"])
        rec["sections_from"] = "pdf"
    rec["pages_count"] = info["pages"]


class Importer:
    def __init__(self, cfg: Config, library: Library | None = None,
                 client: httpx.Client | None = None, fetch_pdf: bool = True):
        self.cfg = cfg
        self.lib = library or Library(cfg.library)
        self.client = client or sources.make_client(cfg)
        self.fetch_pdf = fetch_pdf

    # ------------------------------------------------------------ public
    def add(self, raw: str) -> dict:
        ident = classify(raw)
        handler = getattr(self, f"_add_{ident.kind}")
        return handler(ident.value)

    # ------------------------------------------------------------ helpers
    def _finish(self, rec: dict, pdf_url: str | None = None,
                xml: str | None = None, local_pdf: Path | None = None) -> dict:
        existing = self.lib.find_existing(rec)
        if existing:
            log(f"  already in library as {existing}")
            paper = self.lib.get(existing)
            paper["already_present"] = True
            return paper
        rec = self.lib.save(rec)
        src = self.lib.paper_dir(rec["id"]) / "source"
        files = []
        if xml:
            (src / "fulltext.xml").write_text(xml, encoding="utf-8")
            files.append("source/fulltext.xml")
        if local_pdf:
            shutil.copy2(local_pdf, src / "paper.pdf")
            files.append("source/paper.pdf")
        elif pdf_url and self.fetch_pdf:
            if _download_pdf(self.client, pdf_url, src / "paper.pdf"):
                files.append("source/paper.pdf")
                rec["pdf_from"] = pdf_url
        if files:
            if "source/paper.pdf" in files:
                _attach_pdf_text(rec, src / "paper.pdf")
            rec["files"] = files
            rec = self.lib.save(rec)
        return rec

    def _oa(self, doi: str) -> tuple[str | None, dict | None]:
        up = sources.unpaywall(self.client, self.cfg, doi)
        if up and up.get("pdf_url"):
            return up["pdf_url"], up
        return None, up

    # ------------------------------------------------------------ kinds
    def _add_doi(self, doi: str, extra: dict | None = None) -> dict:
        doi = clean_doi(doi)
        log(f"Looking up DOI {doi}")
        oa = sources.openalex_work(self.client, self.cfg, doi)
        cr = sources.crossref_work(self.client, self.cfg, doi)
        if not oa and not cr and not extra:
            raise LookupError(f"DOI {doi} was not found in OpenAlex or Crossref.")
        rec = merge(extra, cr, oa)
        rec["doi"] = doi
        pdf_url, up = self._oa(doi)
        if up:
            rec["oa_status"] = up.get("oa_status") or rec.get("oa_status")
            rec["licence"] = up.get("licence")
        xml = None
        if rec.get("pmcid"):
            xml = sources.europepmc_fulltext_xml(self.client, rec["pmcid"])
            if xml:
                try:
                    secs = sources.jats_sections(xml)
                    if secs:
                        rec["sections"], rec["sections_from"] = secs, "europepmc"
                except Exception:
                    xml = None
        if not pdf_url and rec.get("oa_url") and str(rec["oa_url"]).lower().endswith(".pdf"):
            pdf_url = rec["oa_url"]
        if not pdf_url and not xml:
            log("  no legal open-access copy found; use your institutional login and "
                "`suluh add <file.pdf>` to attach the PDF.")
        return self._finish(rec, pdf_url=pdf_url, xml=xml)

    def _add_arxiv(self, aid: str) -> dict:
        log(f"Looking up arXiv {aid}")
        rec = sources.arxiv_work(self.client, aid)
        if not rec:
            raise LookupError(f"arXiv id {aid} was not found.")
        extra = None
        if rec.get("doi"):
            extra = sources.openalex_work(self.client, self.cfg, rec["doi"])
        out = merge(rec, extra)
        if out.get("citations") is None:
            hit = sources.openalex_work(self.client, self.cfg, f"10.48550/arxiv.{aid}")
            if hit:
                out["citations"] = hit.get("citations")
        out["arxiv"] = aid
        return self._finish(out, pdf_url=f"https://arxiv.org/pdf/{aid}")

    def _add_pmcid(self, pmcid: str) -> dict:
        log(f"Looking up {pmcid} in Europe PMC")
        meta = sources.europepmc_by_pmcid(self.client, pmcid)
        if not meta:
            raise LookupError(f"{pmcid} was not found in Europe PMC.")
        oa = sources.openalex_work(self.client, self.cfg, meta["doi"]) if meta.get("doi") else None
        rec = merge(meta, oa)
        rec["pmcid"] = pmcid
        xml = sources.europepmc_fulltext_xml(self.client, pmcid)
        if xml:
            try:
                secs = sources.jats_sections(xml)
                if secs:
                    rec["sections"], rec["sections_from"] = secs, "europepmc"
            except Exception as e:
                log(f"  could not parse full-text XML: {e.__class__.__name__}")
        return self._finish(rec, xml=xml)

    def _add_url(self, url: str) -> dict:
        log(f"Fetching {url}")
        doi = find_doi(url) if "doi" in url.lower() else None
        if doi:
            return self._add_doi(doi)
        try:
            r = self.client.get(url)
        except httpx.HTTPError as e:
            raise LookupError(f"Could not fetch {url}: {e.__class__.__name__}") from e
        if r.content[:5] == b"%PDF-":
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "download.pdf"
                p.write_bytes(r.content)
                rec = self._add_pdf(str(p), origin=url)
            return rec
        html = r.text
        m = re.search(r'<meta[^>]+name=["\'](?:citation_doi|dc\.identifier|prism\.doi)["\'][^>]+content=["\']([^"\']+)',
                      html, re.I)
        doi = find_doi(m.group(1)) if m else None
        if doi:
            return self._add_doi(doi, extra={"url": url, "source": "web"})
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        rec = sources.empty_record()
        rec.update({"title": re.sub(r"\s+", " ", title.group(1)).strip() if title else url,
                    "url": url, "type": "webpage", "source": "web"})
        return self._finish(merge(rec))

    def _add_pdf(self, path: str, origin: str | None = None) -> dict:
        pdf = Path(path)
        digest = sha256(pdf)
        existing = self.lib.find_existing({"sha256": digest})
        if existing:
            log(f"  this PDF is already in the library as {existing}")
            paper = self.lib.get(existing)
            paper["already_present"] = True
            return paper
        log(f"Reading {pdf.name}")
        info = pdftext.extract(pdf, max_pages=3)
        doi = find_doi(info["text"])
        rec: dict | None = None
        if doi:
            log(f"  found DOI {doi} in the PDF")
            oa = sources.openalex_work(self.client, self.cfg, doi)
            cr = sources.crossref_work(self.client, self.cfg, doi)
            if oa or cr:
                rec = merge(cr, oa)
                rec["doi"] = doi
                existing = self.lib.find_existing(rec)
                if existing:
                    # Same paper already present (e.g. added by DOI): attach the PDF.
                    paper = self.lib.get(existing)
                    src = self.lib.paper_dir(existing) / "source" / "paper.pdf"
                    if not src.exists():
                        shutil.copy2(pdf, src)
                        paper.setdefault("files", []).append("source/paper.pdf")
                        paper["sha256"] = digest
                        _attach_pdf_text(paper, src)
                        self.lib.save(paper)
                        log(f"  attached the PDF to existing paper {existing}")
                    paper["already_present"] = True
                    return paper
        if rec is None:
            rec = sources.empty_record()
            rec.update({"title": info["title"] or pdf.stem, "type": "document", "source": "pdf"})
            rec = merge(rec)
        rec["sha256"] = digest
        if origin:
            rec["url"] = rec.get("url") or origin
        return self._finish(rec, local_pdf=pdf)


def watch(cfg: Config, folder: str | Path, interval: float = 10.0, once: bool = False,
          importer: Importer | None = None) -> list[dict]:
    """Poll a folder and import any new PDF. Returns the papers added in the last pass."""
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    imp = importer or Importer(cfg)
    seen: dict[str, float] = {}
    added: list[dict] = []
    log(f"Watching {folder} for new PDFs (every {interval:g}s). Press Ctrl+C to stop.")
    while True:
        added = []
        for pdf in sorted(folder.rglob("*.pdf")):
            try:
                mtime = pdf.stat().st_mtime
            except OSError:
                continue
            if seen.get(str(pdf)) == mtime:
                continue
            # Wait until the file has stopped growing (downloads in progress).
            size = pdf.stat().st_size
            time.sleep(0 if once else 1)
            if pdf.stat().st_size != size:
                continue
            seen[str(pdf)] = mtime
            try:
                rec = imp.add(str(pdf))
                if not rec.get("already_present"):
                    log(f"  added {rec['id']}: {rec.get('title')}")
                    added.append(rec)
            except Exception as e:
                log(f"  could not import {pdf.name}: {e}")
        if once:
            return added
        time.sleep(interval)

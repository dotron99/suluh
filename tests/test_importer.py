import httpx
import pytest
import respx

from suluh.importer import Importer, watch
from suluh.sources import find_remote, jats_sections

from .conftest import make_pdf

DOI = "10.1234/abc.5"

CROSSREF = {"message": {
    "DOI": DOI, "title": ["Trust in <i>AI</i> overviews"], "type": "journal-article",
    "author": [{"family": "Li", "given": "Haiwen"}, {"family": "Aral", "given": "Sinan"}],
    "issued": {"date-parts": [[2025, 4]]}, "container-title": ["Test Journal"],
    "abstract": "<jats:p>An experiment on trust.</jats:p>", "is-referenced-by-count": 7,
    "volume": "3", "page": "1-20", "publisher": "Pub",
}}
OPENALEX = {
    "id": "https://openalex.org/W1", "doi": f"https://doi.org/{DOI}",
    "display_name": "Trust in AI overviews", "publication_year": 2025,
    "authorships": [{"author": {"display_name": "Haiwen Li"}}],
    "primary_location": {"source": {"display_name": "Test Journal"}},
    "abstract_inverted_index": {"An": [0], "experiment": [1]},
    "cited_by_count": 9, "type": "article",
    "open_access": {"oa_status": "gold", "oa_url": "https://example.org/a.pdf"},
    "ids": {}, "biblio": {"volume": "3", "first_page": "1", "last_page": "20"},
}
ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
 <entry>
  <id>http://arxiv.org/abs/2106.15183v1</id>
  <published>2021-06-29T08:00:00Z</published>
  <title>Multi-Exit Vision Transformer
   for Dynamic Inference</title>
  <summary>Deep neural networks can be converted to multi-exit architectures.</summary>
  <author><name>Arian Bakhtiarnia</name></author>
  <author><name>Qi Zhang</name></author>
 </entry>
</feed>"""
JATS = """<article><front><article-meta><abstract><p>Short abstract.</p></abstract>
</article-meta></front><body>
<sec><title>Introduction</title><p>Intro <italic>text</italic>.</p>
  <sec><title>Aims</title><p>We aim high.</p></sec></sec>
<sec><title>Methods</title><p>We did things.</p></sec></body></article>"""
EPMC = {"resultList": {"result": [{
    "pmcid": "PMC123", "doi": "10.5555/pmc.1", "title": "A PMC paper", "pubYear": "2020",
    "journalInfo": {"journal": {"title": "PMC Journal"}}, "citedByCount": 4,
    "abstractText": "Abstract here.", "isOpenAccess": "Y",
    "authorList": {"author": [{"lastName": "Smith", "firstName": "Jo"}]},
}]}}


def _imp(cfg, lib, **kw):
    return Importer(cfg, lib, client=httpx.Client(), **kw)


@respx.mock
def test_add_doi_with_oa_pdf(cfg, lib):
    respx.get(f"https://api.openalex.org/works/doi:{DOI}").respond(json=OPENALEX)
    respx.get(f"https://api.crossref.org/works/{DOI}").respond(json=CROSSREF)
    respx.get(f"https://api.unpaywall.org/v2/{DOI}").respond(json={
        "is_oa": True, "oa_status": "gold",
        "best_oa_location": {"url_for_pdf": "https://example.org/a.pdf", "license": "cc-by"}})
    respx.get("https://example.org/a.pdf").respond(
        content=make_pdf(["Introduction", "Some body text about trust."]),
        headers={"content-type": "application/pdf"})
    rec = _imp(cfg, lib).add(DOI)
    assert rec["id"] == "li2025trust"
    assert rec["title"] == "Trust in AI overviews"  # Crossref wins, tags stripped
    assert rec["citations"] == 7 and rec["oa_status"] == "gold" and rec["licence"] == "cc-by"
    assert rec["files"] == ["source/paper.pdf"]
    assert (lib.paper_dir(rec["id"]) / "source" / "paper.pdf").exists()
    assert any("trust" in s["text"].lower() for s in rec["sections"])
    # second add is de-duplicated
    again = _imp(cfg, lib).add(f"https://doi.org/{DOI}")
    assert again["already_present"] and again["id"] == rec["id"]


@respx.mock
def test_unpaywall_needs_email(cfg, lib):
    cfg.email = None
    respx.get(f"https://api.openalex.org/works/doi:{DOI}").respond(404)
    respx.get(f"https://api.crossref.org/works/{DOI}").respond(json=CROSSREF)
    up = respx.get(f"https://api.unpaywall.org/v2/{DOI}")
    rec = _imp(cfg, lib, fetch_pdf=False).add(DOI)
    assert not up.called and rec["title"] == "Trust in AI overviews"


@respx.mock
def test_doi_not_found(cfg, lib):
    respx.get(f"https://api.openalex.org/works/doi:{DOI}").respond(404)
    respx.get(f"https://api.crossref.org/works/{DOI}").respond(404)
    with pytest.raises(LookupError):
        _imp(cfg, lib).add(DOI)


@respx.mock
def test_add_arxiv(cfg, lib):
    respx.get("https://export.arxiv.org/api/query").respond(text=ARXIV_XML)
    respx.get(url__startswith="https://api.openalex.org/").respond(404)
    respx.get("https://arxiv.org/pdf/2106.15183").respond(
        content=make_pdf(["Abstract", "Exits everywhere."]), headers={"content-type": "application/pdf"})
    rec = _imp(cfg, lib).add("arXiv:2106.15183")
    assert rec["id"] == "bakhtiarnia2021multi"
    assert rec["title"] == "Multi-Exit Vision Transformer for Dynamic Inference"
    assert rec["authors"][0] == {"family": "Bakhtiarnia", "given": "Arian"}
    assert rec["files"] == ["source/paper.pdf"]


@respx.mock
def test_add_pmcid_sections(cfg, lib):
    respx.get("https://www.ebi.ac.uk/europepmc/webservices/rest/search").respond(json=EPMC)
    respx.get("https://www.ebi.ac.uk/europepmc/webservices/rest/PMC123/fullTextXML").respond(text=JATS)
    respx.get(url__startswith="https://api.openalex.org/").respond(404)
    rec = _imp(cfg, lib).add("PMC123")
    heads = [s["heading"] for s in rec["sections"]]
    assert heads == ["Abstract", "Introduction", "Introduction > Aims", "Methods"]
    assert rec["sections_from"] == "europepmc"
    assert (lib.paper_dir(rec["id"]) / "source" / "fulltext.xml").exists()


def test_jats_inline_markup():
    secs = jats_sections(JATS)
    assert secs[1]["text"] == "Intro text."


@respx.mock
def test_add_pdf_without_doi_and_dedupe(cfg, lib, tmp_path):
    pdf = tmp_path / "local.pdf"
    pdf.write_bytes(make_pdf(["A Local Working Paper On Heritage", "Introduction", "Body."]))
    rec = _imp(cfg, lib).add(str(pdf))
    assert rec["title"] == "A Local Working Paper On Heritage"
    assert rec["sha256"] and rec["files"] == ["source/paper.pdf"]
    assert _imp(cfg, lib).add(str(pdf))["already_present"]


@respx.mock
def test_add_pdf_with_doi_attaches_to_existing(cfg, lib, tmp_path):
    respx.get(f"https://api.openalex.org/works/doi:{DOI}").respond(json=OPENALEX)
    respx.get(f"https://api.crossref.org/works/{DOI}").respond(json=CROSSREF)
    respx.get(f"https://api.unpaywall.org/v2/{DOI}").respond(json={"best_oa_location": None})
    first = _imp(cfg, lib, fetch_pdf=False).add(DOI)
    pdf = tmp_path / "paywalled.pdf"
    pdf.write_bytes(make_pdf(["Trust paper", f"https://doi.org/{DOI}", "Methods", "Stuff."]))
    rec = _imp(cfg, lib).add(str(pdf))
    assert rec["id"] == first["id"] and rec["already_present"]
    assert (lib.paper_dir(first["id"]) / "source" / "paper.pdf").exists()


@respx.mock
def test_add_url_with_citation_meta(cfg, lib):
    respx.get("https://journal.example/article/1").respond(
        text=f'<html><head><meta name="citation_doi" content="{DOI}"><title>x</title></head></html>')
    respx.get(f"https://api.openalex.org/works/doi:{DOI}").respond(json=OPENALEX)
    respx.get(f"https://api.crossref.org/works/{DOI}").respond(json=CROSSREF)
    respx.get(f"https://api.unpaywall.org/v2/{DOI}").respond(404)
    rec = _imp(cfg, lib, fetch_pdf=False).add("https://journal.example/article/1")
    assert rec["doi"] == DOI


@respx.mock
def test_watch_once(cfg, lib, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "a.pdf").write_bytes(make_pdf(["First Watched Paper Title Here", "Body."]))
    (inbox / "b.pdf").write_bytes(make_pdf(["Second Watched Paper Title Here", "Body."]))
    added = watch(cfg, inbox, once=True, importer=_imp(cfg, lib))
    assert len(added) == 2 and len(lib.ids()) == 2


@respx.mock
def test_find_remote_merges(cfg):
    respx.get("https://api.openalex.org/works").respond(json={"results": [OPENALEX]})
    respx.get("https://api.semanticscholar.org/graph/v1/paper/search").respond(json={"data": [{
        "title": "Trust in AI overviews", "year": 2025, "venue": "TJ",
        "externalIds": {"DOI": DOI.upper(), "ArXiv": "2504.06435"}, "citationCount": 11,
        "isOpenAccess": True, "openAccessPdf": {"url": "https://x/y.pdf"}, "authors": []}]})
    respx.get("https://export.arxiv.org/api/query").respond(text=ARXIV_XML)
    recs = find_remote(cfg, "trust", ["openalex", "semanticscholar", "arxiv", "core"],
                       client=httpx.Client())
    assert len(recs) == 2
    merged = next(r for r in recs if r["doi"] == DOI)
    assert merged["citations"] == 9 and merged["arxiv"] == "2504.06435"
    assert merged["source"] == "openalex+semanticscholar"


def test_find_remote_unknown_source(cfg):
    with pytest.raises(ValueError):
        find_remote(cfg, "x", ["scihub"], client=httpx.Client())

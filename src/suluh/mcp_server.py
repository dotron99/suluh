"""MCP server (stdio) so Claude Code, Codex and other agents can use the library."""

from __future__ import annotations

from typing import Any

from .config import Config
from .export import bibtex
from .importer import Importer
from .library import TAGS, Library
from .sources import find_remote as _find_remote

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore

INSTRUCTIONS = (
    "Suluh is the user's local literature library. Search it before searching the web. "
    "Quote papers accurately and cite them with their Suluh id or DOI. "
    "Never invent papers, numbers or quotes. Remote search uses legal sources only."
)


def build_server(cfg: Config | None = None):
    cfg = cfg or Config.load()
    lib = Library(cfg.library)
    server = _Server("suluh", instructions=INSTRUCTIONS)

    def _summary(p: dict) -> dict:
        return {k: p.get(k) for k in ("id", "title", "authors", "year", "venue", "doi",
                                       "arxiv", "pmcid", "citations", "oa_status", "url")}

    @server.tool()
    def search_library(query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Full-text search of the local library (titles, abstracts, full text and notes).
        Supports SQLite FTS5 syntax, e.g. 'trust AND "AI overviews"'."""
        return lib.search(query, limit)

    @server.tool()
    def get_paper(paper_id: str, include_sections: bool = False) -> dict[str, Any]:
        """Return a paper's metadata and abstract. Set include_sections to get the parsed
        full text, split into sections."""
        p = lib.get(paper_id)
        out = dict(p)
        if not include_sections:
            out["sections"] = [s.get("heading") for s in p.get("sections") or []]
        return out

    @server.tool()
    def get_notes(paper_id: str) -> dict[str, Any]:
        """Return the free notes (notes.md) and anchored annotations for a paper."""
        return {"notes_md": lib.notes(paper_id), "annotations": lib.annotations(paper_id)}

    @server.tool()
    def add_note(paper_id: str, text: str, quote: str | None = None,
                 tag: str | None = None, section: str | None = None) -> dict[str, Any]:
        """Add a note to a paper, optionally anchored to a quoted sentence.
        tag is one of: idea, method, data, question."""
        if tag and tag not in TAGS:
            raise ValueError(f"tag must be one of {TAGS}")
        return lib.add_note(paper_id, text, quote=quote, tag=tag, section=section)

    @server.tool()
    def find_remote(query: str, sources: list[str] | None = None,
                    limit: int = 10) -> list[dict[str, Any]]:
        """Search remote scholarly indexes. sources: any of openalex (default),
        semanticscholar, arxiv, europepmc, core. Returns year, venue, DOI, citation
        count and open-access status. Nothing is added to the library."""
        recs = _find_remote(cfg, query, sources, limit)
        return [{k: r.get(k) for k in ("title", "authors", "year", "venue", "doi", "arxiv",
                                       "citations", "oa_status", "oa_url", "source")}
                for r in recs]

    @server.tool()
    def add_paper(identifier: str) -> dict[str, Any]:
        """Add a paper to the library from a DOI, arXiv id, PMCID, URL or local PDF path.
        Downloads a PDF only from legal open-access locations."""
        rec = Importer(cfg, lib).add(identifier)
        out = _summary(rec)
        out["already_present"] = bool(rec.get("already_present"))
        out["files"] = rec.get("files", [])
        return out

    @server.tool()
    def export_bibtex(paper_ids: list[str] | None = None) -> str:
        """Export BibTeX for the given paper ids, or for the whole library."""
        ids = paper_ids or lib.ids()
        return bibtex(lib.get(i) for i in ids)

    return server


def run(cfg: Config | None = None) -> None:
    build_server(cfg).run("stdio")

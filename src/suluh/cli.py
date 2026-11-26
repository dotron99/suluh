"""Command-line interface: `suluh <command>`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import Config, config_path, save_setting
from .export import bibtex, ris
from .importer import Importer, watch
from .library import TAGS, Library
from .sources import SEARCHERS, find_remote


def _authors_short(rec: dict) -> str:
    a = rec.get("authors") or []
    if not a:
        return "Unknown"
    first = a[0].get("family") or "Unknown"
    return first if len(a) == 1 else (f"{first} & {a[1].get('family')}" if len(a) == 2 else f"{first} et al.")


def cmd_add(args, cfg):
    imp = Importer(cfg, fetch_pdf=not args.no_pdf)
    rc = 0
    for ident in args.identifiers:
        try:
            rec = imp.add(ident)
        except Exception as e:
            print(f"Could not add {ident}: {e}", file=sys.stderr)
            rc = 1
            continue
        state = "already in library" if rec.get("already_present") else "added"
        files = ", ".join(rec.get("files", [])) or "metadata only"
        print(f"{state}: {rec['id']}  {_authors_short(rec)} ({rec.get('year') or 'n.d.'}) "
              f"{rec.get('title')}  [{files}]")
    return rc


def cmd_search(args, cfg):
    hits = Library(cfg.library).search(args.query, args.limit)
    if args.json:
        print(json.dumps(hits, indent=2, ensure_ascii=False))
        return 0
    if not hits:
        print("No matches in the local library.")
    for h in hits:
        print(f"{h['id']}  ({h['year'] or 'n.d.'}) {h['title']}")
        if h.get("snippet"):
            print(f"    {h['snippet']}")
    return 0


def cmd_find(args, cfg):
    srcs = [s.strip() for s in args.sources.split(",")] if args.sources else None
    recs = find_remote(cfg, args.query, srcs, args.limit)
    if args.json:
        print(json.dumps(recs, indent=2, ensure_ascii=False))
        return 0
    if not recs:
        print("No remote results.")
    for i, r in enumerate(recs, 1):
        oa = r.get("oa_status") or "unknown"
        cites = r.get("citations")
        print(f"{i:>2}. {r.get('title')}")
        print(f"    {_authors_short(r)} | {r.get('year') or 'n.d.'} | {r.get('venue') or 'venue unknown'}")
        print(f"    {('DOI: ' + r['doi']) if r.get('doi') else (('arXiv: ' + r['arxiv']) if r.get('arxiv') else 'DOI: none')}"
              f" | cited by {cites if cites is not None else '?'} | OA: {oa} | via {r.get('source')}")
    return 0


def cmd_list(args, cfg):
    for p in Library(cfg.library).papers():
        print(f"{p['id']}  {_authors_short(p)} ({p.get('year') or 'n.d.'}) {p.get('title')}")
    return 0


def cmd_show(args, cfg):
    lib = Library(cfg.library)
    p = lib.get(args.paper_id)
    if args.json:
        print(json.dumps(p, indent=2, ensure_ascii=False))
        return 0
    print(p.get("title"))
    print(", ".join(f"{a.get('given', '')} {a.get('family', '')}".strip() for a in p.get("authors") or []))
    print(f"{p.get('venue') or ''} ({p.get('year') or 'n.d.'})  DOI: {p.get('doi') or '-'}  "
          f"cited by {p.get('citations') if p.get('citations') is not None else '?'}  OA: {p.get('oa_status') or '?'}")
    if p.get("abstract"):
        print("\n" + p["abstract"])
    if p.get("sections"):
        print("\nSections: " + " | ".join(s["heading"] for s in p["sections"]))
    anns = lib.annotations(args.paper_id)
    if anns:
        print(f"\n{len(anns)} note(s):")
        for a in anns:
            q = f' "{a["quote"]}"' if a.get("quote") else ""
            print(f"  [{a.get('tag') or 'note'}]{q} -> {a['text']}")
    return 0


def cmd_note(args, cfg):
    ann = Library(cfg.library).add_note(args.paper_id, args.text, quote=args.quote,
                                        tag=args.tag, section=args.section)
    where = f" in section '{ann['section']}'" if ann.get("section") else ""
    if args.quote and ann["anchor_found"] is False:
        print("Note saved, but the quote was not found in the stored text; check the wording.",
              file=sys.stderr)
    print(f"Note {ann['id']} saved{where}.")
    return 0


def cmd_export(args, cfg):
    lib = Library(cfg.library)
    ids = args.ids or lib.ids()
    papers = [lib.get(i) for i in ids]
    text = bibtex(papers) if args.format == "bib" else ris(papers)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {len(papers)} reference(s) to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def cmd_reindex(args, cfg):
    n = Library(cfg.library).reindex()
    print(f"Rebuilt index.sqlite for {n} paper(s).")
    return 0


def cmd_watch(args, cfg):
    try:
        added = watch(cfg, args.folder, interval=args.interval, once=args.once)
    except KeyboardInterrupt:
        return 0
    if args.once:
        print(f"Imported {len(added)} new PDF(s).")
    return 0


def cmd_config(args, cfg):
    if args.key and args.value is not None:
        p = save_setting(args.key, args.value)
        print(f"Saved {args.key} to {p}")
        return 0
    shown = {
        "library": str(cfg.library),
        "email": cfg.email or "(not set: Unpaywall disabled)",
        "core_key": "set" if cfg.core_key else "(not set)",
        "openalex_key": "set" if cfg.openalex_key else "(not set)",
        "s2_key": "set" if cfg.s2_key else "(not set)",
        "config_file": str(config_path()),
    }
    for k, v in shown.items():
        print(f"{k:13} {v}")
    return 0


def cmd_mcp(args, cfg):
    from .mcp_server import run
    run(cfg)
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="suluh", description="Suluh: a local-first literature library.")
    ap.add_argument("--version", action="version", version=f"suluh {__version__}")
    ap.add_argument("--library", help="library folder (default: $SULUH_LIBRARY or ~/Suluh-Library)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="add papers by DOI, arXiv id, PMCID, URL or PDF path")
    p.add_argument("identifiers", nargs="+")
    p.add_argument("--no-pdf", action="store_true", help="metadata only, do not download PDFs")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("search", help="full-text search of the local library")
    p.add_argument("query")
    p.add_argument("-n", "--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("find", help="search remote sources (OpenAlex by default)")
    p.add_argument("query")
    p.add_argument("-s", "--sources", help=f"comma-separated: {','.join(SEARCHERS)} (default openalex)")
    p.add_argument("-n", "--limit", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("list", help="list papers in the library")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="show one paper")
    p.add_argument("paper_id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("note", help="add a note, optionally anchored to a quote")
    p.add_argument("paper_id")
    p.add_argument("text")
    p.add_argument("--quote", help="the exact sentence the note refers to")
    p.add_argument("--tag", choices=TAGS)
    p.add_argument("--section", help="section heading (found automatically from the quote)")
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("export", help="export references")
    p.add_argument("format", choices=["bib", "ris"])
    p.add_argument("ids", nargs="*", help="paper ids (default: all)")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("reindex", help="rebuild index.sqlite from the paper folders")
    p.set_defaults(func=cmd_reindex)

    p = sub.add_parser("watch", help="import new PDFs from a folder (polling)")
    p.add_argument("folder")
    p.add_argument("-i", "--interval", type=float, default=10.0)
    p.add_argument("--once", action="store_true", help="scan once and exit")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("config", help="show or set settings (library, email, core_key, ...)")
    p.add_argument("key", nargs="?")
    p.add_argument("value", nargs="?")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("mcp", help="run the MCP server over stdio")
    p.set_defaults(func=cmd_mcp)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.load(args.library)
    try:
        return args.func(args, cfg) or 0
    except KeyError as e:
        print(str(e).strip("'\""), file=sys.stderr)
        return 1
    except (ValueError, LookupError, NotADirectoryError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

import asyncio
import json

from suluh.cli import main
from suluh.library import Library
from suluh.mcp_server import build_server

EXPECTED = {"search_library", "get_paper", "get_notes", "add_note", "find_remote",
            "add_paper", "export_bibtex"}


def test_cli_roundtrip(cfg, sample, capsys, tmp_path):
    lib = Library(cfg.library)
    pid = lib.save(dict(sample))["id"]
    base = ["--library", str(cfg.library)]
    assert main(base + ["search", "overviews"]) == 0
    assert pid in capsys.readouterr().out
    assert main(base + ["note", pid, "Big N", "--quote", "We randomised 4,927 participants",
                        "--tag", "method"]) == 0
    assert "section 'Methods'" in capsys.readouterr().out
    out = tmp_path / "refs.bib"
    assert main(base + ["export", "bib", "-o", str(out)]) == 0
    assert out.read_text().startswith("@article{li2025trust")
    assert main(base + ["export", "ris"]) == 0
    assert "TY  - JOUR" in capsys.readouterr().out
    assert main(base + ["reindex"]) == 0
    assert "Rebuilt" in capsys.readouterr().out
    assert main(base + ["show", pid, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == pid
    assert main(base + ["show", "missing"]) == 1


def _call(server, name, args):
    res = asyncio.run(server.call_tool(name, args))
    return res


def test_mcp_tools(cfg, sample):
    lib = Library(cfg.library)
    pid = lib.save(dict(sample))["id"]
    server = build_server(cfg)
    tools = asyncio.run(server.list_tools())
    assert {t.name for t in tools} == EXPECTED
    assert _call(server, "search_library", {"query": "snippets"}) is not None
    _call(server, "add_note", {"paper_id": pid, "text": "via MCP", "tag": "idea"})
    assert lib.annotations(pid)[-1]["text"] == "via MCP"
    bib = _call(server, "export_bibtex", {})
    assert "li2025trust" in str(bib)

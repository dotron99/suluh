# Suluh

**Suluh** (Malay for "torch") is a local-first literature library for researchers. It keeps every paper in an open folder on your own computer, lets you search titles, abstracts, full text and your own notes, and gives AI agents such as Claude Code and Codex safe access to that library through an MCP server.

It is free, open source (MIT) and uses legal sources only.

> New to GitHub? Paste this link into ChatGPT or Claude and ask how to install it: https://github.com/dotron99/suluh

## What it does

- **Imports papers** from a DOI, an arXiv id, a PubMed Central id (PMCID), a URL or a PDF on your disk.
- **Finds legal open-access copies** through Unpaywall, arXiv and Europe PMC, and downloads them into the paper's folder.
- **Splits full text into sections** (Introduction, Methods and so on) from Europe PMC XML, or from the PDF as a fallback.
- **Searches your library** with a fast full-text index that covers your notes too.
- **Searches the wider literature** through OpenAlex, Semantic Scholar, arXiv, Europe PMC and CORE, showing year, venue, DOI, citation count and open-access status.
- **Anchors notes** to an exact quoted sentence, records which section it came from, and tags it as `idea`, `method`, `data` or `question`.
- **Exports** BibTeX and RIS for Zotero, EndNote, Mendeley or LaTeX.
- **Watches a folder** (for example your Downloads or a Google Drive folder) and imports new PDFs automatically.
- **Talks to agents** through a built-in MCP server.

Suluh never uses Sci-Hub or any other pirate source. For paywalled papers, download the PDF through your own institutional login and add it with `suluh add paper.pdf`.

## Install

You need Python 3.10 or newer.

```bash
pip install git+https://github.com/dotron99/suluh
```

Or, to keep it isolated (recommended):

```bash
pipx install git+https://github.com/dotron99/suluh
```

Then set the email address that Unpaywall and Crossref ask polite users to send (it is only sent to those services, as their terms request):

```bash
suluh config email you@university.edu
```

## Quick start

```bash
suluh add 2106.15183                       # arXiv id
suluh add 10.1038/s41586-020-2649-2        # DOI
suluh add PMC13719773                      # PubMed Central, with sections
suluh add ~/Downloads/some-paper.pdf       # a PDF you already have
suluh add https://doi.org/10.1145/3313831.3376727

suluh list
suluh search "exit branches"               # local full-text search
suluh find "trust in AI search overviews"  # remote search (OpenAlex)
suluh find "AI literacy" -s openalex,semanticscholar,europepmc -n 5

suluh note bakhtiarnia2021multi "Seven exit heads, compare by budget" \
  --quote "we propose seven different architectures for early exit branches" --tag method
suluh show bakhtiarnia2021multi

suluh export bib -o references.bib
suluh export ris -o references.ris
suluh watch ~/Downloads/papers             # Ctrl+C to stop; --once to scan once
suluh reindex                              # rebuild the search index
```

## Where your files live

The library is a plain folder, by default `~/Suluh-Library`. Change it with `suluh config library /path/to/folder`, the `SULUH_LIBRARY` environment variable, or `--library` on any command.

```
Suluh-Library/
  harris2020array/
    paper.json          metadata, abstract and parsed sections
    notes.md            your notes, readable in any editor
    annotations.json    notes anchored to quoted sentences
    source/
      paper.pdf         the open-access PDF, if there is one
      fulltext.xml      Europe PMC full text, if there is one
  index.sqlite          search index; delete it any time and run `suluh reindex`
```

Everything is JSON, Markdown, XML or PDF. You can back it up, sync it, or put it under version control. Nothing is uploaded anywhere.

## Settings

| Setting | Environment variable | Purpose |
|---|---|---|
| `library` | `SULUH_LIBRARY` | Library folder |
| `email` | `SULUH_EMAIL` | Contact email for Unpaywall and Crossref. Unpaywall is skipped without it |
| `core_key` | `SULUH_CORE_KEY` | Free API key from core.ac.uk, enables `-s core` |
| `openalex_key` | `SULUH_OPENALEX_KEY` | Optional OpenAlex key for higher limits |
| `s2_key` | `SULUH_S2_KEY` | Optional Semantic Scholar key (the public API is often rate limited) |

Run `suluh config` to see the current values. Keys are stored in `~/.config/suluh/config.json` with owner-only permissions and are never printed.

## Use it from Claude Code or Codex (MCP)

`suluh mcp` starts an MCP server over stdio with these tools:

| Tool | What it does |
|---|---|
| `search_library` | Full-text search of your library, including notes |
| `get_paper` | Metadata, abstract and (optionally) the full text by section |
| `get_notes` | Your notes and anchored annotations for a paper |
| `add_note` | Add a note, optionally anchored to a quote and tagged |
| `find_remote` | Search OpenAlex, Semantic Scholar, arXiv, Europe PMC and CORE |
| `add_paper` | Add a paper by DOI, arXiv id, PMCID, URL or PDF path |
| `export_bibtex` | BibTeX for some or all papers |

**Claude Code**

```bash
claude mcp add suluh -- suluh mcp
```

To pass settings, add them with `-e`, for example `claude mcp add suluh -e SULUH_EMAIL=you@university.edu -- suluh mcp`.

**Codex** (add to `~/.codex/config.toml`)

```toml
[mcp_servers.suluh]
command = "suluh"
args = ["mcp"]

[mcp_servers.suluh.env]
SULUH_EMAIL = "you@university.edu"
# SULUH_LIBRARY = "/Users/you/Suluh-Library"
```

If your agent cannot find the `suluh` command, use the full path from `which suluh`.

Then ask, for example: "Search my Suluh library for papers on AI trust and summarise the methods sections, citing each paper by its id."

## Works well with paperrocks

[paperrocks](https://github.com/dotron99/paperrocks) audits the structure of a paper you are writing. Suluh holds the literature behind it. With both installed, an agent can check each claim in your draft against the papers and notes in your library.

## Roadmap

- Side-by-side translation of papers, sentence by sentence, using your own API key or a local model through Ollama
- Journal quartile and ranking display (SJR and similar open sources)
- A desktop reading app with notes in the margin
- A direct paperrocks integration: claim maps linked to library evidence
- Zotero import and two-way sync
- Better section detection for PDFs

Ideas and pull requests are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Limitations

- PDF section detection is a simple heading match; Europe PMC XML gives far better sections.
- Semantic Scholar's public API often answers "too many requests" without a key; Suluh skips it and carries on.
- Some publishers block automated PDF downloads even for open-access papers. Suluh keeps the metadata, and you can add the PDF by hand.
- `suluh watch` polls the folder rather than using file-system events.

## Licence

MIT. See [LICENSE](LICENSE).

Suluh is an independent project. It was inspired by the idea of local-first, agent-ready reference managers, and contains no code from any other product.

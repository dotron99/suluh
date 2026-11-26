# Contributing to Suluh

Thank you for helping. Suluh aims to stay small, local-first and easy to read.

## Set up

```bash
git clone https://github.com/dotron99/suluh.git
cd suluh
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Ground rules

- **Legal sources only.** Pull requests that add Sci-Hub, LibGen or any other pirate source will be closed.
- **Your data stays local.** No telemetry, no uploads, no accounts.
- **Open files first.** Anything Suluh stores should be readable without Suluh (JSON, Markdown, XML, PDF). The SQLite index must always be rebuildable with `suluh reindex`.
- **Tests do not touch the network.** Mock HTTP calls with `respx` (see `tests/test_importer.py`).
- **Never invent data.** If a source does not return a field, leave it empty.
- **stdout is sacred in `suluh mcp`.** Log to stderr only.

## Style

- Python 3.10+, standard library where possible, type hints on public functions.
- Documentation in British English, plain and direct.

## Good first issues

- Zotero RDF or CSL-JSON import
- Better PDF section detection
- Journal quartile lookup from open data
- A translation command that uses Ollama

Open an issue first for anything large so we can agree the approach.

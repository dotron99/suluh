"""The on-disk library: one folder per paper, open files, rebuildable index.

Layout::

    Suluh-Library/
      <paper-id>/
        paper.json        metadata, abstract, parsed sections
        notes.md          free notes (Markdown)
        annotations.json  notes anchored to a quoted sentence
        source/           original PDF or XML
      index.sqlite        full-text index, safe to delete (see `suluh reindex`)
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

TAGS = ("idea", "method", "data", "question")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def make_id(rec: dict) -> str:
    """Readable id: firstauthor + year + first significant title word."""
    fam = ""
    if rec.get("authors"):
        fam = rec["authors"][0].get("family") or ""
    fam = re.sub(r"[^a-z]", "", _ascii(fam).lower()) or "anon"
    year = str(rec.get("year") or "nd")
    stop = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "with", "towards", "toward"}
    words = [w for w in re.findall(r"[a-z0-9]+", _ascii(rec.get("title") or "").lower())
             if w not in stop]
    word = words[0] if words else "untitled"
    return f"{fam}{year}{word}"[:60]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


class Library:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.sqlite"

    # ------------------------------------------------------------ papers
    def paper_dir(self, pid: str) -> Path:
        return self.root / pid

    def ids(self) -> list[str]:
        return sorted(p.name for p in self.root.iterdir()
                      if p.is_dir() and (p / "paper.json").exists())

    def papers(self) -> Iterator[dict]:
        for pid in self.ids():
            yield self.get(pid)

    def exists(self, pid: str) -> bool:
        return (self.paper_dir(pid) / "paper.json").exists()

    def get(self, pid: str) -> dict:
        p = self.paper_dir(pid) / "paper.json"
        if not p.exists():
            raise KeyError(f"No paper with id '{pid}' in {self.root}")
        return json.loads(p.read_text(encoding="utf-8"))

    def find_existing(self, rec: dict) -> str | None:
        """Return the id of a paper already in the library with the same identifier."""
        keys = [k for k in ("doi", "arxiv", "pmcid", "sha256") if rec.get(k)]
        if not keys:
            return None
        for paper in self.papers():
            for k in keys:
                if paper.get(k) and str(paper[k]).lower() == str(rec[k]).lower():
                    return paper["id"]
        return None

    def save(self, rec: dict) -> dict:
        if not rec.get("id"):
            base = make_id(rec)
            pid, n = base, 1
            while self.exists(pid):
                n += 1
                pid = f"{base}{chr(ord('a') + n - 2)}" if n <= 27 else f"{base}{n}"
            rec["id"] = pid
        rec.setdefault("added", now())
        rec["updated"] = now()
        d = self.paper_dir(rec["id"])
        (d / "source").mkdir(parents=True, exist_ok=True)
        (d / "paper.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False), encoding="utf-8")
        if not (d / "notes.md").exists():
            (d / "notes.md").write_text(f"# Notes: {rec.get('title') or rec['id']}\n\n", encoding="utf-8")
        if not (d / "annotations.json").exists():
            (d / "annotations.json").write_text("[]\n", encoding="utf-8")
        self.index_one(rec)
        return rec

    # ------------------------------------------------------------ notes
    def notes(self, pid: str) -> str:
        p = self.paper_dir(pid) / "notes.md"
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def annotations(self, pid: str) -> list[dict]:
        p = self.paper_dir(pid) / "annotations.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    def locate_quote(self, paper: dict, quote: str) -> str | None:
        """Return the heading of the section that contains the quote, if any."""
        norm = lambda s: re.sub(r"\s+", " ", s or "").strip().lower()  # noqa: E731
        q = norm(quote)
        if not q:
            return None
        if q in norm(paper.get("abstract")):
            return "Abstract"
        for sec in paper.get("sections") or []:
            if q in norm(sec.get("text")):
                return sec.get("heading")
        return None

    def add_note(self, pid: str, text: str, quote: str | None = None,
                 tag: str | None = None, section: str | None = None) -> dict:
        paper = self.get(pid)
        if tag and tag not in TAGS:
            raise ValueError(f"Tag must be one of: {', '.join(TAGS)}")
        found = None
        if quote:
            located = self.locate_quote(paper, quote)
            found = located is not None
            section = section or located
        ann = {
            "id": uuid.uuid4().hex[:8],
            "quote": quote,
            "section": section,
            "tag": tag,
            "text": text,
            "anchor_found": found,
            "created": now(),
        }
        anns = self.annotations(pid)
        anns.append(ann)
        (self.paper_dir(pid) / "annotations.json").write_text(
            json.dumps(anns, indent=2, ensure_ascii=False), encoding="utf-8")
        # Mirror into notes.md so the notes stay readable without any tool.
        lines = [f"\n## [{tag or 'note'}] {ann['created']}  (id {ann['id']})"]
        if section:
            lines.append(f"Section: {section}")
        if quote:
            lines.append(f"> {quote}")
        lines.append(f"\n{text}\n")
        with open(self.paper_dir(pid) / "notes.md", "a", encoding="utf-8") as f:
            f.write("\n".join(lines))
        self.index_one(paper)
        return ann

    # ------------------------------------------------------------ index
    def _db(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.index_path)
        con.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS papers USING fts5("
            "id UNINDEXED, title, authors, venue, year UNINDEXED, abstract, body, notes, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        return con

    def _row(self, rec: dict) -> tuple:
        pid = rec["id"]
        authors = "; ".join(f"{a.get('given', '')} {a.get('family', '')}".strip()
                            for a in rec.get("authors") or [])
        body = "\n".join(s.get("text", "") for s in rec.get("sections") or [])
        notes = self.notes(pid) + "\n" + "\n".join(
            f"{a.get('quote') or ''} {a.get('text') or ''} {a.get('tag') or ''}"
            for a in self.annotations(pid))
        return (pid, rec.get("title") or "", authors, rec.get("venue") or "",
                str(rec.get("year") or ""), rec.get("abstract") or "", body, notes)

    def index_one(self, rec: dict) -> None:
        con = self._db()
        with con:
            con.execute("DELETE FROM papers WHERE id = ?", (rec["id"],))
            con.execute("INSERT INTO papers VALUES (?,?,?,?,?,?,?,?)", self._row(rec))
        con.close()

    def reindex(self) -> int:
        if self.index_path.exists():
            self.index_path.unlink()
        con = self._db()
        n = 0
        with con:
            for rec in self.papers():
                con.execute("INSERT INTO papers VALUES (?,?,?,?,?,?,?,?)", self._row(rec))
                n += 1
        con.close()
        return n

    def search(self, query: str, limit: int = 20) -> list[dict]:
        con = self._db()
        sql = ("SELECT id, title, year, venue, "
               "snippet(papers, -1, '[', ']', ' ... ', 12), bm25(papers, 0, 10, 5, 2, 0, 4, 1, 3) "
               "FROM papers WHERE papers MATCH ? ORDER BY 6 LIMIT ?")
        try:
            rows = con.execute(sql, (query, limit)).fetchall()
        except sqlite3.OperationalError:
            # Fall back to a quoted phrase-per-word query if FTS syntax was invalid.
            safe = " ".join(f'"{w}"' for w in re.findall(r"\w+", query))
            rows = con.execute(sql, (safe, limit)).fetchall() if safe else []
        con.close()
        return [{"id": r[0], "title": r[1], "year": r[2], "venue": r[3], "snippet": r[4]}
                for r in rows]

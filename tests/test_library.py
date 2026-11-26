import json

import pytest

from suluh.library import Library, make_id


def test_make_id():
    assert make_id({"authors": [{"family": "Çiçek"}], "year": 2024,
                    "title": "The Shape of Trust"}) == "cicek2024shape"
    assert make_id({}) == "anonnduntitled"


def test_save_creates_open_files(lib, sample):
    rec = lib.save(dict(sample))
    d = lib.paper_dir(rec["id"])
    assert rec["id"] == "li2025trust"
    assert json.loads((d / "paper.json").read_text())["doi"] == "10.1234/abc.5"
    assert (d / "notes.md").exists()
    assert json.loads((d / "annotations.json").read_text()) == []
    assert (d / "source").is_dir()
    assert (lib.root / "index.sqlite").exists()


def test_id_collision(lib, sample):
    a = lib.save(dict(sample))
    b = lib.save({**sample, "doi": "10.1234/other"})
    assert a["id"] != b["id"] and b["id"].startswith("li2025trust")


def test_find_existing(lib, sample):
    rec = lib.save(dict(sample))
    assert lib.find_existing({"doi": "10.1234/ABC.5"}) == rec["id"]
    assert lib.find_existing({"doi": "10.9/none"}) is None


def test_search_and_reindex(lib, sample):
    rec = lib.save(dict(sample))
    hits = lib.search("randomised participants")
    assert hits and hits[0]["id"] == rec["id"]
    assert lib.search("snippets")[0]["id"] == rec["id"]
    (lib.root / "index.sqlite").unlink()
    assert lib.reindex() == 1
    assert lib.search("overviews")[0]["id"] == rec["id"]
    # invalid FTS syntax falls back gracefully
    assert isinstance(lib.search('AI "overviews'), list)


def test_anchored_note(lib, sample):
    rec = lib.save(dict(sample))
    ann = lib.add_note(rec["id"], "Large sample", quote="randomised 4,927 participants",
                       tag="method")
    assert ann["section"] == "Methods" and ann["anchor_found"] is True
    assert lib.annotations(rec["id"])[0]["tag"] == "method"
    assert "> randomised 4,927 participants" in lib.notes(rec["id"])
    assert lib.search("Large sample")[0]["id"] == rec["id"]
    miss = lib.add_note(rec["id"], "x", quote="not in the paper")
    assert miss["anchor_found"] is False and miss["section"] is None


def test_bad_tag(lib, sample):
    rec = lib.save(dict(sample))
    with pytest.raises(ValueError):
        lib.add_note(rec["id"], "x", tag="banana")


def test_missing_paper(lib):
    with pytest.raises(KeyError):
        lib.get("nope")

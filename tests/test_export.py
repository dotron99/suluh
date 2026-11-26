from suluh.export import bibtex, ris


def test_bibtex(sample):
    p = {**sample, "id": "li2025trust", "venue": "R&D Journal", "pages": "1-10"}
    b = bibtex([p])
    assert b.startswith("@article{li2025trust,")
    assert "author = {Li, Haiwen and Aral, Sinan}" in b
    assert "journal = {R\\&D Journal}" in b
    assert "pages = {1--10}" in b
    assert "doi = {10.1234/abc.5}" in b


def test_bibtex_arxiv():
    p = {"id": "x2021y", "title": "T", "authors": [], "year": 2021, "arxiv": "2106.15183",
         "type": "preprint"}
    b = bibtex([p])
    assert b.startswith("@misc{x2021y,") and "eprint = {2106.15183}" in b


def test_ris(sample):
    r = ris([{**sample, "id": "li2025trust", "pages": "5-9"}])
    assert r.startswith("TY  - JOUR")
    assert "AU  - Li, Haiwen" in r and "DO  - 10.1234/abc.5" in r
    assert "SP  - 5" in r and "EP  - 9" in r and r.rstrip().endswith("ER  -")

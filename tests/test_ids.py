import pytest

from suluh.ids import classify, clean_doi, find_doi


@pytest.mark.parametrize("raw,kind,value", [
    ("10.1038/s41586-020-2649-2", "doi", "10.1038/s41586-020-2649-2"),
    ("https://doi.org/10.1145/3313831.3376727", "doi", "10.1145/3313831.3376727"),
    ("doi:10.1000/XYZ.", "doi", "10.1000/xyz"),
    ("2106.15183", "arxiv", "2106.15183"),
    ("arXiv:2106.15183v2", "arxiv", "2106.15183"),
    ("https://arxiv.org/abs/2106.15183v1", "arxiv", "2106.15183"),
    ("https://arxiv.org/pdf/2106.15183.pdf", "arxiv", "2106.15183"),
    ("hep-th/9901001", "arxiv", "hep-th/9901001"),
    ("PMC7096803", "pmcid", "PMC7096803"),
    ("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7096803/", "pmcid", "PMC7096803"),
    ("https://example.org/paper", "url", "https://example.org/paper"),
])
def test_classify(raw, kind, value):
    i = classify(raw)
    assert (i.kind, i.value) == (kind, value)


def test_classify_pdf(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF-1.4")
    assert classify(str(p)).kind == "pdf"


def test_classify_bad():
    with pytest.raises(ValueError):
        classify("not an identifier")


def test_find_doi():
    assert find_doi("see https://doi.org/10.1016/j.chb.2024.108123.") == "10.1016/j.chb.2024.108123"
    assert find_doi("nothing here") is None
    assert clean_doi("https://dx.doi.org/10.1/ABC") == "10.1/abc"

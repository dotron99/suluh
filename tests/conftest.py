import pytest

from suluh.config import Config
from suluh.library import Library


def make_pdf(lines: list[str]) -> bytes:
    """Build a tiny valid one-page PDF with the given text lines."""
    content = "BT /F1 12 Tf 72 720 Td 14 TL " + " ".join(
        "(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*"
        for ln in lines) + " ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("SULUH_EMAIL", "tester@example.org")
    monkeypatch.delenv("SULUH_CORE_KEY", raising=False)
    monkeypatch.delenv("SULUH_LIBRARY", raising=False)
    return Config.load(tmp_path / "lib")


@pytest.fixture
def lib(cfg):
    return Library(cfg.library)


@pytest.fixture
def sample():
    return {
        "title": "Trust in AI search overviews",
        "authors": [{"family": "Li", "given": "Haiwen"}, {"family": "Aral", "given": "Sinan"}],
        "year": 2025, "venue": "Test Journal", "doi": "10.1234/abc.5",
        "abstract": "People trust generative answers more than snippets. We ran an experiment.",
        "type": "journal-article", "citations": 3, "oa_status": "gold",
        "sections": [
            {"heading": "Introduction", "level": 1, "text": "Search engines now show AI overviews."},
            {"heading": "Methods", "level": 1, "text": "We randomised 4,927 participants to six conditions."},
        ],
    }

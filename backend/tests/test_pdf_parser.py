"""Real local PDF extraction, including page boundaries, without a database."""
import pymupdf
import pytest

from app.services.parsing.parser import parse_pdf


def test_pdf_extraction_preserves_text_and_one_based_page_metadata(tmp_path):
    path = tmp_path / "synthetic.pdf"
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), "Synthetic liquidity research")
        document.new_page()
        document.new_page().insert_text((72, 72), "Second research section")
        document.save(path)
    assert parse_pdf(str(path)) == [
        {"page_num": 1, "text": "Synthetic liquidity research"},
        {"page_num": 2, "text": ""},
        {"page_num": 3, "text": "Second research section"},
    ]


def test_invalid_pdf_still_reports_parse_failure(tmp_path):
    path = tmp_path / "invalid.pdf"
    path.write_bytes(b"This is not a PDF")
    with pytest.raises(RuntimeError, match="Failed to parse PDF"):
        parse_pdf(str(path))

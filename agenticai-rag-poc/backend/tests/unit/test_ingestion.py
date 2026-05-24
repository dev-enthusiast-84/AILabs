import io
import pytest
import openpyxl
import fitz  # PyMuPDF — matches the primary extractor used in production
from app.rag.ingestion import (
    validate_extension,
    extract_text_from_txt,
    extract_text_from_csv,
    extract_text_from_pdf,
    extract_text_from_excel,
    ingest_document,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_pdf(text: str = "Sample document content for testing.") -> bytes:
    """Produce a minimal valid PDF with one page of readable text.

    Uses PyMuPDF so the extraction tests use the same library path as production.
    """
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((50, 72), text, fontsize=12)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_xlsx(headers: list, rows: list[list]) -> bytes:
    """Produce a minimal xlsx from headers + row data."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Extension validation ───────────────────────────────────────────────────────

def test_validate_extension_allowed():
    assert validate_extension("report.pdf") == ".pdf"
    assert validate_extension("data.CSV") == ".csv"
    assert validate_extension("sheet.xlsx") == ".xlsx"
    assert validate_extension("legacy.xls") == ".xls"


def test_validate_extension_disallowed():
    with pytest.raises(ValueError, match="Unsupported file type"):
        validate_extension("script.exe")


# ── TXT extraction ─────────────────────────────────────────────────────────────

def test_extract_txt():
    content = b"Hello world\nLine two."
    text = extract_text_from_txt(content)
    assert "Hello world" in text
    assert "Line two" in text


def test_extract_txt_latin1_fallback():
    """Bytes that are valid latin-1 but not utf-8 should decode via latin-1 fallback."""
    content = "Résumé café".encode("latin-1")
    text = extract_text_from_txt(content)
    assert "sum" in text   # "Résumé" survives; exact chars depend on decode


# ── CSV extraction ─────────────────────────────────────────────────────────────

def test_extract_csv():
    content = b"col1,col2\nval1,val2\n"
    text = extract_text_from_csv(content)
    assert "col1" in text
    assert "val1" in text


# ── PDF extraction ─────────────────────────────────────────────────────────────

def test_extract_pdf_returns_string():
    """extract_text_from_pdf should not raise on a valid blank-page PDF."""
    content = _make_pdf()
    text = extract_text_from_pdf(content)
    assert isinstance(text, str)


def test_extract_pdf_page_marker():
    """Page marker and document body text should appear in extracted output."""
    content = _make_pdf("Hello from the attention paper.")
    text = extract_text_from_pdf(content)
    assert "[Page 1]" in text
    assert "attention" in text.lower()


def test_extract_pdf_multi_page():
    """PyMuPDF should extract all pages with correct markers."""
    doc = fitz.open()
    for i, line in enumerate(["First page content.", "Second page content."]):
        page = doc.new_page(width=612, height=792)
        page.insert_text((50, 72), line, fontsize=12)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    text = extract_text_from_pdf(buf.getvalue())
    assert "[Page 1]" in text
    assert "[Page 2]" in text
    assert "First page" in text
    assert "Second page" in text


# ── Excel extraction ───────────────────────────────────────────────────────────

def test_extract_excel_contains_headers():
    content = _make_xlsx(["Name", "Score"], [["Alice", 95], ["Bob", 80]])
    text = extract_text_from_excel(content)
    assert "Name" in text
    assert "Score" in text


def test_extract_excel_contains_values():
    content = _make_xlsx(["Department", "Budget"], [["Engineering", 500000]])
    text = extract_text_from_excel(content)
    assert "Engineering" in text


def test_extract_excel_sheet_marker():
    content = _make_xlsx(["X"], [[1]])
    text = extract_text_from_excel(content)
    assert "[Sheet:" in text


def test_extract_csv_includes_column_summary():
    """Improved CSV extractor prefixes column names and row count."""
    csv_bytes = b"name,age\nAlice,30\nBob,25\n"
    text = extract_text_from_csv(csv_bytes)
    assert "name" in text.lower()
    assert "Alice" in text
    assert "Rows:" in text


def test_extract_pdf_empty_page_still_has_marker():
    """Blank-page PDFs produce a page marker even with no extractable text."""
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    text = extract_text_from_pdf(buf.getvalue())
    # Should have the [Page 1] marker from either PyMuPDF or pypdf fallback
    assert "[Page 1]" in text


# ── ingest_document ────────────────────────────────────────────────────────────

def test_ingest_document_txt():
    text = ingest_document("doc.txt", b"Sample enterprise content.")
    assert "Sample enterprise content" in text


def test_ingest_document_csv():
    text = ingest_document("data.csv", b"dept,budget\nEng,500000\n")
    assert "Eng" in text


def test_ingest_document_pdf():
    text = ingest_document("report.pdf", _make_pdf("Annual report content."))
    assert isinstance(text, str)
    assert "Annual report" in text


def test_ingest_document_xlsx():
    content = _make_xlsx(["Employee", "Salary"], [["Alice", 90000]])
    text = ingest_document("payroll.xlsx", content)
    assert "Alice" in text


def test_ingest_document_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        ingest_document("empty.txt", b"   ")


def test_ingest_document_bad_ext():
    with pytest.raises(ValueError):
        ingest_document("malware.exe", b"bad content")


# ── PDF extraction: PyMuPDF fallback to pypdf (lines 45-55) ──────────────────

def test_extract_pdf_falls_back_to_pypdf_when_fitz_raises():
    """When PyMuPDF (fitz) raises, extract_text_from_pdf falls back to pypdf."""
    from unittest.mock import patch, MagicMock

    # Build a real single-page PDF with pypdf so the fallback actually works
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    with patch("fitz.open", side_effect=Exception("fitz unavailable")):
        text = extract_text_from_pdf(pdf_bytes)

    # pypdf fallback must still return a string with a page marker
    assert isinstance(text, str)
    assert "[Page 1]" in text


def test_extract_pdf_fitz_returns_empty_page_text():
    """When PyMuPDF returns an empty string for a page, only the page marker is kept."""
    from unittest.mock import patch, MagicMock

    mock_page = MagicMock()
    mock_page.get_text.return_value = ""   # empty page text
    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
    mock_doc.__enter__ = MagicMock(return_value=mock_doc)
    mock_doc.__exit__ = MagicMock(return_value=False)

    with patch("fitz.open", return_value=mock_doc):
        text = extract_text_from_pdf(b"fake-pdf-bytes")

    assert "[Page 1]" in text


def test_extract_pdf_fitz_nonempty_page_includes_content():
    """When PyMuPDF returns non-empty text, the content is included in the result."""
    from unittest.mock import patch, MagicMock

    mock_page = MagicMock()
    mock_page.get_text.return_value = "Hello from fitz page."
    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
    mock_doc.__enter__ = MagicMock(return_value=mock_doc)
    mock_doc.__exit__ = MagicMock(return_value=False)

    with patch("fitz.open", return_value=mock_doc):
        text = extract_text_from_pdf(b"fake-pdf-bytes")

    assert "Hello from fitz page" in text
    assert "[Page 1]" in text


# ── TXT extraction: latin-1 handles any byte sequence (line 64) ──────────────

def test_extract_txt_arbitrary_bytes_returns_string():
    """extract_text_from_txt handles arbitrary byte sequences via latin-1."""
    # latin-1 maps byte 0x00-0xFF directly to Unicode — always succeeds.
    # The function tries utf-8-sig, utf-8, latin-1 in order; any pure-latin-1
    # bytes that fail utf-8 will be caught and decoded by the latin-1 branch.
    result = extract_text_from_txt(b"\xff\xfe\x80\xa3hello")
    assert isinstance(result, str)
    assert len(result) > 0


# ── CSV extraction: all-encoding-fail else branch (lines 73-76) ───────────────

def test_extract_csv_latin1_fallback_when_all_encodings_fail():
    """When utf-8-sig, utf-8, and latin-1 all raise ParserError, the else branch runs."""
    import pandas as pd
    from unittest.mock import patch, MagicMock

    # Simulate pd.read_csv raising ParserError for the three primary encodings,
    # then succeeding on the else-branch call with encoding="latin-1", errors="replace".
    call_count = [0]

    def fake_read_csv(buf, encoding="utf-8", errors=None):
        call_count[0] += 1
        if call_count[0] <= 3:
            raise pd.errors.ParserError("forced parser error")
        # Final fallback call — return a simple DataFrame
        df = pd.DataFrame({"col1": ["val1"], "col2": ["val2"]})
        return df

    with patch("pandas.read_csv", side_effect=fake_read_csv):
        text = extract_text_from_csv(b"bad,csv\ndata")

    assert isinstance(text, str)
    assert call_count[0] == 4  # 3 failed + 1 fallback


def test_extract_csv_unicode_decode_error_triggers_fallback():
    """UnicodeDecodeError in CSV parsing also triggers the fallback else branch."""
    import pandas as pd
    from unittest.mock import patch

    call_count = [0]

    def fake_read_csv(buf, encoding="utf-8", errors=None):
        call_count[0] += 1
        if call_count[0] <= 3:
            raise UnicodeDecodeError(encoding, b"", 0, 1, "forced")
        df = pd.DataFrame({"name": ["Alice"], "score": [100]})
        return df

    with patch("pandas.read_csv", side_effect=fake_read_csv):
        text = extract_text_from_csv(b"\xff\xfe bad data")

    assert isinstance(text, str)
    assert call_count[0] == 4

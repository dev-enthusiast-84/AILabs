import io
import re
from pathlib import Path

import pandas as pd
import structlog

log = structlog.get_logger()

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".csv", ".xlsx", ".xls"}


def validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
    return ext


def _sanitize_text(text: str) -> str:
    """Strip null bytes and excessive whitespace."""
    text = text.replace("\x00", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_pdf(content: bytes) -> str:
    """Extract text using PyMuPDF (primary) with pypdf fallback.

    PyMuPDF preserves reading order across multi-column layouts and handles
    academic papers, equations, and complex formatting far better than pypdf.
    pypdf is retained as a fallback in case fitz is unavailable.
    """
    try:
        import fitz  # PyMuPDF — best reading-order extraction for complex PDFs
        doc = fitz.open(stream=content, filetype="pdf")
        pages = []
        for i, page in enumerate(doc):
            # "text" mode extracts in natural reading order with proper line breaks
            text = page.get_text("text").strip()
            pages.append(f"[Page {i + 1}]\n{text}" if text else f"[Page {i + 1}]")
        doc.close()
        if pages:
            return _sanitize_text("\n\n".join(pages))
    except Exception as exc:
        log.warning("pymupdf_failed_falling_back_to_pypdf", error_type=type(exc).__name__)

    # Fallback: pypdf (works well for simple, single-column PDFs)
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for i, page in enumerate(reader.pages):
        text = (page.extract_text() or "").strip()
        pages.append(f"[Page {i + 1}]\n{text}" if text else f"[Page {i + 1}]")
    return _sanitize_text("\n\n".join(pages))


def extract_text_from_txt(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return _sanitize_text(content.decode(encoding))
        except UnicodeDecodeError:
            continue
    return _sanitize_text(content.decode("latin-1", errors="replace"))


def extract_text_from_csv(content: bytes) -> str:
    # Try common encodings; many CSV exports from Excel use cp1252 / latin-1
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(content), encoding=encoding)
            break
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    else:
        df = pd.read_csv(io.BytesIO(content), encoding="latin-1", errors="replace")

    # Fill NaN so to_string doesn't print 'NaN' for empty cells
    df = df.fillna("")
    rows, cols = df.shape
    header = f"Columns ({cols}): {', '.join(str(c) for c in df.columns)}\nRows: {rows}\n"
    return _sanitize_text(header + df.to_string(index=False))


def extract_text_from_excel(content: bytes) -> str:
    xl = pd.ExcelFile(io.BytesIO(content))
    parts = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet).fillna("")
        rows, cols = df.shape
        header = f"[Sheet: {sheet}] — {rows} rows × {cols} columns"
        parts.append(f"{header}\n{df.to_string(index=False)}")
    return _sanitize_text("\n\n".join(parts))


def ingest_document(filename: str, content: bytes) -> str:
    ext = validate_extension(filename)
    log.info("ingesting_document", filename=filename, ext=ext, size_bytes=len(content))

    extractors = {
        ".pdf": extract_text_from_pdf,
        ".txt": extract_text_from_txt,
        ".csv": extract_text_from_csv,
        ".xlsx": extract_text_from_excel,
        ".xls": extract_text_from_excel,
    }
    text = extractors[ext](content)

    if not text.strip():
        raise ValueError("Document appears to be empty or could not be parsed.")

    return text

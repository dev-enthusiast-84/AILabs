import structlog
import time
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.audit import audit_event
from app.auth.utils import get_current_user, is_token_revoked, require_full_access
from app.auth.models import UserInDB
from app.config import get_settings
from app.core.errors import SafeAppError, safe_app_error_from_exception
from app.guardrails.safety import validate_filename
from app.rag.chunking import chunk_text
from app.rag.file_store import (
    delete_chunk_manifest,
    delete_file,
    read_chunk_manifest,
    read_file,
    save_chunk_manifest,
    save_file,
)
from app.rag.ingestion import ingest_document
from app.rag.scanner import scan_upload
from app.rag.vector_store import (
    _stitch_chunks,
    add_documents,
    delete_document,
    document_exists,
    get_all_documents,
    get_document_chunks,
    invalidate_doc_cache,
)

log = structlog.get_logger()
settings = get_settings()
router = APIRouter()


def _chunks_from_docs(docs) -> list[str]:
    return [doc.metadata.get("raw_chunk") or doc.page_content for doc in docs if doc.page_content.strip()]


def _cleanup_document_storage(filename: str) -> None:
    for cleanup in (delete_document, delete_file, delete_chunk_manifest):
        try:
            cleanup(filename)
        except Exception as exc:
            log.warning("document_upload_cleanup_failed", filename=filename, cleanup=cleanup.__name__, error_type=type(exc).__name__)


def _delete_stale_document(source_key: str) -> None:
    """Best-effort cleanup for index entries that no longer have usable storage."""
    _cleanup_document_storage(source_key)
    invalidate_doc_cache()
    log.info("stale_document_removed", filename=source_key)


def _document_source_key(filename: str, user: UserInDB) -> str:
    if user.role == "guest":
        session = user.session_id or user.username
        prefix = f"guest-{session}-"
        if filename.startswith(prefix):
            return filename
        return f"{prefix}{filename}"
    return filename


def _guest_display_filename(source: str, metadata: dict) -> str:
    session = metadata.get("owner_session")
    if not isinstance(session, str) or not session:
        return source
    prefix = f"guest-{session}-"
    if source.startswith(prefix):
        return source[len(prefix):] or source
    return source


def _document_metadata(filename: str, source_key: str, user: UserInDB) -> dict[str, str]:
    return {
        "source": source_key,
        "filename": filename,
        "owner_role": user.role,
        "owner_username": user.username,
        "owner_session": user.session_id or "",
        "uploaded_at": str(int(time.time())),
    }


def _display_filename(source: str, metadata: dict) -> str:
    filename = metadata.get("filename")
    if isinstance(filename, str) and filename:
        return filename
    if metadata.get("owner_role") == "guest":
        return _guest_display_filename(source, metadata)
    return source


def _document_availability(source_key: str) -> str:
    """Return usable, stale, or unknown for a stored document source."""
    try:
        has_vector_chunks = bool(get_document_chunks(source_key))
    except Exception as exc:
        log.warning("document_availability_vector_read_failed", filename=source_key, error_type=type(exc).__name__)
        return "unknown"
    if not has_vector_chunks:
        return "stale"

    storage_error = False
    try:
        if read_chunk_manifest(source_key):
            return "usable"
    except Exception as exc:
        storage_error = True
        log.warning("document_availability_manifest_read_failed", filename=source_key, error_type=type(exc).__name__)
    try:
        if read_file(source_key) is not None:
            return "usable"
    except Exception as exc:
        storage_error = True
        log.warning("document_availability_file_read_failed", filename=source_key, error_type=type(exc).__name__)
    return "unknown" if storage_error else "stale"


def _candidate_is_upload_duplicate(source_key: str) -> bool:
    if not document_exists(source_key):
        return False
    availability = _document_availability(source_key)
    if availability == "usable":
        return True
    if availability == "stale":
        _delete_stale_document(source_key)
        return False
    raise SafeAppError(
        category="retrieval_error",
        public_message="Document storage is temporarily unavailable.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _list_visible_document_names(user: UserInDB) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    if user.role == "guest":
        session = user.session_id or ""
        for doc in get_all_documents():
            meta = doc.metadata or {}
            if meta.get("owner_role") != "guest" or meta.get("owner_session") != session:
                continue
            source = meta.get("source", "unknown")
            availability = _document_availability(source)
            if availability == "stale":
                _delete_stale_document(source)
                continue
            if availability != "usable":
                continue
            name = _display_filename(meta.get("source", "unknown"), meta)
            if name not in seen:
                seen.add(name)
                names.append(name)
        return names

    for doc in get_all_documents():
        meta = doc.metadata or {}
        if meta.get("owner_role") == "guest":
            continue
        source = meta.get("source", "unknown")
        availability = _document_availability(source)
        if availability == "stale":
            _delete_stale_document(source)
            continue
        if availability != "usable":
            continue
        name = _display_filename(source, meta)
        if name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _visible_document_count(user: UserInDB) -> int:
    return len(_list_visible_document_names(user))


def _document_limit_for_user(user: UserInDB) -> int:
    if user.role == "guest":
        return settings.guest_max_indexed_documents
    return settings.max_indexed_documents


def _build_chunk_manifest_from_original_file(filename: str) -> list[str]:
    data = read_file(filename)
    if data is None:
        return []
    content = ingest_document(filename, data)
    docs = chunk_text(content, metadata={"source": filename})
    return _chunks_from_docs(docs)


def _load_document_chunks_for_display(filename: str) -> list[str]:
    """Read document chunks without letting vector-store preview failures become 500s."""
    try:
        chunks = get_document_chunks(filename)
    except Exception as exc:
        log.warning("document_chunks_vector_read_failed", filename=filename, error_type=type(exc).__name__)
        chunks = []
    if chunks:
        return chunks

    try:
        chunks = read_chunk_manifest(filename) or []
    except Exception as exc:
        log.warning("document_chunks_manifest_read_failed", filename=filename, error_type=type(exc).__name__)
        chunks = []
    if chunks:
        return chunks

    try:
        chunks = _build_chunk_manifest_from_original_file(filename)
    except Exception as exc:
        log.warning("document_chunks_original_backfill_failed", filename=filename, error_type=type(exc).__name__)
        return []

    if chunks:
        try:
            save_chunk_manifest(filename, chunks)
        except Exception as exc:
            log.warning("chunk_manifest_backfill_failed", filename=filename, error_type=type(exc).__name__)
    return chunks


def _guest_upload_key(request: Request) -> str:
    """Rate-limit guests and unauthenticated callers by IP; exempt valid admin tokens.

    Each admin request gets a UUID key, giving it an isolated bucket that can
    never be exhausted — effectively unlimited (OWASP A04).
    Expired tokens (S-05) and revoked tokens (S-04) are NOT exempted.
    """
    import uuid
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from jose import jwt as _jwt
            payload = _jwt.decode(
                auth[7:],
                settings.secret_key,
                algorithms=[settings.algorithm],
                # expiry is now verified (verify_exp=False removed — S-05)
            )
            jti = payload.get("jti", "")
            if jti and is_token_revoked(jti):
                raise ValueError("revoked")
            if payload.get("role") == "admin":
                return f"admin-exempt-{uuid.uuid4()}"
        except Exception:
            pass
    return get_remote_address(request)


_upload_limiter = Limiter(key_func=_guest_upload_key)

# ── Known-good magic byte signatures ──────────────────────────────────────────
_MAGIC_BYTES: dict[str, bytes] = {
    "pdf":  b"%PDF",
    "xlsx": b"PK\x03\x04",    # OOXML is a ZIP archive
    "xls":  b"\xd0\xcf\x11\xe0",  # OLE2 compound document
}

# Executable file headers — always rejected regardless of claimed type
_EXEC_SIGNATURES = [
    b"MZ",        # Windows PE
    b"\x7fELF",   # Linux ELF
    b"\xfe\xed\xfa",  # macOS Mach-O
    b"\xca\xfe\xba\xbe",  # macOS fat binary
]


def _check_content_safety(filename: str, content: bytes) -> None:
    """Basic content safety check: magic bytes + executable/script detection.

    Not a full antivirus scan — call this in addition to extension validation
    for a defence-in-depth approach (OWASP A04).
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # Reject files with known executable headers regardless of extension
    for sig in _EXEC_SIGNATURES:
        if content[: len(sig)] == sig:
            raise ValueError("Executable content detected. Upload rejected.")

    # Validate magic bytes for types where we know the expected signature
    expected = _MAGIC_BYTES.get(ext)
    if expected and not content.startswith(expected):
        raise ValueError(f"File content does not match the declared .{ext} format.")

    # For text-based files: reject null bytes and embedded script markers
    if ext in ("txt", "csv"):
        if b"\x00" in content[:512]:
            raise ValueError("Binary content detected in a text file.")
        sample = content[:2048].lower()
        if b"<script" in sample or b"javascript:" in sample:
            raise ValueError("Potentially unsafe script content detected.")


class DocumentListResponse(BaseModel):
    documents: list[str]
    count: int


class UploadResponse(BaseModel):
    filename: str
    chunks_indexed: int
    message: str


class DeleteResponse(BaseModel):
    filename: str
    chunks_removed: int


class DocumentChunksResponse(BaseModel):
    filename: str
    chunks: list[str]
    total_chunks: int


class DocumentContentResponse(BaseModel):
    filename: str
    content: str
    word_count: int


class DocumentMetadataItem(BaseModel):
    filename: str
    chunk_count: int
    uploaded_at: str | None
    owner_username: str | None
    availability: Literal["usable", "stale", "unknown"]


class DocumentMetadataResponse(BaseModel):
    documents: list[DocumentMetadataItem]
    count: int


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
@_upload_limiter.limit(f"{settings.guest_upload_rate_limit_per_minute}/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    user: UserInDB = Depends(get_current_user),
):
    """Upload and index a document (PDF, TXT, CSV, Excel).

    Any authenticated user may upload. Guests are limited to 2 MB per file and
    {guest_upload_rate_limit_per_minute} uploads/minute per IP; admins are exempt
    from the upload rate limit. All content undergoes basic safety validation
    (magic bytes, executable detection, script injection) before indexing (OWASP A04).
    """
    safe_name = validate_filename(file.filename or "upload")
    source_key = _document_source_key(safe_name, user)

    # ── Early content guards (no vector-store I/O) ─────────────────────────────
    # Peek at the first few bytes to catch empty files and executable magic
    # bytes *before* any vector-store interaction. UploadFile.seek(0) rewinds
    # the SpooledTemporaryFile so the full read below sees all bytes.
    _peek_size = max(len(sig) for sig in _EXEC_SIGNATURES)
    peek = await file.read(_peek_size)
    await file.seek(0)

    if not peek:
        audit_event("document_upload", status="rejected", request=request, user=user,
                    error_category="validation_error", filename=safe_name)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File is empty.")

    for sig in _EXEC_SIGNATURES:
        if peek[:len(sig)] == sig:
            audit_event("document_upload", status="rejected", request=request, user=user,
                        error_category="validation_error", filename=safe_name)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Executable content detected. Upload rejected.",
            )

    # ── Vector-store checks: duplicate + document-count limit ──────────────────
    # Reject duplicate before doing any full I/O (OWASP A04 — resource limits).
    # Case-insensitive: check both the exact name and the lowercase variant to handle
    # OS filesystems that normalise case on upload.
    try:
        duplicate = (
            _candidate_is_upload_duplicate(source_key)
            or (source_key.lower() != source_key and _candidate_is_upload_duplicate(source_key.lower()))
        )
    except SafeAppError as exc:
        audit_event(
            "document_upload",
            status="failed",
            request=request,
            user=user,
            error_category=exc.category,
            filename=safe_name,
        )
        raise
    except Exception as exc:
        safe_error = safe_app_error_from_exception(exc, default="vector_store_error")
        audit_event(
            "document_upload",
            status="failed",
            request=request,
            user=user,
            error_category=safe_error.category,
            filename=safe_name,
        )
        raise safe_error from exc

    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A document named '{safe_name}' is already indexed. Delete it first to re-upload.",
        )

    try:
        current_count = _visible_document_count(user)
    except Exception as exc:
        safe_error = safe_app_error_from_exception(exc, default="retrieval_error")
        audit_event(
            "document_upload",
            status="failed",
            request=request,
            user=user,
            error_category=safe_error.category,
            filename=safe_name,
        )
        raise safe_error from exc
    limit = _document_limit_for_user(user)
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Document limit reached ({limit}). Delete an existing document before uploading another.",
        )

    # ── Full content read + remaining validation ────────────────────────────────
    content = await file.read()

    # Apply the stricter guest size limit; on Vercel, admin uploads are also capped at 4 MB
    # because the serverless function body limit is ~4.5 MB (OWASP A04 — resource limits).
    size_limit = (
        settings.guest_max_upload_size_bytes
        if user.role == "guest"
        else settings.effective_max_upload_size_bytes
    )
    size_limit_mb = (
        settings.guest_max_upload_size_mb
        if user.role == "guest"
        else settings.effective_max_upload_size_mb
    )
    if len(content) > size_limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {size_limit_mb} MB limit.",
        )

    # Enforce role-based file-type policy (OWASP A01): guests may only upload plain text.
    if user.role == "guest" and Path(safe_name).suffix.lower() != ".txt":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Guest accounts may only upload .txt files.",
        )

    # Empty guard is redundant after the peek check above but kept as a safety net
    # for any code path where peek could have been non-empty yet content is empty.
    if not content:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="File is empty.")

    try:
        audit_event("document_upload", status="started", request=request, user=user, filename=safe_name)
        _check_content_safety(safe_name, content)
        scan_upload(safe_name, content)         # ZIP bomb + ClamAV
        text = ingest_document(safe_name, content)
        scan_upload(safe_name, content, extracted_text=text)  # stored injection
        docs = chunk_text(text, metadata=_document_metadata(safe_name, source_key, user))
        manifest_chunks = _chunks_from_docs(docs)
        ids = add_documents(docs)
        try:
            save_file(source_key, content)
            save_chunk_manifest(source_key, manifest_chunks)
        except Exception as exc:
            _cleanup_document_storage(source_key)
            raise safe_app_error_from_exception(exc, default="storage_error") from exc
        invalidate_doc_cache()  # BM25 cache stale after new docs indexed (P1)
    except SafeAppError as exc:
        log.error(
            "upload_indexing_failed",
            filename=safe_name,
            error_category=exc.category,
            error_type=exc.cause_type,
            request_id=getattr(getattr(request, "state", None), "request_id", None),
        )
        audit_event(
            "document_upload",
            status="failed",
            request=request,
            user=user,
            error_category=exc.category,
            filename=safe_name,
        )
        raise
    except ValueError as exc:
        audit_event(
            "document_upload",
            status="rejected",
            request=request,
            user=user,
            error_category="validation_error",
            filename=safe_name,
        )
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception as exc:
        # Catches OpenAI API errors (AuthenticationError, RateLimitError, etc.) and I/O
        # failures that are not ValueError — prevents them from hitting the global 500 handler.
        safe_error = safe_app_error_from_exception(exc, default="internal_error")
        log.error(
            "upload_indexing_failed",
            filename=safe_name,
            error_category=safe_error.category,
            error_type=type(exc).__name__,
            request_id=getattr(getattr(request, "state", None), "request_id", None),
        )
        audit_event(
            "document_upload",
            status="failed",
            request=request,
            user=user,
            error_category=safe_error.category,
            filename=safe_name,
        )
        raise safe_error from exc

    audit_event("document_upload", status="completed", request=request, user=user, filename=safe_name, chunks_indexed=len(ids))
    return UploadResponse(filename=safe_name, chunks_indexed=len(ids), message="Document indexed successfully.")


@router.get("/", response_model=DocumentListResponse)
async def list_documents(request: Request, user: UserInDB = Depends(get_current_user)):
    """List all indexed document sources. Auth required."""
    try:
        sources = _list_visible_document_names(user)
    except Exception as exc:
        safe_error = safe_app_error_from_exception(exc, default="retrieval_error")
        audit_event("document_list", status="failed", request=request, user=user, error_category=safe_error.category)
        raise safe_error from exc
    return DocumentListResponse(documents=sources, count=len(sources))


@router.get("/metadata", response_model=DocumentMetadataResponse)
async def get_documents_metadata(user=Depends(require_full_access)):
    """Return enriched metadata for all admin documents. Admin-only."""
    seen: set[str] = set()
    items: list[DocumentMetadataItem] = []

    for doc in get_all_documents():
        meta = doc.metadata or {}
        if meta.get("owner_role") == "guest":
            continue
        source = meta.get("source", "unknown")
        if source in seen:
            continue
        seen.add(source)

        display_name = _display_filename(source, meta)
        availability = _document_availability(source)

        try:
            chunks = get_document_chunks(source)
            chunk_count = len(chunks)
        except Exception:
            chunk_count = 0

        items.append(DocumentMetadataItem(
            filename=display_name,
            chunk_count=chunk_count,
            uploaded_at=meta.get("uploaded_at"),
            owner_username=meta.get("owner_username"),
            availability=availability,
        ))

    return DocumentMetadataResponse(documents=items, count=len(items))


@router.get("/{filename}/chunks", response_model=DocumentChunksResponse)
async def get_chunks(filename: str, _user=Depends(get_current_user)):
    """Return all indexed text chunks for a document. Read-only; any authenticated user."""
    safe_name = validate_filename(filename)
    source_key = _document_source_key(safe_name, _user)
    chunks = _load_document_chunks_for_display(source_key)
    if not chunks:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{safe_name}' not found.")
    return DocumentChunksResponse(filename=safe_name, chunks=chunks, total_chunks=len(chunks))


@router.get("/{filename}/content", response_model=DocumentContentResponse)
async def get_document_content_endpoint(filename: str, _user=Depends(get_current_user)):
    """Return the full reconstructed document text with chunk overlap removed.

    Chunks are stitched in sequence order with the ~chunk_overlap duplicated
    prefix stripped from each subsequent chunk.  Read-only; any authenticated
    user may call this endpoint (OWASP A01 — same access as /chunks).
    """
    safe_name = validate_filename(filename)
    source_key = _document_source_key(safe_name, _user)
    chunks = _load_document_chunks_for_display(source_key)
    content = _stitch_chunks(chunks, settings.chunk_overlap)
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{safe_name}' not found.",
        )
    word_count = len(content.split()) if content.strip() else 0
    return DocumentContentResponse(filename=safe_name, content=content, word_count=word_count)


_MIME_TYPES: dict[str, str] = {
    "pdf":  "application/pdf",
    "txt":  "text/plain; charset=utf-8",
    "csv":  "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls":  "application/vnd.ms-excel",
}


@router.get("/{filename}/file")
async def get_document_file(filename: str, request: Request, _user=Depends(get_current_user)):
    """Serve the original uploaded file bytes with the correct MIME type.

    Only available for files uploaded after this endpoint was added.
    Falls back to 404 for documents indexed before file storage was introduced.
    Read-only; any authenticated user may call this endpoint (OWASP A01).
    """
    safe_name = validate_filename(filename)
    source_key = _document_source_key(safe_name, _user)
    try:
        data = read_file(source_key)
    except Exception as exc:
        safe_error = safe_app_error_from_exception(exc, default="storage_error")
        audit_event(
            "document_file_read",
            status="failed",
            request=request,
            user=_user,
            error_category=safe_error.category,
            filename=safe_name,
        )
        raise safe_error from exc
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Original file for '{safe_name}' not found. Re-upload the document to enable file preview.",
        )
    ext = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    media_type = _MIME_TYPES.get(ext, "application/octet-stream")
    return Response(content=data, media_type=media_type)


@router.delete("/{filename}", response_model=DeleteResponse)
async def remove_document(filename: str, request: Request, _user=Depends(require_full_access)):
    """Remove a document and all its chunks from the index. Admin required."""
    safe_name = validate_filename(filename)
    source_key = _document_source_key(safe_name, _user)

    # Check persistent storage before touching the vector store so that
    # obviously non-existent documents return 404 even when the vector store
    # is temporarily unavailable (e.g. Pinecone maintenance window).
    try:
        _has_file = read_file(source_key) is not None
    except Exception:
        _has_file = True   # can't confirm absence; let VS decide

    try:
        _has_manifest = bool(read_chunk_manifest(source_key))
    except Exception:
        _has_manifest = True  # can't confirm absence; let VS decide

    try:
        removed = delete_document(source_key)
    except Exception as exc:
        # If neither the file store nor the manifest has any trace of this
        # document, it definitively does not exist — return 404 instead of 503.
        if not _has_file and not _has_manifest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document '{safe_name}' not found.",
            ) from None
        safe_error = safe_app_error_from_exception(exc, default="vector_store_error")
        audit_event(
            "document_delete",
            status="failed",
            request=request,
            user=_user,
            error_category=safe_error.category,
            filename=safe_name,
        )
        raise safe_error from exc
    if removed == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document '{safe_name}' not found.")
    try:
        delete_file(source_key)
        delete_chunk_manifest(source_key)
    except Exception as exc:
        safe_error = safe_app_error_from_exception(exc, default="storage_error")
        audit_event(
            "document_delete",
            status="failed",
            request=request,
            user=_user,
            error_category=safe_error.category,
            filename=safe_name,
        )
        raise safe_error from exc
    invalidate_doc_cache()
    audit_event("document_delete", status="completed", request=request, user=_user, filename=safe_name, chunks_removed=removed)
    return DeleteResponse(filename=safe_name, chunks_removed=removed)

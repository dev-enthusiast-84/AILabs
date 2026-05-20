"""Original-file storage for uploaded documents.

Saves raw bytes alongside the vector-index so the document viewer can serve
the exact file the user uploaded rather than reconstructed chunk text.

Storage root: UPLOAD_DIR env var (default: backend/uploads/).
On Vercel this automatically uses /tmp/uploads because /var/task is read-only.
"""
import json
import os
import pathlib
from mimetypes import guess_type

from app.settings_store import (
    get_effective_blob_read_write_token,
    get_effective_file_store_type,
    get_effective_vector_store_type,
    sync_effective_blob_token_to_env,
)

_BLOB_PREFIX = "rag/files/"
_CHUNK_MANIFEST_BLOB_PREFIX = "rag/chunk-manifests/"


def _use_blob_store() -> bool:
    token = get_effective_blob_read_write_token()
    if token:
        sync_effective_blob_token_to_env()
    return bool(token) and (
        get_effective_file_store_type() == "blob"
        or get_effective_vector_store_type() == "blob"
        or bool(os.environ.get("VERCEL"))
    )


def _blob_path(filename: str) -> str:
    return f"{_BLOB_PREFIX}{filename}"


def _chunk_manifest_blob_path(filename: str) -> str:
    return f"{_CHUNK_MANIFEST_BLOB_PREFIX}{filename}.json"


def _upload_dir() -> pathlib.Path:
    if "UPLOAD_DIR" in os.environ:
        base = os.environ["UPLOAD_DIR"]
    elif os.environ.get("VERCEL"):
        base = "/tmp/uploads"
    else:
        base = str(pathlib.Path(__file__).parent.parent.parent / "uploads")
    d = pathlib.Path(base)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _chunk_manifest_dir() -> pathlib.Path:
    d = _upload_dir() / ".chunk-manifests"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _chunk_manifest_file(filename: str) -> pathlib.Path:
    return _chunk_manifest_dir() / f"{filename}.json"


def save_file(filename: str, data: bytes) -> None:
    if _use_blob_store():
        from vercel.blob import put

        content_type = guess_type(filename)[0] or "application/octet-stream"
        put(
            _blob_path(filename),
            data,
            access="private",
            content_type=content_type,
            overwrite=True,
        )
        return
    (_upload_dir() / filename).write_bytes(data)


def save_chunk_manifest(filename: str, chunks: list[str]) -> None:
    payload = json.dumps({"filename": filename, "chunks": chunks}, ensure_ascii=False).encode("utf-8")
    if _use_blob_store():
        from vercel.blob import put

        put(
            _chunk_manifest_blob_path(filename),
            payload,
            access="private",
            content_type="application/json; charset=utf-8",
            overwrite=True,
        )
        return
    _chunk_manifest_file(filename).write_bytes(payload)


def read_file(filename: str) -> bytes | None:
    if _use_blob_store():
        from vercel.blob import get

        result = get(_blob_path(filename), access="private")
        return result.content if result and result.status_code == 200 else None
    path = _upload_dir() / filename
    return path.read_bytes() if path.exists() else None


def read_chunk_manifest(filename: str) -> list[str] | None:
    if _use_blob_store():
        from vercel.blob import get

        result = get(_chunk_manifest_blob_path(filename), access="private")
        raw = result.content if result and result.status_code == 200 else None
    else:
        path = _chunk_manifest_file(filename)
        raw = path.read_bytes() if path.exists() else None
    if raw is None:
        return None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    chunks = parsed.get("chunks") if isinstance(parsed, dict) else parsed
    if not isinstance(chunks, list):
        return None
    return [chunk for chunk in chunks if isinstance(chunk, str) and chunk.strip()]


def delete_file(filename: str) -> None:
    if _use_blob_store():
        from vercel.blob import delete

        delete(_blob_path(filename))
        return
    path = _upload_dir() / filename
    if path.exists():
        path.unlink()


def delete_chunk_manifest(filename: str) -> None:
    if _use_blob_store():
        from vercel.blob import delete

        delete(_chunk_manifest_blob_path(filename))
        return
    path = _chunk_manifest_file(filename)
    if path.exists():
        path.unlink()

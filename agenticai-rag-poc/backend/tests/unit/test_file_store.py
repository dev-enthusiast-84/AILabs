"""Unit tests for app.rag.file_store — original-file storage."""
import pytest
import app.rag.file_store as fs


def _clear_settings_cache():
    from app.config import get_settings

    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _tmp_upload_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    _clear_settings_cache()
    yield
    _clear_settings_cache()


def test_save_and_read_roundtrip():
    fs.save_file("report.txt", b"hello world")
    assert fs.read_file("report.txt") == b"hello world"


def test_read_nonexistent_returns_none():
    assert fs.read_file("ghost.txt") is None


def test_delete_removes_file():
    fs.save_file("delete_me.txt", b"data")
    fs.delete_file("delete_me.txt")
    assert fs.read_file("delete_me.txt") is None


def test_delete_nonexistent_is_noop():
    fs.delete_file("never_existed.txt")  # must not raise


def test_overwrite_replaces_content():
    fs.save_file("doc.pdf", b"v1 content")
    fs.save_file("doc.pdf", b"v2 content")
    assert fs.read_file("doc.pdf") == b"v2 content"


def test_chunk_manifest_roundtrip():
    fs.save_chunk_manifest("report.txt", ["chunk one", "chunk two"])
    assert fs.read_chunk_manifest("report.txt") == ["chunk one", "chunk two"]


def test_chunk_manifest_delete_is_noop_for_missing_file():
    fs.delete_chunk_manifest("ghost.txt")
    assert fs.read_chunk_manifest("ghost.txt") is None


def test_chunk_manifest_delete_removes_manifest():
    fs.save_chunk_manifest("delete_me.txt", ["chunk"])
    fs.delete_chunk_manifest("delete_me.txt")
    assert fs.read_chunk_manifest("delete_me.txt") is None


def test_upload_dir_created_when_missing(tmp_path, monkeypatch):
    nested = tmp_path / "a" / "b" / "uploads"
    monkeypatch.setenv("UPLOAD_DIR", str(nested))
    fs.save_file("test.txt", b"data")
    assert (nested / "test.txt").exists()


def test_vercel_defaults_to_tmp_uploads(monkeypatch):
    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    _clear_settings_cache()
    assert fs._upload_dir() == fs.pathlib.Path("/tmp/uploads")


def test_blob_file_store_roundtrip(monkeypatch):
    import vercel.blob as blob

    stored: dict[str, bytes] = {}
    deleted: list[str] = []

    def fake_put(path, body, **_kwargs):
        stored[path] = body

    def fake_get(path, **_kwargs):
        if path not in stored:
            return None
        return type("Result", (), {"content": stored[path], "status_code": 200})()

    def fake_delete(path, **_kwargs):
        deleted.append(path)
        stored.pop(path, None)

    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_test")
    monkeypatch.setenv("FILE_STORE_TYPE", "blob")
    _clear_settings_cache()
    monkeypatch.setattr(blob, "put", fake_put)
    monkeypatch.setattr(blob, "get", fake_get)
    monkeypatch.setattr(blob, "delete", fake_delete)

    fs.save_file("doc.txt", b"hello")
    assert fs.read_file("doc.txt") == b"hello"
    fs.delete_file("doc.txt")
    assert deleted == ["rag/files/doc.txt"]
    assert fs.read_file("doc.txt") is None


def test_blob_chunk_manifest_roundtrip(monkeypatch):
    import vercel.blob as blob

    stored: dict[str, bytes] = {}
    deleted: list[str] = []

    def fake_put(path, body, **_kwargs):
        stored[path] = body

    def fake_get(path, **_kwargs):
        if path not in stored:
            return None
        return type("Result", (), {"content": stored[path], "status_code": 200})()

    def fake_delete(path, **_kwargs):
        deleted.append(path)
        stored.pop(path, None)

    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_test")
    monkeypatch.setenv("FILE_STORE_TYPE", "blob")
    _clear_settings_cache()
    monkeypatch.setattr(blob, "put", fake_put)
    monkeypatch.setattr(blob, "get", fake_get)
    monkeypatch.setattr(blob, "delete", fake_delete)

    fs.save_chunk_manifest("doc.txt", ["hello", "again"])
    assert fs.read_chunk_manifest("doc.txt") == ["hello", "again"]
    fs.delete_chunk_manifest("doc.txt")
    assert deleted == ["rag/chunk-manifests/doc.txt.json"]
    assert fs.read_chunk_manifest("doc.txt") is None


def test_blob_read_file_returns_none_on_blob_not_found(monkeypatch):
    """BlobNotFoundError from vercel.blob.get() must return None, not propagate as a storage error.

    Regression test: previously BlobNotFoundError was caught by _document_availability as a
    generic Exception → returned "unknown" → upload endpoint raised 503 ("Document retrieval
    is unavailable") instead of treating the missing file as stale and allowing re-upload.
    """
    import vercel.blob as blob

    def fake_get(path, **_kwargs):
        raise blob.BlobNotFoundError()

    def fake_put(path, body, **_kwargs):
        pass

    monkeypatch.delenv("UPLOAD_DIR", raising=False)
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_test")
    monkeypatch.setenv("FILE_STORE_TYPE", "blob")
    _clear_settings_cache()
    monkeypatch.setattr(blob, "put", fake_put)
    monkeypatch.setattr(blob, "get", fake_get)

    assert fs.read_file("missing.pdf") is None


def test_binary_content_preserved():
    raw = bytes(range(256))
    fs.save_file("binary.bin", raw)
    assert fs.read_file("binary.bin") == raw


def test_read_chunk_manifest_returns_none_on_decode_error(tmp_path, monkeypatch):
    """UnicodeDecodeError in read_chunk_manifest returns None (lines 123-124)."""
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.config import get_settings
    get_settings.cache_clear()

    import json
    # Write a manifest path directly with invalid UTF-8 bytes
    manifests_dir = tmp_path / ".chunk_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / "bad.txt.json"
    manifest_path.write_bytes(b"\xff\xfe")  # invalid UTF-8

    # Patch _chunk_manifest_file to return our bad path
    with pytest.MonkeyPatch().context() as m:
        m.setattr(fs, "_chunk_manifest_file", lambda name: manifest_path)
        result = fs.read_chunk_manifest("bad.txt")

    assert result is None
    get_settings.cache_clear()


def test_read_chunk_manifest_returns_none_on_json_error(tmp_path, monkeypatch):
    """JSONDecodeError in read_chunk_manifest returns None (lines 123-124)."""
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.config import get_settings
    get_settings.cache_clear()

    manifests_dir = tmp_path / ".chunk_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / "corrupt.txt.json"
    manifest_path.write_bytes(b"{ not valid json !!!}")

    with pytest.MonkeyPatch().context() as m:
        m.setattr(fs, "_chunk_manifest_file", lambda name: manifest_path)
        result = fs.read_chunk_manifest("corrupt.txt")

    assert result is None
    get_settings.cache_clear()


def test_read_chunk_manifest_returns_none_when_chunks_not_list(tmp_path, monkeypatch):
    """Parsed JSON that is not a list (or dict with chunks=non-list) returns None (line 127)."""
    import json
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path))
    from app.config import get_settings
    get_settings.cache_clear()

    manifests_dir = tmp_path / ".chunk_manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifests_dir / "nonlist.txt.json"
    # A dict where 'chunks' key holds a non-list value
    manifest_path.write_bytes(json.dumps({"chunks": "not-a-list"}).encode())

    with pytest.MonkeyPatch().context() as m:
        m.setattr(fs, "_chunk_manifest_file", lambda name: manifest_path)
        result = fs.read_chunk_manifest("nonlist.txt")

    assert result is None
    get_settings.cache_clear()


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


def test_binary_content_preserved():
    raw = bytes(range(256))
    fs.save_file("binary.bin", raw)
    assert fs.read_file("binary.bin") == raw

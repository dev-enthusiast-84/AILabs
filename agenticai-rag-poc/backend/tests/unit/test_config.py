"""Unit tests for Settings properties in app/config.py."""
import pytest
from app.config import Settings


def _s(**kwargs) -> Settings:
    """Create a Settings instance with test defaults; kwargs override."""
    return Settings(admin_password="x", **kwargs)


class TestAllowedOriginsList:
    def test_splits_comma_separated_origins(self):
        s = _s(allowed_origins="http://localhost:3000,http://localhost:5173")
        assert s.allowed_origins_list == ["http://localhost:3000", "http://localhost:5173"]

    def test_strips_whitespace_around_each_origin(self):
        s = _s(allowed_origins=" http://localhost:3000 , http://localhost:5173 ")
        assert s.allowed_origins_list == ["http://localhost:3000", "http://localhost:5173"]

    def test_single_origin_returns_one_element_list(self):
        s = _s(allowed_origins="https://example.com")
        assert s.allowed_origins_list == ["https://example.com"]

    def test_empty_string_returns_empty_list(self):
        s = _s(allowed_origins="")
        assert s.allowed_origins_list == []

    def test_ignores_blank_entries_from_trailing_comma(self):
        s = _s(allowed_origins="http://localhost:3000,")
        assert s.allowed_origins_list == ["http://localhost:3000"]


class TestMaxUploadSizeBytes:
    def test_converts_mb_to_bytes(self):
        s = _s(max_upload_size_mb=20)
        assert s.max_upload_size_bytes == 20 * 1024 * 1024

    def test_zero_mb_gives_zero_bytes(self):
        s = _s(max_upload_size_mb=0)
        assert s.max_upload_size_bytes == 0

    def test_one_mb_gives_correct_bytes(self):
        s = _s(max_upload_size_mb=1)
        assert s.max_upload_size_bytes == 1_048_576


class TestEffectiveMaxUploadSize:
    def test_outside_vercel_returns_full_limit(self, monkeypatch):
        monkeypatch.delenv("VERCEL", raising=False)
        s = _s(max_upload_size_mb=20)
        assert s.effective_max_upload_size_mb == 20
        assert s.effective_max_upload_size_bytes == 20 * 1024 * 1024

    def test_on_vercel_caps_at_4mb(self, monkeypatch):
        monkeypatch.setenv("VERCEL", "1")
        s = _s(max_upload_size_mb=20)
        assert s.effective_max_upload_size_mb == 4
        assert s.effective_max_upload_size_bytes == 4 * 1024 * 1024

    def test_on_vercel_does_not_increase_lower_limit(self, monkeypatch):
        monkeypatch.setenv("VERCEL", "1")
        s = _s(max_upload_size_mb=2)
        assert s.effective_max_upload_size_mb == 2

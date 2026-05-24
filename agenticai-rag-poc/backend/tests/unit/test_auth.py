import os

import pytest
from app.auth.utils import (
    hash_password,
    verify_password,
    authenticate_user,
    create_access_token,
    decode_token,
    is_token_revoked,
    revoke_token,
)

_ADMIN_PWD = os.environ["ADMIN_PASSWORD"]


def test_hash_and_verify_password():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed) is True


def test_verify_wrong_password():
    hashed = hash_password("secret123")
    assert verify_password("wrongpass", hashed) is False


def test_authenticate_user_success():
    user = authenticate_user("admin", _ADMIN_PWD)
    assert user is not None
    assert user.username == "admin"


def test_authenticate_user_wrong_password():
    assert authenticate_user("admin", "wrongpassword") is None


def test_authenticate_user_unknown_user():
    assert authenticate_user("nobody", _ADMIN_PWD) is None


def test_create_and_decode_token():
    token = create_access_token({"sub": "admin"})
    data = decode_token(token)
    assert data.username == "admin"


def test_decode_invalid_token():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        decode_token("totally.invalid.token")
    assert exc_info.value.status_code == 401


def test_build_users_raises_when_password_unset():
    from unittest.mock import patch, MagicMock
    from app.auth.utils import _build_users
    mock_s = MagicMock()
    mock_s.admin_password = ""
    with patch("app.auth.utils._current_settings", return_value=mock_s):
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            _build_users()


def test_decode_token_missing_sub_raises():
    """A validly signed JWT without a 'sub' claim must raise 401."""
    from fastapi import HTTPException
    from jose import jwt
    from app.config import get_settings
    s = get_settings()
    token = jwt.encode({"user": "admin"}, s.secret_key, algorithm=s.algorithm)
    with pytest.raises(HTTPException) as exc_info:
        decode_token(token)
    assert exc_info.value.status_code == 401


# ── JTI revocation (S5) ───────────────────────────────────────────────────────

def test_is_token_revoked_returns_false_for_unknown_jti():
    assert is_token_revoked("nonexistent-jti-99999") is False


def test_revoke_token_blocks_subsequent_check():
    import uuid
    jti = f"test-revoke-{uuid.uuid4()}"
    assert is_token_revoked(jti) is False
    revoke_token(jti)
    assert is_token_revoked(jti) is True


def test_jti_blocklist_evicts_at_capacity():
    """When blocklist is full (with non-expired entries), revoke_token evicts the oldest (LRU)."""
    import time
    import app.auth.utils as _utils
    saved = dict(_utils._revoked_jtis)
    far_future = time.time() + 86400  # non-expired
    try:
        _utils._revoked_jtis.clear()
        # Fill to exactly capacity with non-expired entries
        for i in range(_utils._MAX_REVOKED):
            _utils._revoked_jtis[f"fill-{i}"] = far_future
        assert len(_utils._revoked_jtis) == _utils._MAX_REVOKED
        # Adding one more evicts the oldest ("fill-0") and adds the new JTI
        revoke_token("lru-trigger", exp=far_future)
        assert len(_utils._revoked_jtis) == _utils._MAX_REVOKED  # still at capacity
        assert "lru-trigger" in _utils._revoked_jtis
        assert "fill-0" not in _utils._revoked_jtis  # oldest evicted
        assert "fill-1" in _utils._revoked_jtis       # second-oldest kept
    finally:
        _utils._revoked_jtis.clear()
        _utils._revoked_jtis.update(saved)


def test_decode_token_rejects_revoked_jti():
    """decode_token must raise HTTP 401 when the token's JTI is in the blocklist (S-04)."""
    from fastapi import HTTPException
    from jose import jwt as _jwt
    from app.config import get_settings as _gs
    import app.auth.utils as _utils
    token = create_access_token({"sub": "admin"})
    s = _gs()
    payload = _jwt.decode(token, s.secret_key, algorithms=[s.algorithm])
    jti = payload["jti"]
    revoke_token(jti)
    try:
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token)
        assert exc_info.value.status_code == 401
    finally:
        _utils._revoked_jtis.pop(jti, None)


def test_purge_expired_jtis_removes_only_expired():
    """_purge_expired_jtis() removes entries past their expiry but keeps future ones (line 41)."""
    import time
    import app.auth.utils as _utils

    saved = dict(_utils._revoked_jtis)
    try:
        _utils._revoked_jtis.clear()
        past = time.time() - 1
        future = time.time() + 3600
        _utils._revoked_jtis["expired-jti"] = past
        _utils._revoked_jtis["fresh-jti"] = future
        _utils._purge_expired_jtis()
        assert "expired-jti" not in _utils._revoked_jtis
        assert "fresh-jti" in _utils._revoked_jtis
    finally:
        _utils._revoked_jtis.clear()
        _utils._revoked_jtis.update(saved)


def test_revoke_token_early_return_for_duplicate():
    """revoke_token() returns early without re-adding an already-revoked JTI (line 48)."""
    import time
    import uuid
    import app.auth.utils as _utils

    jti = f"dup-{uuid.uuid4()}"
    future = time.time() + 3600
    saved = dict(_utils._revoked_jtis)
    try:
        _utils._revoked_jtis[jti] = future
        size_before = len(_utils._revoked_jtis)
        revoke_token(jti, exp=future)  # second call — must be a no-op
        assert len(_utils._revoked_jtis) == size_before
        assert _utils._revoked_jtis[jti] == future  # expiry not modified
    finally:
        _utils._revoked_jtis.clear()
        _utils._revoked_jtis.update(saved)


def test_admin_password_fingerprint_empty_when_no_password():
    """_admin_password_fingerprint returns '' when admin_password is falsy (line 85)."""
    from unittest.mock import patch, MagicMock
    import app.auth.utils as _utils

    mock_settings = MagicMock()
    mock_settings.admin_password = ""
    with patch.object(_utils, "_current_settings", return_value=mock_settings):
        result = _utils._admin_password_fingerprint(mock_settings)
    assert result == ""

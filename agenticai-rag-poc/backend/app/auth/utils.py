import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
import hmac
import hashlib

import bcrypt
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import Settings, get_settings
from app.auth.models import TokenData, UserInDB

settings = get_settings()
bearer_scheme = HTTPBearer()
log = structlog.get_logger()
_admin_lock = threading.Lock()
_admin_cache: dict[str, str | UserInDB] = {}

# ── JTI revocation blocklist (S5) ────────────────────────────────────────────
# Logout invalidates a token by adding its JTI here. Uses an OrderedDict as a
# bounded LRU cache: when full, the OLDEST entry is evicted (not all entries),
# preserving recently-revoked tokens. Clears all entries would allow an attacker
# to flood the endpoint with throwaway tokens and reactivate logged-out sessions.
# Values store the token's expiry epoch so naturally-expired tokens can be purged
# before the LRU capacity limit is reached.
_revoked_jtis: OrderedDict[str, float] = OrderedDict()
_revoked_lock = threading.Lock()
_MAX_REVOKED = 10_000


def _purge_expired_jtis() -> None:
    """Remove JTIs whose tokens have already naturally expired (call inside _revoked_lock)."""
    now = time.time()
    expired = [j for j, exp in _revoked_jtis.items() if exp < now]
    for j in expired:
        del _revoked_jtis[j]


def revoke_token(jti: str, exp: float | None = None) -> None:
    """Add a JTI to the revocation blocklist; evicts expired entries first, then LRU when full."""
    with _revoked_lock:
        if jti in _revoked_jtis:
            return
        _purge_expired_jtis()
        if len(_revoked_jtis) >= _MAX_REVOKED:
            _revoked_jtis.popitem(last=False)  # evict oldest, not all
            log.warning("jti_blocklist_evicted_oldest", reason="capacity_limit")
        _revoked_jtis[jti] = exp if exp is not None else time.time() + 86400


def is_token_revoked(jti: str) -> bool:
    with _revoked_lock:
        return jti in _revoked_jtis

# Sentinel guest user — no password, read-only role, never stored in auth store
_GUEST_USER = UserInDB(username="guest", hashed_password="", disabled=False, role="guest")


# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── In-memory user store — swap for a DB in production ───────────────────────

def _current_settings() -> Settings:
    # Do not use get_settings() here. Admin password rotation updates env/.env,
    # and auth must stop accepting the previous password without a process restart.
    return Settings()


def _admin_password_fingerprint(s: Settings | None = None) -> str:
    s = s or _current_settings()
    if not s.admin_password:
        return ""
    key = (s.secret_key or "admin-password-version").encode()
    msg = f"{s.admin_username}:{s.admin_password}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _current_admin_user() -> UserInDB:
    s = _current_settings()
    if not s.admin_password:
        raise RuntimeError(
            "ADMIN_PASSWORD is not set. "
            "Run `bash setup.sh` to generate credentials, or add "
            "ADMIN_PASSWORD=<your-password> to backend/.env manually."
        )
    fingerprint = _admin_password_fingerprint(s)
    with _admin_lock:
        if (
            _admin_cache.get("username") == s.admin_username
            and _admin_cache.get("fingerprint") == fingerprint
            and isinstance(_admin_cache.get("user"), UserInDB)
        ):
            return _admin_cache["user"]  # type: ignore[return-value]
        user = UserInDB(
            username=s.admin_username,
            hashed_password=hash_password(s.admin_password),
            role="admin",
        )
        _admin_cache.clear()
        _admin_cache.update({
            "username": s.admin_username,
            "fingerprint": fingerprint,
            "user": user,
        })
        return user


def _build_users() -> dict[str, UserInDB]:
    users: dict[str, UserInDB] = {
        _current_admin_user().username: _current_admin_user()
    }
    users["guest"] = _GUEST_USER
    return users

_USERS: dict[str, UserInDB] = _build_users()


def get_user(username: str) -> UserInDB | None:
    admin = _current_admin_user()
    if username == admin.username:
        return admin
    return _USERS.get(username)


def authenticate_user(username: str, password: str) -> UserInDB | None:
    user = get_user(username)
    if not user or user.disabled or user.role == "guest":
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(data: dict, expire_minutes: int | None = None) -> str:
    payload = data.copy()
    s = _current_settings()
    minutes = expire_minutes if expire_minutes is not None else s.access_token_expire_minutes
    now = datetime.now(timezone.utc)
    payload["exp"] = now + timedelta(minutes=minutes)
    payload["iat"] = now
    payload["jti"] = str(uuid.uuid4())
    if payload.get("role") == "admin":
        payload["pwdv"] = _admin_password_fingerprint(s)
    return jwt.encode(payload, s.secret_key, algorithm=s.algorithm)


def _decode_token_payload(token: str) -> dict:
    """Decode a JWT and verify it isn't revoked. Raises HTTPException 401 on any failure."""
    _exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    s = _current_settings()
    try:
        payload = jwt.decode(token, s.secret_key, algorithms=[s.algorithm])
    except JWTError:
        raise _exc
    jti = payload.get("jti", "")
    if jti and is_token_revoked(jti):
        raise _exc
    if payload.get("role") == "admin" and payload.get("pwdv") != _admin_password_fingerprint(s):
        raise _exc
    return payload


def decode_token(token: str) -> TokenData:
    payload = _decode_token_payload(token)
    username: str | None = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenData(username=username)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = _decode_token_payload(credentials.credentials)
    username: str | None = payload.get("sub")
    if username is None:
        raise credentials_exception
    user = get_user(username)
    if user is None or user.disabled:
        raise credentials_exception
    if user.role == "guest":
        session_id = payload.get("jti")
        from app.runtime.settings_store import set_runtime_scope
        set_runtime_scope(user.role, session_id)
        return user.model_copy(update={"session_id": session_id})
    from app.runtime.settings_store import set_runtime_scope
    set_runtime_scope(user.role, None)
    return user


def require_full_access(user: UserInDB = Depends(get_current_user)) -> UserInDB:
    """Dependency that rejects guest-role tokens. Apply to write/admin endpoints."""
    if user.role == "guest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires a full account. Please sign in.",
        )
    return user

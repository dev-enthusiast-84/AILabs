from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth.models import LoginRequest, TokenResponse
from app.auth.utils import authenticate_user, bearer_scheme, create_access_token, get_current_user, revoke_token, _decode_token_payload
from app.config import get_settings

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
settings = get_settings()


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    """Authenticate and return JWT. Rate-limited to prevent brute-force (OWASP A07)."""
    user = authenticate_user(body.username, body.password)
    if not user:
        # Uniform error — don't leak whether username or password was wrong
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user.username, "role": user.role})
    return TokenResponse(access_token=token)


@router.post("/guest", response_model=TokenResponse)
@limiter.limit("10/minute")
async def guest_login(request: Request):
    """
    Issue a short-lived guest JWT (no credentials required).

    Guest tokens expire after GUEST_TOKEN_EXPIRE_MINUTES (default 15 min).
    Guests may use the chat interface and list indexed documents.
    Upload, delete, and settings endpoints return HTTP 403 for guest tokens.
    """
    token = create_access_token(
        {"sub": "guest", "role": "guest"},
        expire_minutes=settings.guest_token_expire_minutes,
    )
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout(
    credentials: "HTTPAuthorizationCredentials" = Depends(bearer_scheme),
    _user=Depends(get_current_user),
):
    """Invalidate the current JWT by adding its JTI to the server-side blocklist.

    Subsequent requests with the same token will receive HTTP 401 (OWASP A07).
    The blocklist is in-memory and does not survive server restarts.
    """
    payload = _decode_token_payload(credentials.credentials)
    jti = payload.get("jti")
    if jti:
        revoke_token(jti)
    return {"message": "Logged out successfully"}


@router.get("/me")
async def me(current_user=Depends(get_current_user)):
    return {"username": current_user.username, "role": current_user.role}


# dev-credentials endpoint removed (S-10): password is printed in the terminal
# startup banner; exposing it over the network (even localhost-only) allows any
# page running at localhost:3000 to harvest admin credentials without CORS restriction.

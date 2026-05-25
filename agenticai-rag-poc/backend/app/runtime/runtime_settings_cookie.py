"""Encrypted per-browser Settings UI persistence.

Production does not read billable provider credentials from deployment env vars.
This cookie keeps values entered through the Settings UI available to stateless
serverless requests without exposing them to frontend JavaScript.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from typing import Any

import structlog
from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request, Response

from app.auth.models import UserInDB
from app.config import get_settings
from app.runtime.settings_store import persist_infra_credentials, set_request_runtime_settings

COOKIE_NAME = "rag_ui_settings"
HEADER_NAME = "X-Runtime-Settings"
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 4

_log = structlog.get_logger(__name__)

_ALLOWED_KEYS = {
    # Provider credentials and per-node models
    "api_key",
    "model",
    "embedding_model",
    "planner_model",
    "generator_model",
    "validator_model",
    "max_completion_tokens",
    "langchain_api_key",
    "pinecone_api_key",
    "pinecone_index_name",
    "pinecone_namespace",
    "pinecone_cloud",
    "pinecone_region",
    "blob_read_write_token",
    # Pipeline settings — included so Vercel serverless instances honour
    # Settings UI changes across cold starts without requiring a restart.
    "reranker_type",
    "reranker_judge_model",
    "relevance_grader_enabled",
    "retriever_k",
    "retriever_use_mmr",
    "retriever_fetch_k",
    "max_context_chunks",
    "retriever_hybrid_bm25",
    "similarity_score_threshold",
    # Notification settings — persisted so ntfy topic set via UI survives cold starts.
    "notification_enabled",
    "notification_email",
    "notification_ntfy_topic",
}


def _fernet() -> Fernet:
    secret = get_settings().secret_key.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def _same_site() -> str:
    return "none" if get_settings().app_env == "production" else "lax"


def _secure_cookie() -> bool:
    return get_settings().app_env == "production"


def _build_token(*, user: UserInDB, settings_values: dict[str, Any]) -> str:
    payload = {
        "sub": user.username,
        "role": user.role,
        "session_id": user.session_id or "",
        "iat": int(time.time()),
        "settings": {
            key: value
            for key, value in settings_values.items()
            if key in _ALLOWED_KEYS
            and value not in (None, "")
            and not (key == "reranker_type" and value == "none")
        },
    }
    return _fernet().encrypt(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("utf-8")


def set_runtime_settings_cookie(
    response: Response,
    *,
    user: UserInDB,
    settings_values: dict[str, Any],
) -> None:
    token = _build_token(user=user, settings_values=settings_values)
    # Expose only the Fernet ciphertext; raw provider keys never leave the
    # server in plaintext responses, logs, or JavaScript-readable objects.
    response.headers[HEADER_NAME] = token
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=_secure_cookie(),
        samesite=_same_site(),
        path="/",
    )


def clear_runtime_settings_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        httponly=True,
        secure=_secure_cookie(),
        samesite=_same_site(),
        path="/",
    )


def restore_runtime_settings_from_token(raw: str | None, user: UserInDB) -> bool:
    if not raw:
        return False

    try:
        payload = json.loads(_fernet().decrypt(raw.encode("utf-8"), ttl=COOKIE_MAX_AGE_SECONDS))
    except (InvalidToken, ValueError, TypeError) as exc:
        _log.warning("runtime_settings_token_invalid", reason=type(exc).__name__)
        return False

    if payload.get("sub") != user.username or payload.get("role") != user.role:
        return False
    if payload.get("session_id") != (user.session_id or ""):
        return False

    settings_payload = payload.get("settings")
    if not isinstance(settings_payload, dict):
        return False

    restored = {
        key: value
        for key, value in settings_payload.items()
        if key in _ALLOWED_KEYS and value not in (None, "")
    }
    set_request_runtime_settings(restored)

    # Promote admin infra credentials (Pinecone key, blob token) to module-level
    # globals so subsequent requests on the same Vercel function instance —
    # including guest requests that have no settings cookie — can reach the
    # vector store and file store without needing the admin's cookie themselves.
    if payload.get("role") == "admin":
        persist_infra_credentials(restored)

    # Clear the vector store singleton whenever durable storage credentials are
    # restored from the cookie.  On a cold Vercel start the cache may already
    # hold an InMemoryVectorStore (built before the cookie was read); clearing it
    # here costs one store rebuild but ensures the correct durable backend is used.
    # Both BlobVectorStore and PineconeStore are stateless on init (all data lives
    # in external storage), so no indexed documents are lost by this reset.
    if restored.get("blob_read_write_token") or restored.get("pinecone_api_key"):
        try:
            import app.rag.vector_store as _vs_mod
            _vs_mod.get_vector_store.cache_clear()
            _vs_mod.invalidate_doc_cache()
        except Exception:
            pass

    return True


def restore_runtime_settings_from_cookie(request: Request, user: UserInDB) -> None:
    raw = request.headers.get(HEADER_NAME) or request.cookies.get(COOKIE_NAME)
    restore_runtime_settings_from_token(raw, user)

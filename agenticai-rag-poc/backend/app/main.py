import time
import uuid
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import Settings, get_settings
from app.auth.router import router as auth_router
from app.api.documents import router as documents_router
from app.api.guardrails import router as guardrails_router
from app.api.notifications import router as notifications_router
from app.api.query import router as query_router
from app.api.ragas import router as ragas_router
from app.api.settings import router as settings_router
from app.api.troubleshoot import router as troubleshoot_router
from app.api.voice_export import router as voice_export_router
from app.core.errors import SafeAppError, safe_error_response
from app.runtime.settings_store import (
    account_env_fallback_allowed,
    get_effective_api_key,
    get_effective_blob_read_write_token,
    get_effective_file_store_type,
    get_effective_pinecone_api_key,
    get_effective_vector_store_type,
    is_runtime_key_set,
)

settings = get_settings()
log = structlog.get_logger()
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def _print_startup_banner(s: Settings) -> None:
    """Print admin credentials to stdout at startup (development only).

    Suppressed in test and production environments:
    - test: keeps test output clean
    - production/vercel: prevents plaintext credentials appearing in
      cloud log aggregators visible to anyone with dashboard access (OWASP A09)
    """
    if s.app_env != "development":
        return
    sep = "=" * 55
    div = "-" * 55
    print(f"\n{sep}")
    print("  Agentic RAG — backend ready")
    print(sep)
    print(f"  API Docs  :  http://localhost:8000/api/docs")
    print(f"  Health    :  http://localhost:8000/api/health")
    print(div)
    print("  Admin login credentials")
    print(f"    Username :  {s.admin_username}")
    print(f"    Password :  {s.admin_password}")
    print(div)
    print("  Password lives in backend/.env (ADMIN_PASSWORD).")
    print("  Keep that file private — never commit it.")
    print(f"{sep}\n")


_INSECURE_SECRET = "change-me-to-a-long-random-secret-at-least-32-chars"
_WEAK_SECRETS = {"", _INSECURE_SECRET}


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    if settings.secret_key in _WEAK_SECRETS:
        msg = (
            "SECRET_KEY is not set or is the insecure default. "
            "Generate a strong key with `openssl rand -hex 32` and set it as "
            "SECRET_KEY in your environment or backend/.env file."
        )
        if settings.app_env != "development":
            raise RuntimeError(msg)
        log.warning("secret_key_weak", msg=msg)
    # LangSmith tracing — allowed from env only outside production. Production
    # users must opt in through Settings UI to avoid billing a deployer account.
    if (
        settings.app_env != "production"
        and settings.langchain_tracing_v2
        and settings.langchain_api_key
    ):
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        # OWASP A02: do not write the API key to os.environ at startup — it is
        # set per-request via apply_runtime_settings() and read by LangChain clients
        # directly from settings_store.get_effective_langchain_api_key().
        log.info("langsmith_tracing_enabled", project=settings.langchain_project)
    _print_startup_banner(settings)
    yield


limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_per_minute}/minute"])

app = FastAPI(
    title="Agentic RAG API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if settings.app_env == "development" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.app_env == "development" else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(SafeAppError)
async def safe_app_error_handler(request: Request, exc: SafeAppError):
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    log.warning(
        "safe_app_error",
        error_category=exc.category,
        error_type=exc.cause_type,
        path=request.url.path,
        request_id=request_id,
        **exc.metadata,
    )
    return safe_error_response(request, exc)

# CORS — OWASP A05
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Runtime-Settings"],
    expose_headers=["X-App-Session-Compatibility", "X-Request-ID", "X-Runtime-Settings"],
)


def _request_id_from_headers(request: Request) -> str:
    request_id = request.headers.get("X-Request-ID", "").strip()
    if request_id and _REQUEST_ID_RE.fullmatch(request_id):
        return request_id
    return str(uuid.uuid4())


def _apply_common_headers(response, request_id: str) -> None:
    # OWASP security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; object-src 'none'"
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-App-Session-Compatibility"] = settings.session_compatibility_version
    # HSTS — only in production; local and test environments use plain HTTP (S4)
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Remove server fingerprinting (MutableHeaders uses del, not pop)
    if "server" in response.headers:
        del response.headers["server"]


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    request_id = _request_id_from_headers(request)
    request.state.request_id = request_id
    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:
        elapsed = time.perf_counter() - start
        log.error(
            "unhandled_exception",
            error_type=type(exc).__name__,
            path=request.url.path,
            request_id=request_id,
        )
        response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal error occurred.",
                "request_id": request_id,
            },
        )
        _apply_common_headers(response, request_id)
        log.info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            ms=round(elapsed * 1000),
            request_id=request_id,
        )
        return response

    elapsed = time.perf_counter() - start

    _apply_common_headers(response, request_id)

    log.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        ms=round(elapsed * 1000),
        request_id=request_id,
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    log.error(
        "unhandled_exception",
        error_type=type(exc).__name__,
        path=request.url.path,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal error occurred.",
            "request_id": request_id,
        },
    )


app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(documents_router, prefix="/api/documents", tags=["documents"])
app.include_router(guardrails_router, prefix="/api/guardrails", tags=["guardrails"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["notifications"])
app.include_router(query_router, prefix="/api/query", tags=["query"])
app.include_router(voice_export_router, prefix="/api/chat/voice", tags=["chat-voice"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(ragas_router, prefix="/api/ragas", tags=["ragas"])
app.include_router(troubleshoot_router, prefix="/api/troubleshoot", tags=["troubleshoot"])

# Vercel Services mounts the backend at routePrefix="/api" and forwards the
# stripped path to FastAPI, so /api/auth/guest arrives here as /auth/guest.
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(documents_router, prefix="/documents", tags=["documents"])
app.include_router(guardrails_router, prefix="/guardrails", tags=["guardrails"])
app.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
app.include_router(query_router, prefix="/query", tags=["query"])
app.include_router(voice_export_router, prefix="/chat/voice", tags=["chat-voice"])
app.include_router(settings_router, prefix="/settings", tags=["settings"])
app.include_router(ragas_router, prefix="/ragas", tags=["ragas"])
app.include_router(troubleshoot_router, prefix="/troubleshoot", tags=["troubleshoot"])


@app.get("/api/health", tags=["health"])
async def health():
    # OWASP A05: suppress environment disclosure in non-development deployments (S2)
    resp: dict = {"status": "ok"}
    if settings.app_env == "development":
        resp["env"] = settings.app_env
    return resp


@app.get("/health", tags=["health"])
async def health_services():
    return await health()


def _component(status_value: str, **details):
    return {"status": status_value, **details}


def _component_failure(component_name: str, exc: Exception):
    log.warning(
        "readiness_component_failed",
        component=component_name,
        error_type=type(exc).__name__,
    )
    return _component("degraded", error="dependency_check_failed")


def _local_upload_writable() -> bool:
    try:
        if "UPLOAD_DIR" in os.environ:
            path = Path(os.environ["UPLOAD_DIR"])
        elif os.environ.get("VERCEL"):
            path = Path("/tmp/uploads")
        else:
            path = Path(__file__).parent.parent / "uploads"
        check_path = path if path.exists() else path.parent
        return check_path.exists() and check_path.is_dir() and os.access(check_path, os.W_OK)
    except Exception:
        fallback = Path("/tmp" if settings.app_env == "production" else ".")
        return fallback.exists()


def _readiness_status() -> dict:
    components = {}

    try:
        components["app_config"] = _component(
            "ready" if settings.secret_key not in _WEAK_SECRETS else "degraded",
            secret_key_configured=settings.secret_key not in _WEAK_SECRETS,
            environment_disclosure=False,
        )
    except Exception as exc:
        components["app_config"] = _component_failure("app_config", exc)

    try:
        openai_configured = bool(get_effective_api_key())
        components["openai"] = _component(
            "ready" if openai_configured else "degraded",
            configured=openai_configured,
            source="runtime" if is_runtime_key_set() else ("environment" if settings.openai_api_key and account_env_fallback_allowed() else "not_configured"),
        )
    except Exception as exc:
        openai_configured = False
        components["openai"] = _component_failure("openai", exc)

    try:
        vector_store_type = get_effective_vector_store_type()
        pinecone_key_configured = bool(get_effective_pinecone_api_key())
        components["vector_store"] = _component(
            "ready"
            if vector_store_type in {"memory", "chroma", "blob"} or (vector_store_type == "pinecone" and pinecone_key_configured)
            else "degraded",
            type=vector_store_type,
            pinecone_configured=vector_store_type != "pinecone" or pinecone_key_configured,
        )
    except Exception as exc:
        components["vector_store"] = _component_failure("vector_store", exc)

    try:
        file_store_type = get_effective_file_store_type()
        blob_token_configured = bool(get_effective_blob_read_write_token())
        components["file_store"] = _component(
            "ready"
            if file_store_type == "local" and _local_upload_writable()
            else ("ready" if file_store_type == "blob" and blob_token_configured else "degraded"),
            type=file_store_type,
            blob_configured=file_store_type != "blob" or blob_token_configured,
        )
    except Exception as exc:
        components["file_store"] = _component_failure("file_store", exc)

    try:
        components["export"] = _component(
            "ready" if openai_configured else "degraded",
            transcript_redaction=True,
            audio_generation_configured=openai_configured,
        )
    except Exception as exc:
        components["export"] = _component_failure("export", exc)

    overall = "ready" if all(item["status"] == "ready" for item in components.values()) else "degraded"
    return {"status": overall, "components": components}


@app.get("/api/readiness", tags=["health"])
async def readiness():
    body = _readiness_status()
    status_code = status.HTTP_200_OK if body["status"] == "ready" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=body)


@app.get("/readiness", tags=["health"])
async def readiness_services():
    return await readiness()

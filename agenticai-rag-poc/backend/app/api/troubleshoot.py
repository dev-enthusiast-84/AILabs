"""
Troubleshooting agent endpoint.

Accepts error messages, log content, screenshots (vision), and structured
context metadata.  Returns a ranked list of hypotheses with root-cause
analysis and numbered remediation steps.

OWASP A01: endpoint requires any valid JWT (guest or admin).
OWASP A04: rate-limited to 5 requests/minute per IP.
OWASP A05: screenshot content is validated for MIME type and size.
"""
import base64
import json
import re
from typing import Literal

import bleach
import structlog
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from openai import AsyncOpenAI
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth.models import UserInDB
from app.auth.utils import get_current_user
from app.config import get_settings
from app.core.errors import SafeAppError
from app.runtime.runtime_settings_cookie import restore_runtime_settings_from_cookie

log = structlog.get_logger()
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
settings = get_settings()

_MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024   # 8 MB per image
_MAX_SCREENSHOTS = 3
_MAX_ERROR_LEN = 8_000
_MAX_LOG_LEN = 12_000
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}

ComponentType = Literal["frontend", "backend", "agent", "rag", "auth", "deployment", "other"]
EnvironmentType = Literal["local", "docker", "vercel", "production", "unknown"]
SeverityType = Literal["critical", "high", "medium", "low"]

_SYSTEM_PROMPT = """You are an expert debugging assistant for a full-stack Agentic RAG application.

Stack:
- Backend : FastAPI + LangGraph 7-node pipeline (planner→HyDE→retriever→grader→reranker→generator→validator)
- Vector DB: ChromaDB (local/memory) or Pinecone (remote)
- File store: local disk or Vercel Blob
- LLM       : OpenAI GPT-4o / GPT-4o-mini (configurable)
- Frontend  : React 18 + TypeScript + Vite + Tailwind CSS + Zustand auth store
- Auth      : JWT (HS256) with guest and admin roles; 401 → redirect to /login
- Deploy    : Docker Compose (local) or Vercel (serverless)

Respond ONLY with a valid JSON object matching this exact schema (no markdown fences):
{
  "error_category": "<one of: auth|config|network|vectordb|llm|ingestion|agent|frontend|deployment|unknown>",
  "root_cause": "<concise 1-2 sentence root-cause summary>",
  "hypotheses": [
    {
      "rank": 1,
      "title": "<short hypothesis title>",
      "confidence": <0-100>,
      "explanation": "<why this is likely given the evidence>"
    }
  ],
  "remediation_steps": [
    "<numbered step 1>",
    "<numbered step 2>"
  ],
  "follow_up_questions": [
    "<clarifying question if more info would help>"
  ],
  "affected_files": [
    "<relative path to likely affected file, e.g. backend/app/config.py>"
  ]
}

Rules:
- hypotheses: 1-5 items, sorted by confidence descending.
- remediation_steps: 3-8 specific, actionable steps. Reference exact file paths and commands where relevant.
- follow_up_questions: 0-3 items only when diagnosis is ambiguous.
- affected_files: only real paths likely present in this codebase.
- confidence: 0-100 integer. Sum does not need to equal 100.
"""


class Hypothesis(BaseModel):
    rank: int
    title: str
    confidence: int
    explanation: str


class TroubleshootResponse(BaseModel):
    error_category: str
    root_cause: str
    hypotheses: list[Hypothesis]
    remediation_steps: list[str]
    follow_up_questions: list[str]
    affected_files: list[str]


def _sanitize_text(text: str, max_len: int) -> str:
    """Strip HTML tags and truncate."""
    return bleach.clean(text, tags=[], strip=True)[:max_len]


def _build_user_prompt(
    error_message: str,
    log_content: str | None,
    component: str | None,
    environment: str | None,
    severity: str | None,
) -> str:
    parts: list[str] = []
    if component:
        parts.append(f"Component: {component}")
    if environment:
        parts.append(f"Environment: {environment}")
    if severity:
        parts.append(f"Severity: {severity}")
    if parts:
        parts.insert(0, "Context:")
        parts.append("")

    parts.append("=== Error / Stack trace ===")
    parts.append(error_message)

    if log_content:
        parts.append("\n=== Log output ===")
        parts.append(log_content)

    return "\n".join(parts)


async def _read_screenshots(files: list[UploadFile]) -> list[dict]:
    """Read and base64-encode uploaded screenshots for the vision API."""
    encoded: list[dict] = []
    for f in files[:_MAX_SCREENSHOTS]:
        content_type = f.content_type or "image/png"
        if content_type not in _ALLOWED_IMAGE_TYPES:
            log.warning("troubleshoot.screenshot_rejected", reason="invalid_mime", mime=content_type)
            continue
        data = await f.read()
        if len(data) > _MAX_SCREENSHOT_BYTES:
            log.warning("troubleshoot.screenshot_rejected", reason="too_large", size=len(data))
            continue
        encoded.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{content_type};base64,{base64.b64encode(data).decode()}",
                "detail": "low",
            },
        })
    return encoded


def _parse_llm_response(raw: str) -> TroubleshootResponse:
    """Extract and validate JSON from the LLM output."""
    # Strip any accidental markdown fences
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    data = json.loads(text)

    hypotheses = [
        Hypothesis(
            rank=int(h.get("rank", i + 1)),
            title=str(h.get("title", "")),
            confidence=max(0, min(100, int(h.get("confidence", 50)))),
            explanation=str(h.get("explanation", "")),
        )
        for i, h in enumerate(data.get("hypotheses", []))
    ]
    hypotheses.sort(key=lambda h: h.rank)

    return TroubleshootResponse(
        error_category=str(data.get("error_category", "unknown")),
        root_cause=str(data.get("root_cause", "")),
        hypotheses=hypotheses,
        remediation_steps=[str(s) for s in data.get("remediation_steps", [])],
        follow_up_questions=[str(q) for q in data.get("follow_up_questions", [])],
        affected_files=[str(p) for p in data.get("affected_files", [])],
    )


@router.post("/analyze", response_model=TroubleshootResponse)
@limiter.limit("5/minute")
async def analyze(
    request: Request,
    error_message: str = Form(..., max_length=_MAX_ERROR_LEN),
    log_content: str | None = Form(default=None),
    component: str | None = Form(default=None),
    environment: str | None = Form(default=None),
    severity: str | None = Form(default=None),
    screenshots: list[UploadFile] | None = File(default=None),
    _user: UserInDB = Depends(get_current_user),
) -> TroubleshootResponse:
    """Analyse an error and return ranked hypotheses with remediation steps.

    Accepts up to 3 screenshots (PNG/JPEG/WebP ≤ 8 MB each) for vision-based
    analysis.  Rate-limited to 5 requests/minute per IP (OWASP A04).
    """
    restore_runtime_settings_from_cookie(request, _user)

    from app.runtime.settings_store import get_effective_api_key, get_effective_model
    api_key = get_effective_api_key()
    if not api_key:
        raise SafeAppError(
            category="openai_provider_error",
            status_code=503,
            public_message="LLM API key is not configured. Set your OpenAI key in Settings.",
        )

    clean_error = _sanitize_text(error_message, _MAX_ERROR_LEN)
    clean_log = _sanitize_text(log_content, _MAX_LOG_LEN) if log_content else None

    image_parts = await _read_screenshots(screenshots or [])
    user_text = _build_user_prompt(clean_error, clean_log, component, environment, severity)

    user_content: list[dict] = [{"type": "text", "text": user_text}]
    user_content.extend(image_parts)

    log.info(
        "troubleshoot.analyze",
        user=_user.username,
        role=_user.role,
        component=component,
        environment=environment,
        has_screenshots=bool(image_parts),
    )

    try:
        client = AsyncOpenAI(api_key=api_key)
        completion = await client.chat.completions.create(
            model=get_effective_model(),
            temperature=0.1,
            max_tokens=1200,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        raw = completion.choices[0].message.content or ""
        return _parse_llm_response(raw)
    except json.JSONDecodeError as exc:
        log.error("troubleshoot.parse_error", error=str(exc))
        raise SafeAppError(
            category="openai_provider_error",
            status_code=502,
            public_message="Unexpected response from the LLM — could not parse diagnosis.",
        ) from exc
    except SafeAppError:
        raise
    except Exception as exc:
        log.error("troubleshoot.llm_error", error=str(exc))
        raise SafeAppError(
            category="openai_provider_error",
            status_code=502,
            public_message="LLM call failed. Check your API key and try again.",
        ) from exc

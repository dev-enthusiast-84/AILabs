import base64
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from openai import APITimeoutError, OpenAI
from pydantic import BaseModel, Field, field_validator, model_validator

from app.audit import audit_event
from app.auth.models import UserInDB
from app.auth.utils import get_current_user
from app.chat_languages import ChatLanguageCode
from app.config import get_settings
from app.settings_store import get_effective_api_key, set_runtime_scope
from app.voice.export_jobs import VoiceExportJob, VoiceExportJobStatus, VoiceExportJobStore
from app.voice.redaction import build_redacted_transcript, redact_sensitive_text


log = structlog.get_logger()
router = APIRouter()

_AUDIO_MODEL = "tts-1"
_DEFAULT_VOICE = "alloy"
_MAX_MESSAGE_CHARS = 6000
_MAX_MESSAGES = 100
_MAX_TRANSCRIPT_CHARS = 12000
_MAX_AUDIO_INPUT_CHARS = 4000
_MAX_AUDIO_BYTES = 10 * 1024 * 1024
_OPENAI_REQUEST_TIMEOUT_SECONDS = 30.0
_ASYNC_EXPORT_JOB_TTL_SECONDS = 15 * 60
_ASYNC_EXPORT_ARTIFACT_TTL_SECONDS = 10 * 60
_ASYNC_EXPORT_RETRY_AFTER_SECONDS = 1
_ASYNC_EXPORT_MAX_RETRIES = 1
_ASYNC_EXPORT_WORKERS = 2
_ALLOWED_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
    "verse",
}

_job_store = VoiceExportJobStore(
    ttl_seconds=_ASYNC_EXPORT_JOB_TTL_SECONDS,
    artifact_ttl_seconds=_ASYNC_EXPORT_ARTIFACT_TTL_SECONDS,
)
_job_executor = ThreadPoolExecutor(max_workers=_ASYNC_EXPORT_WORKERS, thread_name_prefix="voice-export")


class ChatVoiceExportMessage(BaseModel):
    role: Literal["user", "assistant", "system"] = "assistant"
    content: str = Field(..., min_length=1)
    origin: Literal["typed", "voice"] | None = None

    @field_validator("content")
    @classmethod
    def _trim_content(cls, value: str) -> str:
        value = value.strip()
        if len(value) > _MAX_MESSAGE_CHARS:
            raise ValueError(f"Message content must be {_MAX_MESSAGE_CHARS} characters or fewer.")
        return value


class ChatVoiceExportRequest(BaseModel):
    text: str | None = None
    transcript: str | None = None
    messages: list[ChatVoiceExportMessage] | None = None
    voice: str = Field(default=_DEFAULT_VOICE, max_length=32)
    language: ChatLanguageCode = "en"
    defer: bool = False

    @field_validator("text", "transcript")
    @classmethod
    def _trim_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if len(value) > _MAX_TRANSCRIPT_CHARS:
            raise ValueError(f"Transcript input must be {_MAX_TRANSCRIPT_CHARS} characters or fewer.")
        return value or None

    @field_validator("voice")
    @classmethod
    def _validate_voice(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in _ALLOWED_VOICES:
            raise ValueError("Unsupported voice.")
        return value

    @model_validator(mode="after")
    def _require_export_content(self) -> "ChatVoiceExportRequest":
        has_messages = bool(self.messages)
        if not has_messages and not self.transcript and not self.text:
            raise ValueError("Provide text, transcript, or messages to export.")
        if self.messages and len(self.messages) > _MAX_MESSAGES:
            raise ValueError(f"Export accepts at most {_MAX_MESSAGES} messages.")
        return self


class ChatVoiceExportResponse(BaseModel):
    audio_base64: str
    audio_mime_type: str
    audio_format: Literal["mp3"]
    transcript: str
    redacted: bool
    expires_at: datetime | None = None
    mode: Literal["sync", "async"] = "sync"


class ChatVoiceExportJobError(BaseModel):
    code: str
    message: str


class ChatVoiceExportArtifactResponse(BaseModel):
    audio_base64: str
    audio_mime_type: str
    audio_format: Literal["mp3"]
    expires_at: datetime


class ChatVoiceExportJobPolicy(BaseModel):
    max_retries: int
    timeout_seconds: float
    retry_after_seconds: int
    artifact_ttl_seconds: int


class ChatVoiceExportAcceptedResponse(BaseModel):
    job_id: str
    status: VoiceExportJobStatus
    status_url: str
    cancel_url: str
    expires_at: datetime
    artifact_expires_at: datetime
    retry_after_seconds: int
    policy: ChatVoiceExportJobPolicy


class ChatVoiceExportJobStatusResponse(BaseModel):
    job_id: str
    status: VoiceExportJobStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    artifact_expires_at: datetime
    retry_count: int
    policy: ChatVoiceExportJobPolicy
    artifact: ChatVoiceExportArtifactResponse | None = None
    error: ChatVoiceExportJobError | None = None


class ChatTranscriptRedactionResponse(BaseModel):
    transcript: str
    redacted: bool


def _safe_error(code: str, message: str, **extra: object) -> dict[str, object]:
    return {
        "code": code,
        "message": message,
        **extra,
    }


def _raise_safe_error(status_code: int, code: str, message: str, **extra: object) -> None:
    raise HTTPException(
        status_code=status_code,
        detail=_safe_error(code, message, **extra),
    )


def _owner_key(user: UserInDB) -> str:
    return f"{user.role}:{user.session_id or user.username}"


def _job_policy() -> ChatVoiceExportJobPolicy:
    return ChatVoiceExportJobPolicy(
        max_retries=_ASYNC_EXPORT_MAX_RETRIES,
        timeout_seconds=_OPENAI_REQUEST_TIMEOUT_SECONDS,
        retry_after_seconds=_ASYNC_EXPORT_RETRY_AFTER_SECONDS,
        artifact_ttl_seconds=_ASYNC_EXPORT_ARTIFACT_TTL_SECONDS,
    )


def _raw_export_text(body: ChatVoiceExportRequest) -> str:
    if body.messages:
        lines = [
            f"{message.role.strip().title()}: {message.content.strip()}"
            for message in body.messages
            if message.content.strip()
        ]
        return "\n\n".join(lines)
    return body.transcript or body.text or ""


def _export_text(body: ChatVoiceExportRequest) -> str:
    if body.messages:
        return build_redacted_transcript((message.role, message.content) for message in body.messages)
    return redact_sensitive_text(body.transcript or body.text or "")


def _enforce_transcript_limit(*, request: Request, user: UserInDB, transcript: str, event: str) -> None:
    if len(transcript) <= _MAX_TRANSCRIPT_CHARS:
        return
    audit_event(
        event,
        status="rejected",
        request=request,
        user=user,
        error_category="transcript_too_large",
        transcript_chars=len(transcript),
        max_transcript_chars=_MAX_TRANSCRIPT_CHARS,
    )
    _raise_safe_error(
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        "transcript_too_large",
        f"Export transcript must be {_MAX_TRANSCRIPT_CHARS} characters or fewer.",
        limit_chars=_MAX_TRANSCRIPT_CHARS,
        actual_chars=len(transcript),
    )


def _enforce_audio_input_limit(*, request: Request, user: UserInDB, transcript: str) -> None:
    if len(transcript) <= _MAX_AUDIO_INPUT_CHARS:
        return
    audit_event(
        "voice_export",
        status="rejected",
        request=request,
        user=user,
        error_category="audio_input_too_large",
        transcript_chars=len(transcript),
        max_audio_input_chars=_MAX_AUDIO_INPUT_CHARS,
    )
    _raise_safe_error(
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        "audio_input_too_large",
        f"Audio export transcript must be {_MAX_AUDIO_INPUT_CHARS} characters or fewer.",
        limit_chars=_MAX_AUDIO_INPUT_CHARS,
        actual_chars=len(transcript),
    )


def _response_bytes(response: object) -> bytes:
    content = getattr(response, "content", None)
    if isinstance(content, bytes):
        return content
    read = getattr(response, "read", None)
    if callable(read):
        data = read()
        if isinstance(data, bytes):
            return data
    if isinstance(response, bytes):
        return response
    raise TypeError("OpenAI audio response did not contain bytes.")


def _generate_speech_mp3(*, api_key: str, text: str, voice: str) -> bytes:
    client = OpenAI(api_key=api_key, timeout=_OPENAI_REQUEST_TIMEOUT_SECONDS)
    response = client.audio.speech.create(
        model=_AUDIO_MODEL,
        voice=voice,
        input=text,
        response_format="mp3",
    )
    return _response_bytes(response)


def _text_chunks(text: str, *, max_chars: int = _MAX_AUDIO_INPUT_CHARS) -> list[str]:
    chunks: list[str] = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n\n", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = remaining.rfind(" ", 0, max_chars)
        if split_at < max_chars // 2:
            split_at = max_chars
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    return [chunk for chunk in chunks if chunk]


def _generate_export_audio_mp3(*, api_key: str, text: str, voice: str) -> bytes:
    chunks = _text_chunks(text)
    audio_parts = [_generate_speech_mp3(api_key=api_key, text=chunk, voice=voice) for chunk in chunks]
    return b"".join(audio_parts)


def _serialize_job(job: VoiceExportJob) -> ChatVoiceExportJobStatusResponse:
    artifact = None
    if job.artifact is not None:
        artifact = ChatVoiceExportArtifactResponse(
            audio_base64=base64.b64encode(job.artifact.audio).decode("ascii"),
            audio_mime_type=job.artifact.mime_type,
            audio_format=job.artifact.audio_format,
            expires_at=job.artifact.expires_at,
        )
    error = None
    if job.error_code and job.error_message:
        error = ChatVoiceExportJobError(code=job.error_code, message=job.error_message)
    return ChatVoiceExportJobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        expires_at=job.expires_at,
        artifact_expires_at=job.artifact_expires_at,
        retry_count=job.retry_count,
        policy=_job_policy(),
        artifact=artifact,
        error=error,
    )


def _accepted_response(job: VoiceExportJob) -> ChatVoiceExportAcceptedResponse:
    return ChatVoiceExportAcceptedResponse(
        job_id=job.job_id,
        status=job.status,
        status_url=f"/api/chat/voice/export/jobs/{job.job_id}",
        cancel_url=f"/api/chat/voice/export/jobs/{job.job_id}",
        expires_at=job.expires_at,
        artifact_expires_at=job.artifact_expires_at,
        retry_after_seconds=_ASYNC_EXPORT_RETRY_AFTER_SECONDS,
        policy=_job_policy(),
    )


def _run_export_job(*, job_id: str, api_key: str, transcript: str, voice: str) -> None:
    if not _job_store.mark_running(job_id=job_id):
        return

    retry_count = 0
    while True:
        try:
            audio = _generate_export_audio_mp3(api_key=api_key, text=transcript, voice=voice)
            if not audio:
                raise ValueError("OpenAI audio response was empty.")
            if len(audio) > _MAX_AUDIO_BYTES:
                _job_store.fail(
                    job_id=job_id,
                    code="audio_response_too_large",
                    message="Audio export response was too large to retain safely. Try a shorter transcript.",
                    retry_count=retry_count,
                )
                return
            _job_store.complete(job_id=job_id, audio=audio)
            return
        except APITimeoutError:
            if retry_count >= _ASYNC_EXPORT_MAX_RETRIES:
                _job_store.fail(
                    job_id=job_id,
                    code="voice_export_timeout",
                    message="Audio export timed out after retry. Try a shorter transcript and export again.",
                    retry_count=retry_count,
                )
                return
            retry_count += 1
            if not _job_store.mark_retry(job_id=job_id, retry_count=retry_count):
                return
            time.sleep(_ASYNC_EXPORT_RETRY_AFTER_SECONDS)
        except Exception as exc:
            log.warning("voice_export_job_failed", job_id=job_id, error_type=type(exc).__name__)
            _job_store.fail(
                job_id=job_id,
                code="voice_export_generation_failed",
                message="Failed to generate chat audio export. Verify your OpenAI API key and try again.",
                retry_count=retry_count,
            )
            return


def _should_defer_export(*, body: ChatVoiceExportRequest, transcript: str) -> bool:
    return body.defer or get_settings().app_env == "production" or len(transcript) > _MAX_AUDIO_INPUT_CHARS


@router.post("/export", response_model=ChatVoiceExportResponse | ChatVoiceExportAcceptedResponse)
async def export_chat_voice(
    request: Request,
    body: ChatVoiceExportRequest,
    user: UserInDB = Depends(get_current_user),
):
    """Generate playable audio from a redacted chat export transcript."""
    set_runtime_scope(user.role, user.session_id)
    api_key = get_effective_api_key()
    if not api_key:
        audit_event("voice_export", status="rejected", request=request, user=user, error_category="missing_api_key")
        _raise_safe_error(
            status.HTTP_400_BAD_REQUEST,
            "missing_api_key",
            "OpenAI API key is required to generate chat audio export. Add a key in Settings and try again.",
        )

    original_text = _raw_export_text(body)
    _enforce_transcript_limit(request=request, user=user, transcript=original_text, event="voice_export")
    transcript = _export_text(body)
    if not transcript:
        audit_event("voice_export", status="rejected", request=request, user=user, error_category="empty_after_redaction")
        _raise_safe_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "empty_after_redaction",
            "Export transcript is empty after redaction.",
        )
    _enforce_transcript_limit(request=request, user=user, transcript=transcript, event="voice_export")

    if _should_defer_export(body=body, transcript=transcript):
        job = _job_store.create(
            owner_key=_owner_key(user),
            metadata={
                "language": body.language,
                "voice": body.voice,
                "transcript_chars": len(transcript),
                "redacted": transcript != original_text,
            },
        )
        audit_event(
            "voice_export",
            status="queued",
            request=request,
            user=user,
            language=body.language,
            voice=body.voice,
            transcript_chars=len(transcript),
            job_id=job.job_id,
            max_retries=_ASYNC_EXPORT_MAX_RETRIES,
            timeout_seconds=_OPENAI_REQUEST_TIMEOUT_SECONDS,
            artifact_ttl_seconds=_ASYNC_EXPORT_ARTIFACT_TTL_SECONDS,
        )
        _job_executor.submit(_run_export_job, job_id=job.job_id, api_key=api_key, transcript=transcript, voice=body.voice)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content=_accepted_response(job).model_dump(mode="json"),
            headers={"Retry-After": str(_ASYNC_EXPORT_RETRY_AFTER_SECONDS)},
        )

    _enforce_audio_input_limit(request=request, user=user, transcript=original_text)
    _enforce_audio_input_limit(request=request, user=user, transcript=transcript)

    try:
        audit_event(
            "voice_export",
            status="started",
            request=request,
            user=user,
            language=body.language,
            voice=body.voice,
            transcript_chars=len(transcript),
        )
        audio = _generate_speech_mp3(api_key=api_key, text=transcript, voice=body.voice)
        if not audio:
            raise ValueError("OpenAI audio response was empty.")
        if len(audio) > _MAX_AUDIO_BYTES:
            audit_event(
                "voice_export",
                status="rejected",
                request=request,
                user=user,
                error_category="audio_response_too_large",
                audio_bytes=len(audio),
                max_audio_bytes=_MAX_AUDIO_BYTES,
            )
            _raise_safe_error(
                status.HTTP_502_BAD_GATEWAY,
                "audio_response_too_large",
                "Audio export response was too large to return safely. Try a shorter transcript.",
                limit_bytes=_MAX_AUDIO_BYTES,
            )
    except APITimeoutError as exc:
        log.warning(
            "voice_export_generation_timeout",
            user_role=user.role,
            timeout_seconds=_OPENAI_REQUEST_TIMEOUT_SECONDS,
        )
        audit_event("voice_export", status="failed", request=request, user=user, error_category="timeout")
        _raise_safe_error(
            status.HTTP_504_GATEWAY_TIMEOUT,
            "voice_export_timeout",
            "Audio export timed out. Try a shorter transcript and export again.",
            timeout_seconds=_OPENAI_REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        log.warning(
            "voice_export_generation_failed",
            user_role=user.role,
            error_type=type(exc).__name__,
        )
        audit_event("voice_export", status="failed", request=request, user=user, error_category=type(exc).__name__)
        _raise_safe_error(
            status.HTTP_502_BAD_GATEWAY,
            "voice_export_generation_failed",
            "Failed to generate chat audio export. Verify your OpenAI API key and try again.",
        )

    audit_event(
        "voice_export",
        status="completed",
        request=request,
        user=user,
        language=body.language,
        voice=body.voice,
        redacted=transcript != original_text,
        audio_bytes=len(audio),
    )
    return ChatVoiceExportResponse(
        audio_base64=base64.b64encode(audio).decode("ascii"),
        audio_mime_type="audio/mpeg",
        audio_format="mp3",
        transcript=transcript,
        redacted=transcript != original_text,
    )


@router.get("/export/jobs/{job_id}", response_model=ChatVoiceExportJobStatusResponse)
async def get_voice_export_job(
    job_id: str,
    user: UserInDB = Depends(get_current_user),
):
    """Poll a deferred audio export job and retrieve its in-memory artifact before expiry."""
    job = _job_store.get(job_id=job_id, owner_key=_owner_key(user))
    if job is None:
        _raise_safe_error(
            status.HTTP_404_NOT_FOUND,
            "voice_export_job_not_found",
            "Voice export job was not found or is no longer available.",
        )
    return _serialize_job(job)


@router.delete("/export/jobs/{job_id}", response_model=ChatVoiceExportJobStatusResponse)
async def cancel_voice_export_job(
    job_id: str,
    request: Request,
    user: UserInDB = Depends(get_current_user),
):
    """Cancel a queued/running deferred export and discard any later artifact."""
    job = _job_store.cancel(job_id=job_id, owner_key=_owner_key(user))
    if job is None:
        _raise_safe_error(
            status.HTTP_404_NOT_FOUND,
            "voice_export_job_not_found",
            "Voice export job was not found or is no longer available.",
        )
    audit_event("voice_export", status="canceled", request=request, user=user, job_id=job_id)
    return _serialize_job(job)


@router.post("/redact", response_model=ChatTranscriptRedactionResponse)
async def redact_chat_transcript(
    request: Request,
    body: ChatVoiceExportRequest,
    user: UserInDB = Depends(get_current_user),
):
    """Return the backend-authoritative redacted transcript without generating audio."""
    original_text = _raw_export_text(body)
    _enforce_transcript_limit(request=request, user=user, transcript=original_text, event="transcript_redaction")
    transcript = _export_text(body)
    if not transcript:
        audit_event("transcript_redaction", status="rejected", request=request, user=user, error_category="empty_after_redaction")
        _raise_safe_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "empty_after_redaction",
            "Export transcript is empty after redaction.",
        )
    _enforce_transcript_limit(request=request, user=user, transcript=transcript, event="transcript_redaction")
    redacted = transcript != original_text
    audit_event(
        "transcript_redaction",
        status="completed",
        request=request,
        user=user,
        language=body.language,
        redacted=redacted,
        transcript_chars=len(transcript),
    )
    return ChatTranscriptRedactionResponse(transcript=transcript, redacted=redacted)

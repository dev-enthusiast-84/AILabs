"""In-memory voice export job registry.

This is an app-level fallback for deployments without object storage or a
durable queue. Artifacts are scoped to the authenticated user and expire from
process memory; callers must poll and download promptly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Literal
from uuid import uuid4


VoiceExportJobStatus = Literal["queued", "running", "succeeded", "failed", "canceled", "expired"]


@dataclass
class VoiceExportArtifact:
    audio: bytes
    mime_type: str
    audio_format: Literal["mp3"]
    expires_at: datetime


@dataclass
class VoiceExportJob:
    job_id: str
    owner_key: str
    status: VoiceExportJobStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    artifact_expires_at: datetime
    retry_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    artifact: VoiceExportArtifact | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class VoiceExportJobStore:
    def __init__(self, *, ttl_seconds: int, artifact_ttl_seconds: int) -> None:
        self._ttl = timedelta(seconds=ttl_seconds)
        self._artifact_ttl = timedelta(seconds=artifact_ttl_seconds)
        self._jobs: dict[str, VoiceExportJob] = {}
        self._lock = Lock()

    def create(self, *, owner_key: str, metadata: dict[str, object] | None = None) -> VoiceExportJob:
        now = datetime.now(UTC)
        job = VoiceExportJob(
            job_id=uuid4().hex,
            owner_key=owner_key,
            status="queued",
            created_at=now,
            updated_at=now,
            expires_at=now + self._ttl,
            artifact_expires_at=now + self._artifact_ttl,
            metadata=metadata or {},
        )
        with self._lock:
            self._purge_expired_locked(now)
            self._jobs[job.job_id] = job
            return self._copy(job)

    def get(self, *, job_id: str, owner_key: str) -> VoiceExportJob | None:
        now = datetime.now(UTC)
        with self._lock:
            self._purge_expired_locked(now)
            job = self._jobs.get(job_id)
            if job is None or job.owner_key != owner_key:
                return None
            if job.status == "succeeded" and now >= job.artifact_expires_at:
                job.status = "expired"
                job.artifact = None
                job.updated_at = now
            return self._copy(job)

    def mark_running(self, *, job_id: str) -> bool:
        now = datetime.now(UTC)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued" or now >= job.expires_at:
                return False
            job.status = "running"
            job.updated_at = now
            return True

    def mark_retry(self, *, job_id: str, retry_count: int) -> bool:
        now = datetime.now(UTC)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"canceled", "expired"}:
                return False
            job.retry_count = retry_count
            job.updated_at = now
            return True

    def complete(self, *, job_id: str, audio: bytes, mime_type: str = "audio/mpeg") -> bool:
        now = datetime.now(UTC)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"canceled", "expired"}:
                return False
            job.status = "succeeded"
            job.updated_at = now
            job.artifact_expires_at = now + self._artifact_ttl
            job.artifact = VoiceExportArtifact(
                audio=audio,
                mime_type=mime_type,
                audio_format="mp3",
                expires_at=job.artifact_expires_at,
            )
            return True

    def fail(self, *, job_id: str, code: str, message: str, retry_count: int) -> bool:
        now = datetime.now(UTC)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"canceled", "expired"}:
                return False
            job.status = "failed"
            job.updated_at = now
            job.retry_count = retry_count
            job.error_code = code
            job.error_message = message
            job.artifact = None
            return True

    def cancel(self, *, job_id: str, owner_key: str) -> VoiceExportJob | None:
        now = datetime.now(UTC)
        with self._lock:
            self._purge_expired_locked(now)
            job = self._jobs.get(job_id)
            if job is None or job.owner_key != owner_key:
                return None
            if job.status in {"queued", "running"}:
                job.status = "canceled"
                job.updated_at = now
                job.artifact = None
            return self._copy(job)

    def force_expire(self, *, job_id: str) -> None:
        """Test helper: expire a job/artifact without sleeping."""
        now = datetime.now(UTC)
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.expires_at = now - timedelta(seconds=1)
            job.artifact_expires_at = now - timedelta(seconds=1)

    def reset(self) -> None:
        with self._lock:
            self._jobs.clear()

    def _purge_expired_locked(self, now: datetime) -> None:
        for job in self._jobs.values():
            if job.status == "succeeded" and now >= job.artifact_expires_at:
                job.status = "expired"
                job.artifact = None
                job.updated_at = now

    @staticmethod
    def _copy(job: VoiceExportJob) -> VoiceExportJob:
        artifact = None
        if job.artifact is not None:
            artifact = VoiceExportArtifact(
                audio=job.artifact.audio,
                mime_type=job.artifact.mime_type,
                audio_format=job.artifact.audio_format,
                expires_at=job.artifact.expires_at,
            )
        return VoiceExportJob(
            job_id=job.job_id,
            owner_key=job.owner_key,
            status=job.status,
            created_at=job.created_at,
            updated_at=job.updated_at,
            expires_at=job.expires_at,
            artifact_expires_at=job.artifact_expires_at,
            retry_count=job.retry_count,
            error_code=job.error_code,
            error_message=job.error_message,
            artifact=artifact,
            metadata=dict(job.metadata),
        )

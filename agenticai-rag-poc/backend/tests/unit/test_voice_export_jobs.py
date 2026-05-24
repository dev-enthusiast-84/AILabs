"""Unit tests for app.voice.export_jobs — targets previously uncovered lines.

Uncovered lines (pre-fix): 76-78, 86, 96, 119-130, 151.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.voice.export_jobs import VoiceExportJobStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store() -> VoiceExportJobStore:
    """Fresh store with generous TTLs."""
    return VoiceExportJobStore(ttl_seconds=3600, artifact_ttl_seconds=3600)


@pytest.fixture()
def store_short_ttl() -> VoiceExportJobStore:
    """Store with very short TTLs to test expiry paths."""
    return VoiceExportJobStore(ttl_seconds=1, artifact_ttl_seconds=1)


# ---------------------------------------------------------------------------
# Lines 75-78: get() — succeeded job whose artifact has already expired
# should transition status to "expired" and clear the artifact.
# ---------------------------------------------------------------------------


def test_get_transitions_succeeded_to_expired_when_artifact_ttl_elapsed(store: VoiceExportJobStore) -> None:
    """Lines 76-78: artifact expiry inside get() flips status and clears artifact."""
    job = store.create(owner_key="user-a")
    # Drive it to succeeded state.
    store.mark_running(job_id=job.job_id)
    store.complete(job_id=job.job_id, audio=b"audio-data")

    # Force the artifact TTL to the past so the expiry branch is hit.
    store.force_expire(job_id=job.job_id)

    result = store.get(job_id=job.job_id, owner_key="user-a")

    assert result is not None
    assert result.status == "expired"
    assert result.artifact is None


def test_get_returns_none_for_unknown_job(store: VoiceExportJobStore) -> None:
    """Line 73: job not found → None."""
    assert store.get(job_id="nonexistent", owner_key="user-a") is None


def test_get_returns_none_for_wrong_owner(store: VoiceExportJobStore) -> None:
    """Line 73: owner_key mismatch → None."""
    job = store.create(owner_key="user-a")
    assert store.get(job_id=job.job_id, owner_key="user-b") is None


def test_get_does_not_expire_running_job(store: VoiceExportJobStore) -> None:
    """Artifact expiry branch only fires for succeeded jobs."""
    job = store.create(owner_key="user-a")
    store.mark_running(job_id=job.job_id)
    store.force_expire(job_id=job.job_id)

    result = store.get(job_id=job.job_id, owner_key="user-a")

    assert result is not None
    assert result.status == "running"


# ---------------------------------------------------------------------------
# Line 86: mark_running() returns False for missing / non-queued / expired job
# ---------------------------------------------------------------------------


def test_mark_running_returns_false_for_missing_job(store: VoiceExportJobStore) -> None:
    """Line 86 (job is None): unknown job_id → False."""
    assert store.mark_running(job_id="ghost") is False


def test_mark_running_returns_false_for_non_queued_job(store: VoiceExportJobStore) -> None:
    """Line 86 (status != queued): already-running job → False."""
    job = store.create(owner_key="user-a")
    store.mark_running(job_id=job.job_id)
    # Second call: no longer queued.
    assert store.mark_running(job_id=job.job_id) is False


def test_mark_running_returns_false_for_expired_job(store: VoiceExportJobStore) -> None:
    """Line 86 (now >= expires_at): job past its TTL → False."""
    job = store.create(owner_key="user-a")
    store.force_expire(job_id=job.job_id)
    assert store.mark_running(job_id=job.job_id) is False


def test_mark_running_returns_true_for_valid_queued_job(store: VoiceExportJobStore) -> None:
    """Baseline: queued job within TTL → True and status flips."""
    job = store.create(owner_key="user-a")
    assert store.mark_running(job_id=job.job_id) is True
    result = store.get(job_id=job.job_id, owner_key="user-a")
    assert result is not None
    assert result.status == "running"


# ---------------------------------------------------------------------------
# Line 96: mark_retry() returns False for missing/canceled/expired jobs
# ---------------------------------------------------------------------------


def test_mark_retry_returns_false_for_missing_job(store: VoiceExportJobStore) -> None:
    """Line 96 (job is None): unknown job_id → False."""
    assert store.mark_retry(job_id="ghost", retry_count=1) is False


def test_mark_retry_returns_false_for_canceled_job(store: VoiceExportJobStore) -> None:
    """Line 96 (status == canceled): canceled job → False."""
    job = store.create(owner_key="user-a")
    store.cancel(job_id=job.job_id, owner_key="user-a")
    assert store.mark_retry(job_id=job.job_id, retry_count=1) is False


def test_mark_retry_returns_false_for_expired_job(store: VoiceExportJobStore) -> None:
    """Line 96 (status == expired): expired job → False."""
    job = store.create(owner_key="user-a")
    store.mark_running(job_id=job.job_id)
    store.complete(job_id=job.job_id, audio=b"data")
    store.force_expire(job_id=job.job_id)
    # Trigger the expiry transition via get().
    store.get(job_id=job.job_id, owner_key="user-a")
    assert store.mark_retry(job_id=job.job_id, retry_count=2) is False


def test_mark_retry_updates_count_for_running_job(store: VoiceExportJobStore) -> None:
    """Baseline: running job → True and retry_count updated."""
    job = store.create(owner_key="user-a")
    store.mark_running(job_id=job.job_id)
    result = store.mark_retry(job_id=job.job_id, retry_count=3)
    assert result is True
    fetched = store.get(job_id=job.job_id, owner_key="user-a")
    assert fetched is not None
    assert fetched.retry_count == 3


# ---------------------------------------------------------------------------
# Lines 119-130: fail() — happy path + guard for missing/canceled/expired jobs
# ---------------------------------------------------------------------------


def test_fail_sets_error_fields_on_running_job(store: VoiceExportJobStore) -> None:
    """Lines 124-129: fail() persists all error fields for a running job."""
    job = store.create(owner_key="user-a")
    store.mark_running(job_id=job.job_id)
    result = store.fail(
        job_id=job.job_id,
        code="TTS_ERROR",
        message="TTS service unavailable",
        retry_count=2,
    )
    assert result is True

    fetched = store.get(job_id=job.job_id, owner_key="user-a")
    assert fetched is not None
    assert fetched.status == "failed"
    assert fetched.error_code == "TTS_ERROR"
    assert fetched.error_message == "TTS service unavailable"
    assert fetched.retry_count == 2
    assert fetched.artifact is None


def test_fail_returns_false_for_missing_job(store: VoiceExportJobStore) -> None:
    """Line 122 (job is None): unknown job_id → False."""
    assert store.fail(job_id="ghost", code="ERR", message="oops", retry_count=0) is False


def test_fail_returns_false_for_canceled_job(store: VoiceExportJobStore) -> None:
    """Line 122 (status == canceled): already-canceled job → False."""
    job = store.create(owner_key="user-a")
    store.cancel(job_id=job.job_id, owner_key="user-a")
    assert store.fail(job_id=job.job_id, code="ERR", message="oops", retry_count=0) is False


def test_fail_returns_false_for_expired_job(store: VoiceExportJobStore) -> None:
    """Line 122 (status == expired): expired job → False."""
    job = store.create(owner_key="user-a")
    store.mark_running(job_id=job.job_id)
    store.complete(job_id=job.job_id, audio=b"audio")
    store.force_expire(job_id=job.job_id)
    store.get(job_id=job.job_id, owner_key="user-a")  # trigger expiry transition
    assert store.fail(job_id=job.job_id, code="ERR", message="late", retry_count=1) is False


def test_fail_clears_existing_artifact(store: VoiceExportJobStore) -> None:
    """Line 129 (artifact = None): fail() wipes any partial artifact."""
    job = store.create(owner_key="user-a")
    store.mark_running(job_id=job.job_id)
    store.complete(job_id=job.job_id, audio=b"partial")
    # Directly fail an already-succeeded job (not canceled/expired) to hit line 129.
    result = store.fail(
        job_id=job.job_id,
        code="POST_COMPLETE_ERR",
        message="something went wrong after completion",
        retry_count=1,
    )
    assert result is True
    fetched = store.get(job_id=job.job_id, owner_key="user-a")
    assert fetched is not None
    assert fetched.artifact is None
    assert fetched.status == "failed"


# ---------------------------------------------------------------------------
# Line 151: force_expire() early return when job_id is not found
# ---------------------------------------------------------------------------


def test_force_expire_is_noop_for_missing_job(store: VoiceExportJobStore) -> None:
    """Line 151: force_expire() on unknown id returns silently without error."""
    # Should not raise.
    store.force_expire(job_id="does-not-exist")


def test_force_expire_sets_past_timestamps_for_existing_job(store: VoiceExportJobStore) -> None:
    """Baseline: force_expire() pushes both TTLs into the past."""
    job = store.create(owner_key="user-a")
    store.force_expire(job_id=job.job_id)
    now = datetime.now(UTC)
    # Access internal state directly to verify timestamps were rewound.
    internal = store._jobs[job.job_id]  # noqa: SLF001
    assert internal.expires_at < now
    assert internal.artifact_expires_at < now

# Spec 005 Compliance And Extension Checklist

> [Home](README.md) · [Coverage Matrix](testing/COVERAGE-MATRIX.md) · [Security](security/SECURITY.md)

This checklist tracks `005-enterprise-production-hardening` recommendations without requiring paid services. Runtime-heavy local persistence and cloud products are intentionally kept out of the default app path.

## Current No-Paid Coverage

| Area | Status | Evidence |
|------|--------|----------|
| Backend-authoritative export redaction | Implemented | `backend/app/voice/redaction.py`, `backend/tests/unit/test_voice_redaction.py`, `backend/tests/integration/test_api_voice_export.py` |
| Redaction fixture matrix | Implemented | API keys, project keys, bearer tokens, refresh/API tokens, passwords, client secrets, private keys, emails, phones, SSNs, payment cards, and long opaque secrets are covered in `test_voice_redaction.py` |
| Shared chat language contract | Implemented | `shared/chat_languages.json`, `scripts/generate_chat_languages.py`, generated backend/frontend language modules, contract drift tests |
| Async export workflow | Implemented as local fallback | In-memory user-scoped jobs support queued/running/succeeded/failed/canceled/expired states, polling, cancellation, retry, timeout policy, and artifact expiry |
| Typed safe backend errors | Implemented | `backend/app/errors.py`, query/document provider and storage failure tests |
| Request correlation and safe readiness | Implemented | `backend/app/main.py`, `backend/tests/integration/test_api_readiness.py` |
| Offline E2E coverage | Implemented | Mocked Playwright flows cover typed chat, multilingual chat, document access, settings prerequisites, transcript export, and UI structure |
| Coverage matrix | Implemented | `docs/testing/COVERAGE-MATRIX.md` |

## Deliberately Not Added Locally

| Recommendation | Reason |
|----------------|--------|
| SQLite-backed export job/artifact store | Adds schema, cleanup, disk growth, and lifecycle burden for limited demo value. |
| Local file download-token artifacts | Adds file cleanup and access-control complexity; current in-memory expiry is simpler and safer for local use. |
| SQLite audit event store | Adds persistence and retention decisions; current structured logs plus safe audit tests are enough for the capstone path. |

## Cloud Deployment Extension Points

These are documented extension features for a future cloud deployment. They are not enabled by default and do not require paid services for local development.

| Extension | Purpose | Integration Shape |
|-----------|---------|-------------------|
| Durable export queue | Survive process restarts and scale beyond one backend instance. | Replace the in-memory export job registry with a queue adapter such as Redis/RQ, Celery, Cloud Tasks, or a managed workflow service. Keep the existing job status API contract. |
| Object-storage artifacts | Avoid large base64 responses and support signed downloads. | Store generated MP3 artifacts in Blob/S3/GCS/Azure storage and return short-lived signed URLs from the existing job status response. |
| Artifact retention policy | Meet enterprise retention requirements. | Add configurable retention and cleanup jobs for generated audio artifacts and job metadata. |
| External observability sink | Centralize safe operational telemetry. | Forward existing request IDs, `SafeAppError` categories, readiness status, and audit metadata to OpenTelemetry, Sentry, Datadog, CloudWatch, or equivalent. |
| Distributed rate limiting | Keep limits consistent across instances. | Swap in a shared rate-limit backend while preserving current per-route rate-limit behavior. |
| Live-provider E2E stage | Validate deployed integrations without charging by default. | Keep deterministic CI mocked; add an explicitly gated pipeline stage requiring live-provider opt-in and test credentials. |

## Acceptance Boundary

The local/default application is considered complete for the current spec when deterministic tests pass and no paid-provider or cloud-only service is required. Cloud extensions should preserve the current API contracts so the frontend can keep polling, canceling, and handling export failures the same way.

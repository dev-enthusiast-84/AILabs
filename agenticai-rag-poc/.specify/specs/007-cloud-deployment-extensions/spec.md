# Feature Specification: Cloud Deployment Extensions

**Feature Branch**: `007-cloud-deployment-extensions`  
**Created**: 2026-05-19  
**Status**: Draft  
**Input**: User description: "add it as a separate feature file - to be implemented only if cloud deployment is opted in with cloud providers"

## Scope Boundary *(mandatory)*

This feature is optional. It MUST be implemented only when a deployment explicitly opts into cloud providers or managed infrastructure. Local, Docker, test, and capstone-demo paths MUST continue to run without paid cloud products, durable queues, object storage, external observability vendors, or live-provider E2E stages.

The default application behavior remains the `005-enterprise-production-hardening` local fallback: deterministic tests, in-memory export jobs, safe typed errors, backend redaction, readiness, request IDs, and mocked/offline E2E coverage.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Durable Cloud Audio Export Jobs (Priority: P1)

A cloud deployment owner wants long-running audio export jobs to survive process restarts, serverless cold starts, and horizontal scaling.

**Why this priority**: The local in-memory export registry is intentionally lightweight. Cloud deployments need durable state when multiple instances can process or poll the same export job.

**Independent Test**: Configure a cloud queue/job adapter in a non-production test profile with fake credentials or a local emulator; submit a deferred export, restart the app process or simulate worker handoff, and verify the job status remains pollable without exposing secrets.

**Acceptance Scenarios**:

1. **Given** cloud export jobs are enabled, **When** a user starts a deferred audio export, **Then** the job is persisted in a durable queue/store and can be polled by job ID.
2. **Given** the API process restarts after queuing a job, **When** the owner polls the job, **Then** the job remains visible with a safe status.
3. **Given** a different user or guest session polls the job ID, **When** access is checked, **Then** the response is `404` or equivalent non-disclosing denial.
4. **Given** cloud export jobs are not enabled, **When** the app runs locally or in tests, **Then** the existing in-memory job implementation remains active.

---

### User Story 2 - Cloud Artifact Storage And Signed URLs (Priority: P1)

A cloud deployment owner wants generated audio artifacts delivered through object storage instead of large base64 API responses.

**Why this priority**: Object storage and short-lived signed URLs reduce API memory pressure, improve artifact delivery, and fit serverless payload limits.

**Independent Test**: Use an object-storage emulator, fake provider adapter, or mocked storage client to verify upload, signed URL generation, expiration, owner scoping, and cleanup without using paid services in CI.

**Acceptance Scenarios**:

1. **Given** cloud artifact storage is enabled, **When** an audio export succeeds, **Then** the artifact is stored outside process memory and the job status returns a short-lived download reference.
2. **Given** a signed URL expires, **When** the user polls the job, **Then** the status indicates expiration or returns a refreshed owner-scoped URL according to policy.
3. **Given** artifact upload fails, **When** the export job completes generation but cannot store the file, **Then** the job fails with a typed safe error and redacted transcript export remains available.
4. **Given** local mode is active, **When** audio export succeeds, **Then** no cloud storage client is initialized or required.

---

### User Story 3 - External Observability Sink (Priority: P2)

An operator wants production events, request IDs, safe error categories, readiness status, and audit metadata forwarded to an external monitoring system when cloud deployment is opted in.

**Why this priority**: Cloud operations benefit from centralized telemetry, but local development should not need a hosted APM or observability account.

**Independent Test**: Configure a local OpenTelemetry collector, console exporter, or mocked telemetry sink; exercise query, upload, export, readiness, and failure paths; verify no raw prompts, transcripts, document content, or credentials leave the app.

**Acceptance Scenarios**:

1. **Given** an external telemetry sink is configured, **When** safe operational events occur, **Then** request ID, event name, status, safe error category, and role/session scope metadata are emitted.
2. **Given** an exception contains sensitive text, **When** telemetry is emitted, **Then** the telemetry payload omits the sensitive text and includes only safe type/category metadata.
3. **Given** no telemetry sink is configured, **When** the app runs locally, **Then** structured local logs continue to work without external network calls.

---

### User Story 4 - Cloud-Specific Deployment Gates (Priority: P2)

A release owner wants deterministic local CI by default and explicit opt-in stages for live cloud dependencies.

**Why this priority**: Live provider tests can cost money and fail for reasons unrelated to application code. They must be separate from default CI.

**Independent Test**: Run default CI without cloud credentials and verify no live provider calls occur; run the cloud opt-in stage with mocked/emulated providers or explicit credentials and verify cloud adapters are exercised.

**Acceptance Scenarios**:

1. **Given** default CI runs without cloud credentials, **When** tests execute, **Then** cloud deployment extension tests are skipped, mocked, or emulator-backed.
2. **Given** cloud extension tests are explicitly enabled, **When** required provider variables are missing, **Then** the test stage fails fast with a clear prerequisite message and does not run partial live operations.
3. **Given** cloud extension tests are enabled with valid prerequisites, **When** deployment-critical flows run, **Then** durable jobs, artifact storage, signed URL delivery, telemetry export, and readiness are validated.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Cloud extensions MUST be disabled by default for local, Docker, test, and deterministic CI workflows.
- **FR-002**: Cloud extensions MUST require an explicit opt-in configuration value such as `CLOUD_EXTENSIONS_ENABLED=true` or equivalent deployment setting.
- **FR-003**: Durable export queues MUST preserve the existing job status API contract for queued, running, succeeded, failed, canceled, and expired states.
- **FR-004**: Durable export jobs MUST remain owner-scoped by role/session or authenticated user identity.
- **FR-005**: Cloud artifact storage MUST avoid returning large base64 audio payloads for cloud-managed artifacts.
- **FR-006**: Cloud artifact storage MUST return short-lived, owner-scoped, non-secret download references or signed URLs.
- **FR-007**: Artifact retention and cleanup policy MUST be configurable and documented.
- **FR-008**: Cloud provider errors MUST map to typed safe error categories and MUST NOT expose credentials, raw transcripts, provider payloads, raw prompts, or document content.
- **FR-009**: External observability MUST emit only safe metadata: request ID, event name, status, role/session scope, dependency name, and safe error category.
- **FR-010**: Default CI MUST NOT require paid services, cloud credentials, or live provider access.
- **FR-011**: Live/cloud-provider tests MUST be explicitly gated and skipped or failed fast when prerequisites are absent.
- **FR-012**: Local fallback behavior from `005-enterprise-production-hardening` MUST remain available and covered by deterministic tests.
- **FR-013**: Documentation MUST explain provider-specific setup, costs, retention, cleanup, and teardown before enabling cloud extensions.
- **FR-014**: Cloud deployment readiness checks MUST report configured cloud queue, artifact storage, telemetry sink, and provider connectivity without exposing secrets.

### Non-Goals

- This feature does not require any cloud provider for local development.
- This feature does not replace the current local in-memory export job fallback.
- This feature does not mandate one provider. Adapters may target Vercel Blob, S3, GCS, Azure Blob, Redis/RQ, Celery, Cloud Tasks, OpenTelemetry, or equivalent systems.
- This feature does not run live-provider tests in default CI.

## Key Entities *(include if feature involves data)*

- **Cloud Export Job Adapter**: Durable queue/store implementation preserving the existing export job state contract.
- **Cloud Artifact Store Adapter**: Provider-specific storage layer for generated audio artifacts and signed/download references.
- **Signed Artifact Reference**: Short-lived URL or token-bound reference that allows the owner to download an artifact without exposing storage credentials.
- **Cloud Telemetry Sink**: Optional external destination for safe logs, traces, metrics, and audit metadata.
- **Cloud Extension Gate**: Explicit configuration flag and prerequisite validation controlling whether cloud-specific code paths are enabled.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Default local and CI test runs pass without cloud credentials, paid services, or live-provider calls.
- **SC-002**: With cloud extensions disabled, audio export uses the existing local fallback behavior.
- **SC-003**: With cloud extensions enabled in an emulator/mocked provider test profile, deferred export jobs survive process or adapter handoff simulation.
- **SC-004**: Cloud artifact responses avoid base64 payloads for provider-stored artifacts and include expiration metadata.
- **SC-005**: Unauthorized users cannot poll, cancel, or download another user/session artifact.
- **SC-006**: Cloud provider failures return typed safe errors and sanitized logs.
- **SC-007**: Readiness reports cloud extension dependency health without secrets.
- **SC-008**: Documentation includes setup, cost notes, retention/cleanup policy, teardown instructions, and test-gating instructions.

## Assumptions

- Cloud deployment is optional and should not burden the local capstone/demo workflow.
- Provider adapters should preserve existing frontend contracts where possible so the UI keeps polling/canceling jobs consistently.
- Emulator-backed or mocked tests are preferred for deterministic CI; live tests require explicit opt-in.
- Object storage and durable queues are valuable only when the deployment runs across multiple instances, serverless functions, or restart-prone environments.

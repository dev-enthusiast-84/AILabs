# Feature Specification: Lightweight Upload Safety

**Feature Branch**: `009-lightweight-upload-safety`  
**Created**: 2026-05-21  
**Status**: Implemented  
**Input**: User description: "Implement the lightweight virus scanning recommendation as spec kit feature without paid services, Vercel package bloat, or intermittent upload behavior."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Uploads Are Hardened Without Heavy AV (Priority: P1)

An admin or guest uploads an allowed document and the app blocks clearly unsafe payloads before indexing without adding ClamAV or paid scanning services.

**Why this priority**: Vercel deployments must stay under package limits and avoid background services that create flaky user experience.

**Independent Test**: Upload unsafe PDF, CSV, XLSX, executable, and ZIP-like payloads; assert the API returns a clear 422 and no chunks are indexed.

**Acceptance Scenarios**:

1. **Given** a file with an executable signature, **When** it is uploaded under an allowed extension, **Then** upload is rejected before ingestion.
2. **Given** a PDF containing active action markers, **When** an admin uploads it, **Then** upload is rejected with a safe validation message.
3. **Given** an XLSX containing macros, embedded objects, or external relationships, **When** it is uploaded, **Then** upload is rejected before workbook parsing.
4. **Given** a CSV containing spreadsheet formula cells, **When** it is uploaded, **Then** upload is rejected before indexing.

---

### User Story 2 - Vercel Package Remains Lean (Priority: P1)

A production deploy can run the upload safety checks using only stdlib and existing app dependencies.

**Why this priority**: ClamAV and large ML packages can exceed serverless bundle limits or require unavailable daemons.

**Independent Test**: Inspect backend requirements and Vercel packaging; assert this feature adds no new runtime dependency.

**Acceptance Scenarios**:

1. **Given** the app is deployed to Vercel, **When** upload validation runs, **Then** it uses dependency-free checks and existing scanner hooks.
2. **Given** ClamAV is not configured, **When** a document is uploaded, **Then** the user flow does not fail due to missing AV services.

---

### User Story 3 - Safe Files Still Upload Predictably (Priority: P2)

Users can continue uploading valid role-allowed documents without new stale or intermittent behavior.

**Why this priority**: Security hardening must not break the walkthrough or normal guest/admin upload paths.

**Independent Test**: Upload valid TXT, CSV, PDF, and XLSX fixtures; assert successful indexing and document listing for the current role/session.

**Acceptance Scenarios**:

1. **Given** a guest uploads a valid TXT file with UI-provided settings, **When** validation passes, **Then** indexing proceeds normally.
2. **Given** an admin uploads a valid allowed document, **When** validation passes, **Then** listing/query behavior remains scoped to the current role/session.

### Edge Cases

- CSV cells with leading whitespace before `=`, `+`, `-`, or `@` are treated as formula risks.
- XLSX relationship files are scanned only up to a bounded size to avoid resource abuse.
- ZIP/XLSX archives with path traversal, excessive entries, huge entries, or extreme compression ratios are rejected.
- Production deployments still do not fall back to environment-provided billable API keys.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST reject known executable signatures before document ingestion.
- **FR-002**: System MUST validate declared magic bytes for PDF, XLSX, and XLS files.
- **FR-003**: System MUST reject PDF files containing active JavaScript, open actions, launch actions, embedded files, rich media, or additional actions.
- **FR-004**: System MUST reject XLSX files containing macros, ActiveX, embedded OLE objects, external links, or external relationships.
- **FR-005**: System MUST reject CSV cells that may execute as spreadsheet formulas.
- **FR-006**: System MUST reject ZIP/XLSX archives with traversal paths, too many entries, oversized entries, excessive uncompressed size, or extreme compression ratios.
- **FR-007**: System MUST implement these checks without adding paid services, background daemons, network calls, or heavyweight runtime dependencies.
- **FR-008**: System MUST return safe user-facing validation errors without logging uploaded content or billable secrets.

### Key Entities

- **Upload Payload**: Raw file bytes and normalized filename submitted by guest or admin.
- **Safety Validator**: Dependency-free pre-ingestion checks for file signatures, active content, spreadsheet risks, and archive abuse.
- **Scanner Pipeline**: Existing scan orchestration that also performs ZIP bomb, optional ClamAV, and stored prompt-injection checks.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Unsafe PDF, XLSX, CSV, executable, and archive fixtures are rejected with HTTP 422.
- **SC-002**: Valid role-allowed files continue to upload and index without new package dependencies.
- **SC-003**: Vercel deployment package size is not increased by antivirus or ML scanning packages.
- **SC-004**: Safety failures expose only generic validation messages and never reveal API keys or billable configuration.

## Assumptions

- This feature provides lightweight hardening, not full malware detection.
- ClamAV remains optional for local or container deployments only when explicitly configured by operators.
- Guest/admin upload size and type limits continue to be enforced by existing role policy.

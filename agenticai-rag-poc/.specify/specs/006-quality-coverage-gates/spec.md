# Feature Specification: Quality Coverage Gates

**Feature Branch**: `006-quality-coverage-gates`  
**Created**: 2026-05-19  
**Status**: Draft  
**Input**: User description: "Add code coverage and application quality improvements as a spec feature; include only changes that do not introduce refactor, performance, security, or maintainability concerns to the current application"

## Scope Guardrails

This feature is intentionally limited to additive test, coverage, and CI quality checks. It MUST NOT require production runtime refactors, large component splits, provider behavior changes, performance redesigns, security-policy redesigns, dependency replacements, or broad maintainability rewrites.

Allowed changes:

- Add or update focused frontend/backend tests.
- Add coverage thresholds and coverage exclusions for non-application files.
- Add CI workflow steps that run existing test/build commands.
- Add documentation that explains quality gates and how to run them.
- Add test fixtures or mocks needed for missing-settings and coverage scenarios.

Out of scope:

- Refactoring application architecture or splitting large components.
- Changing production request/response contracts except where already supported.
- Changing security controls, CSP, auth, guardrails, or provider credential behavior.
- Adding performance optimization, async job systems, caching redesigns, or storage changes.
- Replacing test frameworks or introducing large new tooling.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Enforce Meaningful Frontend Coverage Gates (Priority: P1)

A developer wants frontend coverage reports to fail when important application coverage drops, while ignoring files that do not represent user-facing app behavior.

**Why this priority**: Coverage currently reports useful information but does not enforce a quality floor. A non-enforced report can drift without blocking regressions.

**Independent Test**: Run `npm run test:coverage` and verify coverage thresholds are enforced for application source files while config/type-only files are excluded.

**Acceptance Scenarios**:

1. **Given** frontend unit tests run with coverage, **When** coverage falls below configured thresholds, **Then** the command fails.
2. **Given** coverage is reported, **When** the report is generated, **Then** config files, type-only files, generated output, E2E specs, and entrypoint bootstrap files are excluded from coverage totals.
3. **Given** current frontend tests pass, **When** coverage gates are introduced, **Then** the initial thresholds are realistic for the current codebase and do not require runtime application changes.

---

### User Story 2 - Cover Missing Settings Prerequisite Prompts (Priority: P1)

A user who starts an operation without required UI-configured settings should receive a clear prompt in the Settings modal explaining exactly what must be configured.

**Why this priority**: The application relies on runtime settings for provider keys and storage tokens. Tests should protect the user guidance that tells users how to unblock an operation.

**Independent Test**: Run focused frontend tests for upload, chat, audio export, and Settings modal prerequisite notices.

**Acceptance Scenarios**:

1. **Given** OpenAI API key is missing, **When** a user attempts upload, chat, audio export, or Ragas evaluation, **Then** the UI shows a specific prerequisite message and opens or points to Settings where applicable.
2. **Given** Pinecone is the active vector store and its key is missing, **When** upload or chat requires retrieval/indexing, **Then** the UI shows a Pinecone-specific prerequisite message.
3. **Given** Blob storage is enabled and its token is missing, **When** upload or chat requires Blob-backed files/chunks, **Then** the UI shows a Blob-specific prerequisite message.
4. **Given** Settings opens because of a prerequisite failure, **When** the modal renders, **Then** it displays the operation-specific notice without hiding existing settings fields.

---

### User Story 3 - Verify Production Billing-Safety Settings Behavior (Priority: P1)

A developer wants backend tests that prove production deployments do not accidentally consume billing-bearing provider values from environment variables.

**Why this priority**: Recent production behavior intentionally requires provider credentials and cost-affecting settings through runtime Settings UI. Tests should prevent regressions.

**Independent Test**: Run backend settings-store and settings API tests with production-mode config patches and verify env fallbacks are ignored while runtime overrides still work.

**Acceptance Scenarios**:

1. **Given** `APP_ENV=production` and `OPENAI_API_KEY` is present in environment config, **When** the effective API key is requested, **Then** it is treated as not configured unless a runtime setting is present.
2. **Given** `APP_ENV=production` and Pinecone, Blob, or LangSmith provider values are present in environment config, **When** effective settings are requested, **Then** those provider values are ignored unless runtime settings are present.
3. **Given** `APP_ENV=production` and model/token cost controls are present in environment config, **When** effective settings are requested, **Then** safe runtime defaults or explicit runtime settings are used.
4. **Given** runtime Settings UI values are applied in production mode, **When** effective settings are requested, **Then** runtime values take precedence and operations can proceed.

---

### User Story 4 - Add Lightweight CI Quality Workflow (Priority: P2)

A maintainer wants pull requests to run the same basic quality checks developers run locally.

**Why this priority**: The repository currently has docs deployment automation, but application-quality checks should also run automatically.

**Independent Test**: Trigger the CI workflow or inspect workflow logs to verify backend compile/tests and frontend build/tests run without requiring live provider credentials.

**Acceptance Scenarios**:

1. **Given** a pull request changes backend or frontend code, **When** CI runs, **Then** it installs dependencies and runs backend unit tests, backend integration tests, frontend build, and frontend unit tests.
2. **Given** live provider credentials are not available, **When** CI runs, **Then** live tests are skipped and CI still validates local deterministic suites.
3. **Given** frontend coverage gates are configured, **When** CI runs frontend coverage, **Then** failures are reported as test failures rather than only as generated reports.
4. **Given** CI passes, **When** a maintainer reviews the result, **Then** generated reports or logs clearly identify which suites ran.

---

### Edge Cases

- Coverage thresholds are set higher than the current application can satisfy without unrelated refactors.
- Coverage includes config, type-only, generated, or E2E files and creates noisy or misleading failures.
- CI accidentally attempts live OpenAI, Pinecone, Blob, Vercel, or browser-microphone flows.
- CI depends on secrets or local `.env` files.
- Settings prerequisite tests become brittle because they assert full prose instead of stable intent.
- Backend production-mode tests leak patched runtime settings into later tests.
- Coverage gates block documentation-only changes unnecessarily.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Frontend coverage MUST have enforceable thresholds for statements, branches, functions, and lines.
- **FR-002**: Frontend coverage MUST exclude config files, E2E specs, generated artifacts, type-only files, test setup files, and bootstrap entrypoints that do not represent application behavior.
- **FR-003**: Initial frontend coverage thresholds MUST be achievable by the current focused test suite without requiring application refactors.
- **FR-004**: Tests MUST verify missing OpenAI settings prompts for upload, chat, audio export, and Ragas evaluation paths.
- **FR-005**: Tests MUST verify missing Pinecone and Blob prerequisite prompts for operations dependent on those settings.
- **FR-006**: Tests MUST verify the Settings modal can display an operation-specific prerequisite notice.
- **FR-007**: Backend tests MUST verify production mode ignores billing-bearing provider env fallbacks for OpenAI, Pinecone, Blob, and LangSmith values.
- **FR-008**: Backend tests MUST verify production mode ignores environment-provided model/token cost controls unless runtime settings are applied.
- **FR-009**: Backend tests MUST verify runtime settings still override production-safe defaults.
- **FR-010**: CI MUST run deterministic backend and frontend quality checks without requiring live provider credentials.
- **FR-011**: CI MUST include frontend build and unit tests.
- **FR-012**: CI MUST include backend unit and integration tests when dependencies install successfully.
- **FR-013**: CI MUST avoid running live tests unless explicitly enabled by a separate opt-in flag or workflow.
- **FR-014**: Documentation MUST describe how to run coverage and quality checks locally.
- **FR-015**: Existing user-facing behavior MUST remain unchanged except for already-supported prerequisite notices and test-only quality gates.
- **FR-016**: The implementation MUST NOT introduce runtime refactors, provider behavior changes, performance redesigns, security-policy redesigns, or broad maintainability rewrites.

### Key Entities *(include if feature involves data)*

- **Coverage Gate**: Enforced coverage threshold configuration for frontend unit tests.
- **Coverage Exclusion**: File pattern excluded from coverage totals because it is config, generated, type-only, bootstrap, or E2E-only.
- **Prerequisite Notice Test Fixture**: Mocked settings state used to verify operation-specific missing-settings prompts.
- **Production Settings Fixture**: Backend test fixture or patch that simulates production config without reading real provider credentials.
- **Quality CI Workflow**: Automated workflow that runs deterministic tests/builds and reports failures.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `npm run test:coverage` fails when coverage drops below configured thresholds and passes with the current focused frontend suite.
- **SC-002**: Frontend coverage totals no longer include config, type-only, generated, bootstrap, or E2E-only files.
- **SC-003**: Focused frontend tests cover OpenAI, Pinecone, Blob, audio export, Ragas, and Settings modal prerequisite notices.
- **SC-004**: Backend tests cover production-mode env fallback blocking for provider credentials and cost-affecting settings.
- **SC-005**: Backend tests prove runtime settings continue to work in production mode.
- **SC-006**: CI runs deterministic backend/frontend quality checks without live provider credentials.
- **SC-007**: Existing backend, frontend, and E2E tests remain runnable with their existing commands.

## Assumptions

- The first version should favor realistic thresholds over aspirational thresholds.
- Coverage gates should focus on application behavior, not framework bootstrap or configuration files.
- CI should validate deterministic suites by default; live provider tests remain manually or separately gated.
- This feature is additive quality infrastructure and should not change production runtime behavior.
- Any future refactor, performance, security, or maintainability hardening belongs in separate specs such as `005-enterprise-production-hardening`.

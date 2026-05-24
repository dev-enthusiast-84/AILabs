# Tasks: Document Cleanup

**Input**: plan.md (Document Cleanup) + contracts/api-doc-cleanup.json
**Branch**: `005-enterprise-production-hardening`
**Stack**: FastAPI + ChromaDB/Pinecone + Vercel Blob (backend) · React 18 + TypeScript + Vitest (frontend)

## Format: `[ID] [P?] [Story] Description`
- **[P]** = parallelisable (independent files, no pending deps)
- **[USn]** = user story scope
- TDD order: test tasks precede implementation tasks within each phase

---

## Dependency Graph

```
Phase 1 (Setup) → Phase 2 (Foundational)
                       ├─► Phase 3 (US1 Guest auto-cleanup)       ─┐
                       ├─► Phase 4 (US2 Admin cleanup + cadence)  ─┤ parallel
                       ├─► Phase 5 (US3 Limit warning + force)      ← needs US2 cadence fields
                       └─► Phase 6 (US4 Notifications)              ← needs US3 upload hook
Phase 7 (Polish) ← all phases complete
```

**MVP scope**: Phases 1–4 (18 tasks) → guest auto-cleanup + admin manual cleanup with cadence.
US3 and US4 are independently testable increments.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Wire new config fields and TypeScript types so all later tasks compile cleanly.

- [ ] T001 Add cadence + notification config fields to `backend/app/config.py`: `admin_cleanup_cadence` (str, default `"monthly"`), `admin_cleanup_custom_value` (int, default 30), `admin_cleanup_custom_unit` (str, default `"days"`), `admin_max_indexed_documents` (int, default 100), `notification_enabled` (bool, default False), `notification_email`, `notification_smtp_host`, `notification_smtp_port` (int, 587), `notification_smtp_user`, `notification_smtp_password`, `notification_ntfy_topic` — all with matching env-var aliases
- [ ] T002 [P] Add TypeScript types to `frontend/src/types/index.ts`: `CleanupResult`, `CleanupStatusResponse`, `CleanupCadence` union type (`"hourly"|"daily"|"weekly"|"biweekly"|"monthly"|"custom"`); extend `SettingsResponse` with `admin_cleanup_cadence`, `admin_cleanup_custom_value`, `admin_cleanup_custom_unit`, `admin_cleanup_retention_hours`, `admin_doc_count`, `admin_doc_limit`, `admin_docs_near_limit`, `notification_enabled`, `notification_email`, `notification_ntfy_topic`
- [ ] T003 [P] Add API client methods to `frontend/src/services/api.ts`: `triggerCleanup(force?: boolean): Promise<CleanupResult>` (POST `/api/documents/cleanup`), `getCleanupStatus(): Promise<CleanupStatusResponse>` (GET `/api/documents/cleanup/status`), `sendTestNotification(): Promise<{email_sent: boolean; ntfy_sent: boolean; errors: string[]}>` (POST `/api/notifications/test`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: CleanupService core and settings_store cadence functions — shared by all user-story phases.

- [ ] T004 Implement `backend/app/rag/cleanup.py`: `CADENCE_HOURS: dict[str, int]` = `{hourly:1, daily:24, weekly:168, biweekly:336, monthly:720}`; isolation predicates `_admin_filter(meta, cutoff_ts)`, `_admin_force_filter(meta)`, `_guest_session_filter(meta, session)`; `_select_documents_for_cleanup(filter_fn) → list[str]` (calls `get_all_documents()`, de-dupes by `source` key); `CleanupService` class with `sweep_admin(force: bool = False) → CleanupResult` and `sweep_guest(current_session: str) → CleanupResult`; module-level `_last_cleanup_result: CleanupResult | None = None`; each sweep calls `_cleanup_document_storage()` + `invalidate_doc_cache()` per source key, collects errors without aborting; import `CleanupResult` Pydantic model from `app.core.errors` or define locally in this file
- [ ] T005 [P] Add cadence resolution to `backend/app/runtime/settings_store.py`: module-level globals `_runtime_cleanup_cadence`, `_runtime_cleanup_custom_value`, `_runtime_cleanup_custom_unit`; `get_effective_cleanup_retention_hours() → int` resolving preset via `CADENCE_HOURS` (imported from `cleanup.py`) or custom formula `value × (1 if unit=="hours" else 24)`; update `apply_runtime_settings()` to accept and store all three cadence fields; retain `get_effective_admin_doc_retention_days()` as a deprecated alias; update `persist_infra_credentials()` to promote cadence globals for cross-request availability

---

## Phase 3: US1 — Guest Auto-Cleanup

**Story goal**: Previous-session guest documents are pruned automatically on first document list load of a new session. The list reflects the cleaned state; an info message shows if docs were removed.

**Independent test criteria**: Upload a doc as guest session A; call `GET /api/documents/` as guest session B; the doc is absent and the response contains `pruned_previous_session_count > 0`.

- [ ] T006 [US1] Write unit tests in `backend/tests/unit/test_cleanup.py` for `_guest_session_filter`: verify it includes docs with `owner_role="guest"` and `owner_session != current`; verify it excludes admin docs, current-session guest docs, and docs with missing session; test empty document list → empty `CleanupResult`
- [ ] T007 [US1] Write unit tests in `backend/tests/unit/test_cleanup.py` for `CleanupService.sweep_guest`: mock `get_all_documents()` with admin doc + current-session guest doc + two previous-session guest docs; assert `_cleanup_document_storage` called exactly twice (once per previous-session doc); assert `CleanupResult` fields `trigger="session_start"`, `scope="guest"`, `deleted_count=2`, `force_mode=False`; assert `_last_cleanup_result` updated
- [ ] T008 [P] [US1] Write unit test in `frontend/tests/unit/DocumentList.test.tsx` for guest session-pruned info banner: mock `getDocuments()` returning `{documents: [], pruned_previous_session_count: 2}`; assert info banner "Previous session documents have been cleared." renders; assert banner is removed from DOM after 5 000 ms (use `vi.useFakeTimers()`)
- [ ] T009 [US1] Extend `backend/app/api/documents.py` `GET /api/documents/` handler: after cookie restore, if user is guest call `CleanupService().sweep_guest(user.session_id)` in a `BackgroundTasks`; add `pruned_previous_session_count: int = 0` field to `DocumentListResponse` Pydantic model; populate it from the cleanup result's `deleted_count` before returning (since `BackgroundTasks` runs after response, capture the count synchronously before handing off); import `CleanupService` from `app.rag.cleanup`
- [ ] T010 [P] [US1] Add guest session-pruned info banner to `frontend/src/components/DocumentList.tsx`: when `response.pruned_previous_session_count > 0` show a blue dismissible `<div>` with "Previous session documents have been cleared."; use `useEffect` + `setTimeout(5000)` to auto-dismiss; render only for guest users (check `authStore`)

---

## Phase 4: US2 — Admin Manual Cleanup + Cadence Configuration

**Story goal**: Admin triggers background cleanup from Settings. Cadence dropdown sets the retention age. CleanupResultCard shows deleted files, cadence used, and any errors.

**Independent test criteria**: `POST /api/documents/cleanup` returns `CleanupResult` with `scope="admin"`, `trigger="manual"`, correct `cadence`; `GET /api/documents/cleanup/status` returns the same cached result.

- [ ] T011 [US2] Write unit tests in `backend/tests/unit/test_cleanup.py` for `CleanupService.sweep_admin`: mock `get_all_documents()` with admin docs at ages 10 h, 200 h, 800 h; test monthly cadence deletes only the 800 h doc; test weekly (168 h) deletes 800 h and 200 h docs; test custom `14 days (336 h)` deletes only 800 h doc; test `force=True` deletes all three regardless of age; assert `CleanupResult.force_mode` matches `force` arg; assert partial file-store error captured in `errors` without aborting sweep; assert guest docs are never selected regardless of age
- [ ] T012 [P] [US2] Write unit tests in `backend/tests/unit/test_documents_cleanup.py` for cleanup endpoints: mock `CleanupService.sweep_admin()` and `get_current_user` returning admin; assert `POST /cleanup` → 200 + `CleanupResult` schema; assert `GET /cleanup/status` → `{has_result: true, result: {...}}`; assert guest JWT → 403; assert `POST /cleanup` third call within one minute → 429; assert `restore_runtime_settings_from_cookie` is called on both endpoints
- [ ] T013 [US2] Add `POST /api/documents/cleanup` and `GET /api/documents/cleanup/status` to `backend/app/api/documents.py`: define `CleanupRequest(force: bool = False)` Pydantic model; `POST` requires `require_full_access`, `@limiter.limit("2/minute")`; calls `CleanupService().sweep_admin(force=body.force)` and stores result in `cleanup._last_cleanup_result`; returns `CleanupResult`; `GET /status` requires `require_full_access`; returns `CleanupStatusResponse(has_result=bool(_last_cleanup_result), result=_last_cleanup_result)`; both endpoints call `restore_runtime_settings_from_cookie(request, _user)` and `audit_event("document_cleanup", ...)`
- [ ] T014 [P] [US2] Extend `SettingsUpdateRequest` in `backend/app/api/settings.py`: add `admin_cleanup_cadence: str | None`, `admin_cleanup_custom_value: int | None`, `admin_cleanup_custom_unit: str | None`; add bleach sanitisation for cadence and unit strings; add validation: cadence must be in `{"hourly","daily","weekly","biweekly","monthly","custom"}`; custom_value range 1–8760; custom_unit must be `"hours"` or `"days"` if provided
- [ ] T015 [P] [US2] Extend `SettingsResponse` in `backend/app/api/settings.py`: add `admin_cleanup_cadence: str`, `admin_cleanup_custom_value: int | None`, `admin_cleanup_custom_unit: str`, `admin_cleanup_retention_hours: int`; update `_build_response()` to populate from `get_effective_cleanup_retention_hours()` and the current cadence globals
- [ ] T016 [P] [US2] Update `POST /api/settings` handler to pass cadence fields to `apply_runtime_settings()` when role is admin; update `persist_infra_credentials()` in `backend/app/runtime/settings_store.py` to persist cadence globals so BackgroundTask sweep uses current cadence
- [ ] T017 [US2] Add Document Retention section to `frontend/src/components/SettingsModal.tsx` (admin-only, rendered below Ragas section): cadence `<select>` with options Hourly/Daily/Weekly/Bi-weekly/Monthly/Custom; when cadence = `"custom"` reveal `<input type="number" min=1 max=8760>` and `<select>` for Hours/Days unit; live count badge `"{count} / {limit}"` with amber Tailwind classes when `admin_docs_near_limit`; `handleRunCleanup` async function calling `triggerCleanup(false)`; `CleanupResultCard` component showing trigger badge (Manual/Session start), mode badge (Force/Normal), scope badge (Admin/Guest), cadence label, deleted count, deleted filenames `<ul>`, errors list; button disabled and shows spinner while `cleanupRunning` state is true
- [ ] T018 [P] [US2] Write unit tests in `frontend/tests/unit/SettingsModal.test.tsx` for Document Retention section: assert section absent for guest user; assert cadence `<select>` renders "Monthly" selected by default; assert custom number+unit inputs hidden until "Custom" selected; mock `triggerCleanup(false)` returning a valid `CleanupResult`; assert CleanupResultCard renders with correct deleted count and cadence string after button click; assert button disabled during in-flight request; assert amber styling on count badge when `admin_docs_near_limit=true`

---

## Phase 5: US3 — Upload-Limit Warning + Force Mode

**Story goal**: When admin doc count ≥ 80% of limit, an amber banner appears and the cleanup button becomes a force-mode trigger that deletes all admin docs regardless of age.

**Independent test criteria**: `GET /api/settings` returns `admin_docs_near_limit=true` when count ≥ 80% of limit; `POST /api/documents/cleanup` with `force=true` deletes all admin docs; frontend shows amber banner and force-mode button.

- [ ] T019 [US3] Write unit tests in `backend/tests/unit/test_cleanup.py` for force mode: mock docs all uploaded within the last 1 h; normal monthly sweep → `deleted_count=0`; force sweep → all admin docs deleted; assert `CleanupResult.force_mode=True`, `retention_hours=None`
- [ ] T020 [P] [US3] Write unit test in `backend/tests/unit/test_documents_cleanup.py` for force request: POST `/cleanup` body `{"force": true}`; mock `sweep_admin(force=True)` returning result with `force_mode=True`; assert response `force_mode=True`
- [ ] T021 [P] [US3] Write unit test in `frontend/tests/unit/DocumentList.test.tsx` for amber banner: mock settings `admin_docs_near_limit=true`, `admin_doc_count=85`, `admin_doc_limit=100`; assert amber banner text contains "85/100"; assert "Go to Settings →" link present; assert banner dismissed and hidden after close button click (sessionStorage key set)
- [ ] T022 [US3] Add `admin_doc_count`, `admin_doc_limit`, `admin_docs_near_limit` to `backend/app/api/settings.py` `_build_response()`: call `get_all_documents()`, count unique `source` values where `owner_role=="admin"`; cache the count in the existing doc-list LRU to avoid repeated full scans; `admin_doc_limit = get_settings().admin_max_indexed_documents`; `admin_docs_near_limit = count >= limit * 0.8`
- [ ] T023 [P] [US3] Add `admin_docs_near_limit: bool` to `DocumentMetadataResponse` in `backend/app/api/documents.py` and populate it in `GET /api/documents/metadata` handler using the same LRU-cached count
- [ ] T024 [P] [US3] Hook near-limit detection into `POST /api/documents/upload` in `backend/app/api/documents.py`: after successful indexing when user is admin, recompute count; if `admin_docs_near_limit` just became true and module-level `_near_limit_notified_at` is `0` or more than `NOTIFICATION_DEDUP_SECONDS` ago, enqueue `send_limit_warning(count, limit)` in `BackgroundTasks`; guard with `if get_settings().notification_enabled`
- [ ] T025 [US3] Add amber near-limit banner to `frontend/src/components/DocumentList.tsx` (admin-only): read `admin_docs_near_limit`, `admin_doc_count`, `admin_doc_limit` from the settings API response (fetched on mount); render persistent amber banner "You have {count}/{limit} documents indexed. Consider running cleanup." with "Go to Settings →" anchor `href="#document-retention"`; dismiss via ✕ button writing `sessionStorage.setItem("doc_limit_banner_dismissed", "1")`; add amber `●` dot on Settings gear icon in `ChatToolbar.tsx` or `DocumentList.tsx` header when `admin_docs_near_limit`
- [ ] T026 [P] [US3] Update cleanup button in `frontend/src/components/SettingsModal.tsx` for force mode: when `settings.admin_docs_near_limit` is true change button text to "Force cleanup (limit reached)" and apply amber Tailwind classes; pass `force=true` to `triggerCleanup()`; CleanupResultCard shows `Force` badge in amber when `result.force_mode=true`, otherwise `Normal` badge in green

---

## Phase 6: US4 — Zero-Cost Notifications

**Story goal**: Admin receives email (SMTP) and/or mobile push (ntfy.sh) when doc limit is approaching. Both channels are off by default, configurable in Settings, and unit-tested with mocks.

**Independent test criteria**: `POST /api/notifications/test` returns `{email_sent, ntfy_sent, errors}` with mocked channels; unit tests confirm no real network calls; notification section visible and saveable in SettingsModal.

- [ ] T027 [US4] Write unit tests in `backend/tests/unit/test_notifications.py` for `send_limit_warning`: patch `smtplib.SMTP` as context manager; with SMTP config set assert `starttls()`, `login()`, `sendmail()` called; message body contains count/limit but not SMTP password; with empty SMTP config assert no `SMTP()` instantiation; patch `httpx.AsyncClient.post`; with ntfy topic set assert POST to `https://ntfy.sh/{topic}` with title/message fields; with empty topic assert httpx not called; test deduplication: second call within `NOTIFICATION_DEDUP_SECONDS` is a no-op
- [ ] T028 [P] [US4] Write unit test in `backend/tests/unit/test_notifications.py` for `POST /api/notifications/test` endpoint: mock `send_test_notification()` returning `{email_sent: True, ntfy_sent: True, errors: []}`; assert 200; test 422 when `notification_enabled=False` and no channels configured; test guest → 403
- [ ] T029 [US4] Implement `backend/app/core/notifications.py`: `NOTIFICATION_DEDUP_SECONDS = 86400`; module-level `_last_notified_at: float = 0.0`; `async def send_limit_warning(doc_count: int, doc_limit: int) -> None` checks master switch + dedup timestamp then fires SMTP in `asyncio.to_thread(_send_smtp, ...)` and ntfy via `httpx.AsyncClient().post(url, headers=..., data=...)` independently (errors logged via structlog, never raised); `async def send_test_notification() -> dict` bypasses dedup; `def _send_smtp(host, port, user, password, to_email, count, limit)` helper using `smtplib.SMTP` STARTTLS; password excluded from all log calls
- [ ] T030 [P] [US4] Create `backend/app/api/notifications.py` router: `POST /test` endpoint requires `require_full_access`, calls `await send_test_notification()`; returns `{email_sent: bool, ntfy_sent: bool, errors: list[str]}`; raises `HTTPException(422)` when no notification channels configured; register in `backend/app/main.py` under prefix `/api/notifications`
- [ ] T031 [P] [US4] Add notification settings fields to `SettingsUpdateRequest` and `SettingsResponse` in `backend/app/api/settings.py`: accept `notification_enabled: bool | None`, `notification_email: str | None` (bleach-sanitised), `notification_ntfy_topic: str | None` (alphanumeric + hyphens pattern); return masked values in response (`notification_email` masked as `o**@example.com`, `notification_ntfy_topic` masked as first 4 chars + `***`); pass to `apply_runtime_settings()` and `persist_infra_credentials()`
- [ ] T032 [P] [US4] Add Notifications section to `frontend/src/components/SettingsModal.tsx` (admin-only, below Document Retention): toggle `notification_enabled`; email `<input type="email">` and ntfy topic `<input type="text">` inputs (disabled when toggle off); "Send test notification" `<button>` calling `sendTestNotification()` then showing inline success/error toast via the existing `toast` helper; inputs show masked placeholder values from settings response
- [ ] T033 [P] [US4] Write unit tests in `frontend/tests/unit/SettingsModal.test.tsx` for notifications section: assert section hidden for guest; assert inputs disabled when toggle off; mock `sendTestNotification()` success → assert success toast; mock failure → assert error toast; assert notification fields included in `PUT /api/settings` payload when saving

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T034 Write integration test `backend/tests/integration/test_documents_cleanup_integration.py` using `TestClient`: upload two admin documents; patch their `uploaded_at` metadata to be > 720 h in the past; call `POST /api/documents/cleanup`; assert `GET /api/documents/` returns empty list; test guest cleanup isolation: upload as guest session A; call `GET /api/documents/` as guest session B (new `session_id`); assert session A doc absent
- [ ] T035 [P] Update `docs/api/API.md` with new endpoints: `POST /api/documents/cleanup` (CleanupRequest → CleanupResult), `GET /api/documents/cleanup/status` (CleanupStatusResponse), `POST /api/notifications/test`; update `SettingsResponse` table with all new cadence, count, and notification fields
- [ ] T036 [P] Update `backend/.env.example` with all new env vars: `ADMIN_CLEANUP_CADENCE`, `ADMIN_CLEANUP_CUSTOM_VALUE`, `ADMIN_CLEANUP_CUSTOM_UNIT`, `ADMIN_MAX_INDEXED_DOCUMENTS`, `NOTIFICATION_ENABLED`, `NOTIFICATION_EMAIL`, `NOTIFICATION_SMTP_HOST`, `NOTIFICATION_SMTP_PORT`, `NOTIFICATION_SMTP_USER`, `NOTIFICATION_SMTP_PASSWORD`, `NOTIFICATION_NTFY_TOPIC` — each with inline comment and example value
- [ ] T037 [P] Update `README.md` env vars table and `docs/deployment/DEPLOY-LOCAL.md` with new cleanup and notification variables and their defaults
- [ ] T038 [P] Update `docs/security/SECURITY.md`: document cleanup isolation guarantee (admin/guest filter disjointness by `owner_role`), SMTP password handling (env-only, never logged or returned), ntfy.sh topic treated as a shared secret (use long random slug), rate limit on cleanup endpoint (OWASP A04)
- [ ] T039 Run `pytest tests/unit/ tests/integration/ --cov=app --cov-report=term-missing` in `backend/`; verify coverage ≥ 98% on `app/rag/cleanup.py`, `app/core/notifications.py`, and the new endpoints in `app/api/documents.py`; diagnose and fix any gaps
- [ ] T040 Run `npm test` in `frontend/`; confirm all tests pass including new `DocumentList.test.tsx` suites and updated `SettingsModal.test.tsx`; fix any type errors from new `CleanupResult` / `SettingsResponse` fields

---

## Parallel Execution Plan

| Sprint | Tasks | Notes |
|--------|-------|-------|
| 1 | T001, T002, T003 | All parallel — different files |
| 2 | T004, T005 | Parallel — different files |
| 3a | T006 → T007 → T009 → T010 | Guest stream (sequential within) |
| 3b | T011 → T012 → T013 → T014 → T015 → T016 → T017 → T018 | Admin stream (parallel with 3a) |
| 4 | T019, T020, T021 → T022 → T023, T024 → T025, T026 | US3 |
| 5 | T027, T028 → T029 → T030, T031, T032, T033 | US4 |
| 6 | T034 → T035, T036, T037, T038 → T039 → T040 | Polish |

---

## Task Count Summary

| Phase | Tasks | Parallelisable |
|-------|-------|----------------|
| Phase 1 — Setup | 3 | 2 |
| Phase 2 — Foundational | 2 | 1 |
| Phase 3 — US1 Guest auto-cleanup | 5 | 2 |
| Phase 4 — US2 Admin cleanup + cadence | 8 | 5 |
| Phase 5 — US3 Limit warning + force | 8 | 5 |
| Phase 6 — US4 Notifications | 7 | 5 |
| Phase 7 — Polish | 7 | 4 |
| **Total** | **40** | **24** |

**MVP scope (Phases 1–4)**: 18 tasks — delivers guest auto-cleanup + admin manual cleanup with full cadence configuration.

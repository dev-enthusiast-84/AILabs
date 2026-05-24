# Feature Specification: Document Cleanup

**Feature Branch**: `012-document-cleanup`
**Created**: 2026-05-24
**Status**: Draft
**Input**: User description: "Document Cleanup — Admin manual trigger with cadence presets (hourly/daily/weekly/biweekly/monthly/custom, default 30 days), guest auto-cleanup on new session, upload-limit warning with force mode when limit hit, zero-cost email and push notifications (SMTP + ntfy.sh), dual-store cleanup (vector + file store). Admin configures cadence and notifications via Settings UI. Manual vs auto delete clearly shown. No cross-role deletion between admin and guest documents."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Guest Session Auto-Cleanup (Priority: P1)

A guest user starts a fresh session and expects to begin with a clean slate — their uploaded documents from previous sessions should be automatically removed without any manual action.

**Why this priority**: Guest sessions are ephemeral by design. Leaving previous-session documents in the index creates stale, irrelevant search results for the new session and wastes storage. This is the most critical baseline behaviour for guest users.

**Independent Test**: A guest uploads a document, ends their session, and a new guest session begins. The document list in the new session is empty and a message confirms that previous session documents have been cleared.

**Acceptance Scenarios**:

1. **Given** a guest user uploaded one or more documents in a previous session, **When** the same or a different guest user opens the document list in a new session, **Then** the previous session's documents are absent from the list.
2. **Given** previous-session guest documents were removed, **When** the document list loads, **Then** a brief information message "Previous session documents have been cleared." is shown and automatically dismissed after a few seconds.
3. **Given** a guest user has no prior uploaded documents, **When** a new guest session begins, **Then** no cleanup message is shown and the document list is simply empty.
4. **Given** a guest's previous-session cleanup runs, **When** the cleanup completes, **Then** only that guest's previous-session documents are removed — admin documents and other guest session documents are untouched.

---

### User Story 2 — Admin Manual Cleanup with Cadence Configuration (Priority: P1)

An admin user wants to control which documents are eligible for deletion by configuring a retention period, then trigger the deletion on demand. The result of the cleanup should be clearly visible in the UI.

**Why this priority**: Admins manage the knowledge base and must be able to recover storage on Vercel's stateless serverless environment where scheduled jobs are not available. Manual trigger with cadence control is the primary admin retention tool.

**Independent Test**: Admin sets cadence to "weekly", uploads documents with dates spanning more than a week, triggers cleanup, and verifies only documents older than 7 days are removed. The result card shows the correct count and filenames.

**Acceptance Scenarios**:

1. **Given** the admin opens Settings, **When** they view the Document Retention section, **Then** they see a cadence selector with options: Hourly, Daily, Weekly, Bi-weekly, Monthly (default), and Custom.
2. **Given** the admin selects "Custom", **When** they enter a number and choose Hours or Days, **Then** the effective retention period is computed and displayed.
3. **Given** the admin clicks "Run cleanup now", **When** cleanup completes, **Then** a result card appears showing: trigger type (Manual), scope (Admin), deleted document count, list of deleted filenames, effective cadence, and any errors encountered.
4. **Given** the cleanup is running, **When** the button is clicked, **Then** it shows a loading state and is disabled until the operation completes.
5. **Given** the admin triggers cleanup with the monthly cadence, **When** sweep completes, **Then** only admin-owned documents older than 30 days are deleted — guest documents are never touched.
6. **Given** the admin saves a new cadence setting, **When** they next trigger cleanup, **Then** the new cadence is applied.

---

### User Story 3 — Upload-Limit Warning and Force Cleanup (Priority: P2)

An admin approaching the indexed document limit receives a visible warning and can perform a force cleanup that removes all their documents immediately, regardless of document age, to free space quickly.

**Why this priority**: Without a warning and a fast recovery path, admins silently hit upload errors. The force mode is the safety valve when the normal cadence would not remove enough documents quickly.

**Independent Test**: With document count at 80% of the configured limit, an amber banner appears. Clicking "Force cleanup (limit reached)" removes all admin documents and the banner disappears.

**Acceptance Scenarios**:

1. **Given** admin document count reaches 80% or more of the configured limit, **When** the Documents tab is opened, **Then** an amber persistent banner shows: "You have {count}/{limit} documents indexed. Consider running cleanup." with a "Go to Settings →" link.
2. **Given** the admin is near the limit, **When** Settings is opened, **Then** the Document Retention section shows the count/limit badge in amber and the cleanup button reads "Force cleanup (limit reached)".
3. **Given** the admin clicks "Force cleanup (limit reached)", **When** the sweep completes, **Then** ALL admin documents are deleted regardless of their age, the result card shows a "Force" mode badge, and the near-limit banner disappears.
4. **Given** the limit banner is shown, **When** the admin dismisses it, **Then** it does not reappear in the same browser session.
5. **Given** admin document count drops below 80% of the limit after cleanup, **When** the document list reloads, **Then** the amber banner and badge are no longer shown.

---

### User Story 4 — Zero-Cost Notifications When Limit Is Approaching (Priority: P3)

An admin wants to be notified via email or mobile push notification when the document limit is approaching, so they can take action before uploads start failing — without incurring any subscription costs.

**Why this priority**: Proactive alerting prevents surprise upload failures. Using only zero-cost channels (SMTP and ntfy.sh) ensures the feature is accessible to all users regardless of budget.

**Independent Test**: Admin configures an email address and SMTP settings in the Notifications section, triggers an upload that crosses the 80% threshold, and receives an email alert. The same test with an ntfy.sh topic delivers a push notification to the admin's mobile app.

**Acceptance Scenarios**:

1. **Given** the admin opens Settings, **When** they view the Notifications section, **Then** they can enable notifications and enter an email address and/or an ntfy.sh topic slug.
2. **Given** an admin upload causes document count to cross the 80% near-limit threshold, **When** notification channels are configured and enabled, **Then** an alert is dispatched to the configured email address and/or ntfy.sh topic.
3. **Given** the 80% threshold was crossed, **When** another upload happens within 24 hours, **Then** no duplicate notification is sent.
4. **Given** the admin clicks "Send test notification", **When** at least one channel is configured, **Then** a test alert is dispatched and the UI confirms which channels succeeded.
5. **Given** no notification channels are configured, **When** the test button is clicked, **Then** the user sees a message indicating no channels are set up.
6. **Given** the SMTP password or ntfy topic is stored, **When** the Settings page is loaded, **Then** the sensitive values are masked in the UI and are never returned in full by the system.

---

### Edge Cases

- A guest uploads a document, the server restarts (new Vercel instance), and the same guest session continues — cleanup should only run when a genuinely new session ID is detected.
- An admin triggers cleanup while another cleanup is still running in the background — rate limiting prevents a second request within one minute.
- A cleanup sweep encounters a file-store error for one document (e.g., Vercel Blob unavailable) — the sweep continues for remaining documents and the error is listed in the result card, not silently dropped.
- The admin sets "Custom" cadence to 1 hour — only documents uploaded more than 1 hour ago are eligible; documents uploaded seconds ago are safe.
- Force cleanup is triggered when there are zero admin documents — the result card shows `deleted_count=0` and no error.
- The email SMTP server is unreachable when a notification fires — the error is logged but the upload operation is not blocked.
- Admin document count is exactly at 80% of the limit (boundary) — the near-limit warning MUST appear at ≥ 80%, not just > 80%.
- A guest session's previous-session cleanup partially fails (some chunks removed, file store unavailable) — the visible document count drops correctly and the file-store error is logged but does not crash the document list load.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST automatically remove a guest user's documents from a previous session when that user starts a new session and opens the document list.
- **FR-002**: Guest auto-cleanup MUST only remove documents belonging to the previous guest session — admin documents and other guest sessions' documents MUST NOT be touched.
- **FR-003**: The system MUST display a brief, auto-dismissing information message when previous-session guest documents have been cleared.
- **FR-004**: Admin users MUST be able to configure a document retention cadence via the Settings UI, choosing from: Hourly, Daily, Weekly, Bi-weekly, Monthly, or Custom.
- **FR-005**: The Custom cadence option MUST allow the admin to specify a numeric value and a unit (Hours or Days).
- **FR-006**: The default retention cadence MUST be Monthly (30 days) unless overridden by environment variable or runtime settings.
- **FR-007**: Admin users MUST be able to trigger a manual document cleanup from the Settings UI at any time.
- **FR-008**: Manual cleanup MUST delete admin-owned documents that are older than the configured cadence threshold, and MUST NOT delete documents that are within the threshold.
- **FR-009**: After every cleanup run, the system MUST display a result card showing: trigger type (Manual or Session start), scope (Admin or Guest), number of documents deleted, list of deleted document names, effective cadence, and any errors.
- **FR-010**: The system MUST remove documents from BOTH the vector index (ChromaDB or Pinecone) AND the file store (local disk or Vercel Blob) in every cleanup operation.
- **FR-011**: When admin document count reaches 80% or more of the configured limit, the system MUST display an amber warning banner in the Documents tab and an amber indicator on the Settings icon.
- **FR-012**: When the admin is at or above the 80% near-limit threshold, the cleanup button MUST switch to "Force cleanup (limit reached)" mode.
- **FR-013**: Force cleanup MUST delete ALL admin-owned documents regardless of their upload date, and the result card MUST clearly indicate force mode was used.
- **FR-014**: The warning banner MUST be dismissible by the admin and MUST NOT reappear in the same browser session once dismissed.
- **FR-015**: Admin users MAY configure email notifications via SMTP settings (host, port, user, password) and a recipient email address.
- **FR-016**: Admin users MAY configure push notifications via an ntfy.sh topic slug.
- **FR-017**: When the near-limit threshold is first crossed on an upload, the system MUST dispatch a notification to all configured channels if notifications are enabled.
- **FR-018**: Notifications MUST NOT be sent more than once per 24-hour period for the same threshold-crossing event.
- **FR-019**: A "Send test notification" action MUST be available to verify notification channel configuration, bypassing the 24-hour deduplication.
- **FR-020**: SMTP passwords and ntfy.sh topic slugs MUST be masked in all UI displays and API responses — they MUST NOT be returned in full.
- **FR-021**: The cleanup endpoint MUST be rate-limited to prevent repeated expensive sweeps within a short period.
- **FR-022**: Admin and guest cleanup operations MUST be structurally isolated — the admin sweep filter MUST only select documents where `owner_role = "admin"` and the guest sweep filter MUST only select documents where `owner_role = "guest"` with a different session identifier.
- **FR-023**: All cleanup operations MUST be logged with: trigger type, scope, document count deleted, cadence used, and any error categories — without logging document content, raw filenames as PII, or credentials.

### Key Entities

- **CleanupResult**: The outcome of a cleanup sweep. Attributes: trigger type (manual or session-start), scope (admin or guest), force mode flag, documents deleted count, documents eligible count, effective retention period, list of deleted display names, list of safe error descriptions, timestamp.
- **CleanupCadence**: The configured retention period that determines document age eligibility. Presets: hourly (1 h), daily (24 h), weekly (7 days), biweekly (14 days), monthly (30 days), custom (user-defined hours or days).
- **NotificationChannel**: A delivery target for limit-approaching alerts. Types: email (SMTP-based) and push (ntfy.sh topic). Attributes: enabled flag, address/topic (masked in UI), last-notified timestamp for deduplication.
- **DocumentOwnership**: Metadata stored with every indexed document. Attributes: owner role (admin/guest), owner session identifier, upload timestamp. Determines eligibility for each cleanup scope.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A guest's previous-session documents are absent from the document list within the first load of a new session — no manual action required.
- **SC-002**: Admin manual cleanup completes a sweep of up to 500 documents and returns a result within 5 seconds from trigger.
- **SC-003**: Zero admin documents are deleted by guest cleanup runs, and zero guest documents are deleted by admin cleanup runs, in all tested scenarios.
- **SC-004**: When the 80% near-limit threshold is crossed, the warning banner appears on the next document list load without requiring a page refresh.
- **SC-005**: Force cleanup removes all admin documents and reduces the document count to zero within the same 5-second performance envelope as normal cleanup.
- **SC-006**: Notification dispatch (email and push) adds no more than 2 seconds of latency to the upload operation that triggers the alert — notifications fire in the background.
- **SC-007**: Sensitive credential values (SMTP password, ntfy topic) are never visible in the Settings UI or returned in full by any API response.
- **SC-008**: The cleanup result card correctly reflects trigger type, force mode, and per-document details for every cleanup run verified in testing.
- **SC-009**: All existing document upload, listing, and deletion tests continue to pass after this feature is implemented.
- **SC-010**: Backend test coverage on the cleanup service module and notification module remains at or above 98%.

---

## Assumptions

- Guest auto-cleanup runs on the first document list request of a new session — no background scheduler is used (compatible with Vercel stateless serverless).
- Admin manual cleanup is the primary mechanism for recurring retention; there is no automatic scheduled sweep for admin documents because the deployment environment does not guarantee persistent background processes.
- The 80% near-limit threshold and the default 100-document limit are configurable via environment variable but have sensible defaults that require no setup for most deployments.
- Push notifications use the free public ntfy.sh service. The admin is responsible for choosing a sufficiently random topic slug to prevent unauthorised subscriptions. Self-hosted ntfy instances are out of scope.
- Email notifications use any SMTP server the admin controls (e.g. Gmail App Password, corporate relay). No email service subscription is required.
- Notification delivery failures do not block or roll back the upload operation that triggered the alert.
- The custom cadence option accepts any value between 1 hour and 365 days; values outside this range are rejected with a clear validation message.
- Document ownership metadata (owner role, session ID, upload timestamp) is already stored with every indexed document and requires no schema migration.
- The cleanup result is cached in memory per server instance; on Vercel, where each function invocation may run on a different instance, the status endpoint may return "no result" after a server cold-start.

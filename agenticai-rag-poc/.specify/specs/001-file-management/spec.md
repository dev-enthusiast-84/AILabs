# Feature Specification: File Management — Delete & Duplicate Prevention

**Feature Branch**: `001-file-management`  
**Created**: 2026-05-14  
**Status**: Draft  
**Input**: User description: "file-management: delete uploaded files with vector DB chunk removal, and reject duplicate file upload with error"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Delete an Uploaded Document (Priority: P1)

An admin user wants to remove a document they uploaded. Clicking the delete button
removes the document from the index list and ensures it no longer appears in query results.

**Why this priority**: Data hygiene is a core admin responsibility; without delete, stale
documents pollute retrieval results permanently.

**Independent Test**: Upload a document, click delete — the document disappears from the list
and a subsequent query about its content returns no relevant results.

**Acceptance Scenarios**:

1. **Given** an admin is logged in and at least one document is indexed, **When** the admin
   clicks the delete (trash) icon next to a document and confirms, **Then** the document is
   removed from the list and all its vector-store chunks are purged.
2. **Given** an admin clicks delete and confirms, **When** the operation succeeds, **Then**
   a success toast is shown ("Removed `<filename>`").
3. **Given** an admin attempts to delete a document that no longer exists (race condition),
   **When** the server returns 404, **Then** a user-friendly error toast is shown.
4. **Given** a guest user views the document list, **When** they inspect the UI, **Then**
   no delete button is visible — guests cannot delete documents.

---

### User Story 2 — Reject Duplicate File Upload (Priority: P1)

A user attempts to upload a file whose name already exists in the index. The system
rejects the upload immediately with a clear error rather than creating duplicate chunks.

**Why this priority**: Without duplicate rejection, re-uploading the same file doubles the
chunk count silently, degrading retrieval quality and wasting token budget.

**Independent Test**: Upload `report.pdf`, then attempt to upload `report.pdf` again — the
second attempt fails with a "file already indexed" error; the chunk count stays the same.

**Acceptance Scenarios**:

1. **Given** a document named `report.pdf` is already indexed, **When** a user uploads a
   file also named `report.pdf`, **Then** the server returns HTTP 409 with a message
   "A document named 'report.pdf' is already indexed. Delete it first to re-upload."
2. **Given** the 409 response is received, **When** the frontend processes it, **Then**
   an error toast shows the server's message to the user.
3. **Given** a document named `report.pdf` exists, **When** a user uploads `Report.PDF`
   (different casing), **Then** the upload is treated as a duplicate (case-insensitive match)
   and is rejected with the same 409 error.
4. **Given** a document is deleted, **When** a user immediately re-uploads a file with the
   same name, **Then** the upload succeeds (no false-positive block).

---

### Edge Cases

- What happens when the file store and vector store are out of sync (file deleted manually)?
  → The upload endpoint checks the vector-store index, not the file store, as the source of truth.
- How does the system handle a duplicate check race condition (two uploads of the same file simultaneously)?
  → The vector-store write is not atomic; a best-effort pre-flight check is sufficient for this use case.
- What if a file is partially uploaded and then fails? → No chunks are written; the duplicate check will pass on retry.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose a `DELETE /api/documents/{filename}` endpoint that removes
  the document and all its associated vector-store chunks atomically.
- **FR-002**: The delete endpoint MUST require full (admin) access; guests MUST receive HTTP 403.
- **FR-003**: The delete endpoint MUST return HTTP 404 when the filename is not found in the index.
- **FR-004**: The delete endpoint MUST return the count of chunks removed in the response body.
- **FR-005**: The `POST /api/documents/upload` endpoint MUST check whether a document with the
  same normalised filename already exists in the vector store before processing.
- **FR-006**: When a duplicate filename is detected, the upload MUST be rejected with HTTP 409
  and an error message: "A document named '{filename}' is already indexed. Delete it first to re-upload."
- **FR-007**: Duplicate detection MUST be case-insensitive (e.g. `Report.PDF` matches `report.pdf`).
- **FR-008**: The frontend document list MUST show a delete button only to admin users; guests see no delete control.
- **FR-009**: After a successful delete the frontend MUST remove the item from the list without
  requiring a full page refresh.
- **FR-010**: The frontend upload form MUST surface the 409 duplicate error as a visible toast
  notification with the server's error message.

### Key Entities

- **Document**: A file indexed into the system, identified by its normalised filename. Has one or more associated vector-store chunks keyed by `source` metadata.
- **Chunk**: A text segment stored in the vector store with `source`, `chunk_index`, and page-content fields.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Deleting a document removes 100% of its chunks from the vector store (zero orphaned chunks after delete).
- **SC-002**: Attempting to re-upload an existing file name returns an error within the same response time as a normal upload rejection (under 500 ms).
- **SC-003**: 100% of unit and integration tests for the delete and duplicate-check paths pass before merge.
- **SC-004**: Guests cannot trigger a delete under any circumstance — HTTP 403 is returned for any guest delete attempt.
- **SC-005**: After a delete the document no longer appears in list responses or query results.

## Assumptions

- The backend `DELETE /{filename}` endpoint and frontend delete button already exist in the codebase; this spec governs their completeness and the addition of duplicate rejection.
- The vector store `list_document_sources()` function is the authoritative source for "which files are indexed" — the duplicate check calls this function.
- Filename normalisation means lowercase + strip leading/trailing whitespace; the validated safe name from `validate_filename()` is the key used for both duplicate detection and deletion.
- Re-upload after delete is a valid workflow and must not be blocked.
- Bulk delete (multiple files at once) is out of scope for this iteration.

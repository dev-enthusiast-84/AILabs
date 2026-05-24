# Feature Specification: Document Management

**Feature Branch**: `brownfield/documents`
**Created**: 2026-05-04
**Status**: Brownfield (describes current production behaviour)
**Input**: Existing implementation in `backend/app/api/documents.py`

---

> **Brownfield notice**: This spec documents what the system **currently does**. It is
> derived directly from `backend/app/api/documents.py`, `backend/app/config.py`,
> `backend/app/guardrails/safety.py`, and `frontend/src/types/index.ts`.
> No new functionality is described here.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Admin Document Upload (Priority: P1)

An admin user uploads a document (PDF, TXT, CSV, or XLSX) to have it split into chunks and
indexed in ChromaDB so that subsequent RAG queries can retrieve relevant content.

**Why this priority**: Document ingestion is the prerequisite for all RAG query value. No
uploaded documents means no answers.

**Independent Test**: Authenticate as admin, upload a valid TXT file under 20 MB, and verify
the response contains `filename`, `chunks_indexed > 0`, and `message: "Document indexed
successfully."`. Then call `GET /api/documents/` and confirm the filename appears in the
list.

**Acceptance Scenarios**:

1. **Given** a valid admin JWT and a well-formed TXT file under 20 MB, **When** a client
   sends `POST /api/documents/upload` (multipart/form-data, field name `file`), **Then** the
   server returns HTTP 201 with a JSON body containing `filename` (sanitized), `chunks_indexed`
   (integer >= 1), and `message: "Document indexed successfully."`.

2. **Given** a valid admin JWT and a PDF file whose first 4 bytes are `%PDF`, **When** the
   file is uploaded, **Then** the server ingests and indexes it successfully (HTTP 201).

3. **Given** a valid admin JWT and a well-formed XLSX file (ZIP magic bytes `PK\x03\x04`)
   or XLS file (OLE2 magic bytes `\xd0\xcf\x11\xe0`), **When** the file is uploaded,
   **Then** the server ingests and indexes it (HTTP 201).

4. **Given** a valid admin JWT and a CSV file under 20 MB, **When** the file is uploaded,
   **Then** the server ingests and indexes it (HTTP 201).

5. **Given** a file that was previously uploaded under the same filename, **When** it is
   uploaded again, **Then** the server re-indexes it (all chunks are added again — no
   deduplication) and returns HTTP 201 with the new chunk count.

6. **Given** a valid admin JWT and a file whose size exceeds 20 MB (or 4 MB on Vercel),
   **When** the file is uploaded, **Then** the server returns HTTP 413 with
   `detail: "File exceeds the <N> MB limit."`.

7. **Given** a valid admin JWT and a zero-byte file, **When** it is uploaded, **Then** the
   server returns HTTP 422 with `detail: "File is empty."`.

---

### User Story 2 - Guest Document Upload (Priority: P2)

A guest user may upload documents but is subject to a stricter file-size cap (3 MB) to
prevent resource abuse. The same safety checks apply.

**Why this priority**: Guest upload enables lightweight demos and self-service testing
without requiring an admin account. The tighter size cap is an OWASP A04 control.

**Independent Test**: Obtain a guest JWT, upload a TXT file under 3 MB, and verify HTTP 201.
Then upload a TXT file over 3 MB and verify HTTP 413.

**Acceptance Scenarios**:

1. **Given** a valid guest JWT and a TXT file under 3 MB, **When** the file is uploaded,
   **Then** the server returns HTTP 201 with a populated `UploadResponse`.

2. **Given** a valid guest JWT and a file whose size exceeds 3 MB (even if under 20 MB),
   **When** the file is uploaded, **Then** the server returns HTTP 413 with
   `detail: "File exceeds the 3 MB limit."`.

3. **Given** a valid guest JWT and a TXT file containing null bytes in the first 512 bytes,
   **When** the file is uploaded, **Then** the server returns HTTP 422 with
   `detail: "Binary content detected in a text file."`.

4. **Given** a valid guest JWT and a TXT or CSV file whose first 2048 bytes contain
   `<script` or `javascript:`, **When** the file is uploaded, **Then** the server returns
   HTTP 422 with `detail: "Potentially unsafe script content detected."`.

---

### User Story 3 - List Indexed Documents (Priority: P1)

Any authenticated user (admin or guest) can retrieve the list of document sources currently
indexed in ChromaDB, along with the total count.

**Why this priority**: The document list drives the UI document panel and is required for
users to know what knowledge is available for querying.

**Independent Test**: Upload two documents as admin, then call `GET /api/documents/` with
an admin token and a guest token separately; both must return the same list with `count: 2`.

**Acceptance Scenarios**:

1. **Given** one or more documents have been indexed and a valid JWT (any role), **When** a
   client sends `GET /api/documents/`, **Then** the server returns HTTP 200 with a JSON body
   containing `documents` (array of filename strings) and `count` (integer equal to the
   array length).

2. **Given** no documents have been indexed and a valid JWT, **When** a client calls
   `GET /api/documents/`, **Then** the server returns HTTP 200 with
   `{"documents": [], "count": 0}`.

3. **Given** no `Authorization` header, **When** `GET /api/documents/` is called, **Then**
   the server returns HTTP 403 (HTTPBearer rejects missing credentials).

---

### User Story 4 - Retrieve Document Chunks (Priority: P2)

Any authenticated user can inspect the individual text chunks that were indexed for a
specific document filename.

**Why this priority**: Chunk inspection is useful for debugging ingestion quality and
verifying that a document was correctly processed.

**Independent Test**: Upload a document as admin, then call
`GET /api/documents/{filename}/chunks` with both an admin and a guest token; verify the
response contains non-empty `chunks` and a matching `total_chunks` count.

**Acceptance Scenarios**:

1. **Given** a document has been indexed and a valid JWT (any role), **When** a client
   calls `GET /api/documents/{filename}/chunks`, **Then** the server returns HTTP 200 with
   a JSON body containing `filename` (the sanitized name), `chunks` (array of strings), and
   `total_chunks` (integer equal to the array length).

2. **Given** a filename that has not been indexed, **When** the chunks endpoint is called,
   **Then** the server returns HTTP 404 with
   `detail: "Document '<filename>' not found."`.

3. **Given** a filename containing path traversal sequences (e.g. `../etc/passwd`),
   **When** the chunks endpoint is called, **Then** `validate_filename()` sanitizes or
   rejects the name before any ChromaDB query, returning HTTP 422.

4. **Given** no `Authorization` header, **When** `GET /api/documents/{filename}/chunks`
   is called, **Then** the server returns HTTP 403.

---

### User Story 5 - Delete a Document (Priority: P2)

An admin user removes a document and all its associated chunks from the ChromaDB index.
Guest users are blocked.

**Why this priority**: Deletion is a destructive write operation that must be restricted to
admins to protect the integrity of the shared knowledge base.

**Independent Test**: Upload a document as admin, delete it with an admin token, verify
HTTP 200 with `chunks_removed > 0`, then confirm the document no longer appears in the
list or chunks endpoints.

**Acceptance Scenarios**:

1. **Given** a valid admin JWT and an indexed document, **When** a client sends
   `DELETE /api/documents/{filename}`, **Then** the server returns HTTP 200 with a JSON
   body containing `filename` (sanitized) and `chunks_removed` (integer > 0 — the count of
   ChromaDB chunks removed).

2. **Given** a valid guest JWT, **When** `DELETE /api/documents/{filename}` is called,
   **Then** the server returns HTTP 403 with
   `detail: "This action requires a full account. Please sign in."` — no deletion occurs.

3. **Given** an admin JWT and a filename that does not exist in the index, **When** the
   delete endpoint is called, **Then** the server returns HTTP 404 with
   `detail: "Document '<filename>' not found."`.

4. **Given** a filename containing path traversal sequences, **When** the delete endpoint
   is called, **Then** `validate_filename()` sanitizes or rejects the name before any
   ChromaDB operation.

---

### Edge Cases

- What happens when an unsupported file extension is uploaded? `ingest_document()` raises
  `ValueError` (unrecognised format), which the upload handler catches and returns as
  HTTP 422 with the error detail.
- What happens when a PDF file is uploaded but its first 4 bytes are not `%PDF`?
  `_check_content_safety()` raises `ValueError("File content does not match the declared
  .pdf format.")`, returned as HTTP 422.
- What happens when a file with a Windows PE header (`MZ`) is uploaded regardless of
  extension? `_check_content_safety()` raises `ValueError("Executable content detected.
  Upload rejected.")`, returned as HTTP 422.
- What happens when an XLSX file is uploaded but the magic bytes match an ELF binary?
  The executable signature check runs first and rejects with HTTP 422.
- What happens when no documents have been indexed and delete is called? `delete_document()`
  returns 0; the endpoint raises HTTP 404.
- What happens when an upload is retried with the same filename? ChromaDB receives
  `add_documents()` again — all new chunks are added without deduplication. The `chunks_indexed`
  value in the response reflects the newly added batch only.
- What happens on Vercel when an admin uploads a file over 4 MB but under 20 MB? The
  `effective_max_upload_size_mb` property caps the limit at 4 MB; the response is HTTP 413
  with `detail: "File exceeds the 4 MB limit."`.
- What happens when the filename contains only a dot or starts with a dot? `validate_filename()`
  handles these edge cases; invalid names are rejected with HTTP 422.
- What happens when a CSV file's first 512 bytes contain a null byte? HTTP 422 with
  `detail: "Binary content detected in a text file."`.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST expose `POST /api/documents/upload` (multipart/form-data)
  requiring a valid JWT (any role). The endpoint MUST return HTTP 201 on success with
  `UploadResponse` containing `filename`, `chunks_indexed`, and `message`.
- **FR-002**: The upload endpoint MUST enforce per-role file size limits:
  - Admin (standard): 20 MB (`max_upload_size_mb`, configurable via `MAX_UPLOAD_SIZE_MB`).
  - Admin (Vercel): 4 MB (capped by `effective_max_upload_size_mb`).
  - Guest: 3 MB (`guest_max_upload_size_mb`, configurable via `GUEST_MAX_UPLOAD_SIZE_MB`).
  - Exceeding the limit MUST return HTTP 413.
- **FR-003**: The upload endpoint MUST reject empty files with HTTP 422.
- **FR-004**: The system MUST accept only PDF, TXT, CSV, and XLSX file types for indexing.
  Unsupported types MUST return HTTP 422.
- **FR-005**: The upload endpoint MUST perform content safety validation via
  `_check_content_safety()` before any ingestion:
  - Files with executable magic bytes (`MZ`, `\x7fELF`, Mach-O signatures) MUST be rejected
    with HTTP 422.
  - PDF/XLSX/XLS files MUST have matching magic bytes; mismatches MUST be rejected.
  - TXT/CSV files MUST NOT contain null bytes in the first 512 bytes.
  - TXT/CSV files MUST NOT contain `<script` or `javascript:` in the first 2048 bytes.
- **FR-006**: The upload endpoint MUST sanitize filenames via `validate_filename()` before
  any storage or ingestion operation (path traversal prevention, OWASP A01).
- **FR-007**: The system MUST expose `GET /api/documents/` requiring any valid JWT.
  The endpoint MUST return HTTP 200 with `DocumentListResponse` containing `documents`
  (array of strings) and `count` (integer).
- **FR-008**: The system MUST expose `GET /api/documents/{filename}/chunks` requiring any
  valid JWT. The endpoint MUST return HTTP 200 with `DocumentChunksResponse` containing
  `filename`, `chunks` (array of strings), and `total_chunks` (integer). If the document
  is not found, the endpoint MUST return HTTP 404.
- **FR-009**: The system MUST expose `DELETE /api/documents/{filename}` requiring a
  `require_full_access` JWT (admin only). Guest tokens MUST receive HTTP 403.
- **FR-010**: The delete endpoint MUST return HTTP 200 with `DeleteResponse` containing
  `filename` and `chunks_removed` (integer) when the document exists. If the document is
  not found, the endpoint MUST return HTTP 404.
- **FR-011**: All filename parameters in URL paths MUST be passed through `validate_filename()`
  before use (chunks and delete endpoints).
- **FR-012**: The system MUST use ChromaDB as the backing vector store for document chunks.
  Functions `add_documents`, `delete_document`, `get_document_chunks`, and
  `list_document_sources` from `app.rag.vector_store` are the only permitted data access
  layer.

### Key Entities

- **UploadResponse**: Returned on successful upload. Fields: `filename` (str, sanitized),
  `chunks_indexed` (int, number of ChromaDB documents added), `message` (str, always
  `"Document indexed successfully."`).
- **DocumentListResponse**: Returned by the list endpoint. Fields: `documents` (list[str],
  unique source names from ChromaDB), `count` (int, length of `documents`).
- **DocumentChunksResponse**: Returned by the chunks endpoint. Fields: `filename` (str),
  `chunks` (list[str], raw text of each chunk), `total_chunks` (int).
- **DeleteResponse**: Returned by the delete endpoint. Fields: `filename` (str),
  `chunks_removed` (int, number of ChromaDB entries deleted).
- **_MAGIC_BYTES map**: Internal constant mapping `"pdf"` → `b"%PDF"`, `"xlsx"` →
  `b"PK\x03\x04"`, `"xls"` → `b"\xd0\xcf\x11\xe0"`.
- **_EXEC_SIGNATURES list**: Internal constant listing known executable file headers
  (`MZ`, `\x7fELF`, `\xfe\xed\xfa`, `\xca\xfe\xba\xbe`) that cause immediate rejection.
- **Chunk**: A unit of text produced by `chunk_text()` (800 characters, 100-character
  overlap). Each chunk is stored in ChromaDB with `metadata.source = filename`.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `POST /api/documents/upload` with a valid file returns HTTP 201 and
  `chunks_indexed >= 1` in every successful invocation.
- **SC-002**: Uploading a file that exceeds the applicable size limit (3 MB for guests,
  20 MB for admins) returns HTTP 413 in 100% of attempts.
- **SC-003**: Uploading a file with an executable magic byte header returns HTTP 422 in
  100% of attempts, regardless of file extension.
- **SC-004**: `DELETE /api/documents/{filename}` with a guest token returns HTTP 403 in
  100% of attempts with the prescribed detail message.
- **SC-005**: `GET /api/documents/` returns the correct `count` equal to `len(documents)`
  in every response.
- **SC-006**: After a successful delete, `GET /api/documents/` no longer includes the
  deleted filename and `GET /api/documents/{filename}/chunks` returns HTTP 404.
- **SC-007**: A TXT or CSV file containing `<script` in the first 2048 bytes is rejected
  with HTTP 422 in 100% of attempts.
- **SC-008**: 100% of the unit and integration test cases in `backend/tests/unit/` and
  `backend/tests/integration/` related to document management pass.

---

## Assumptions

- ChromaDB is the only supported vector store for production. The `VECTOR_STORE_TYPE`
  environment variable may be set to `"memory"` for tests or Vercel deployments; in that
  case, data is not persisted between restarts.
- File deduplication is not implemented at the storage layer. Uploading the same filename
  twice results in additional chunks being appended to the collection. Callers are
  responsible for deleting existing documents before re-uploading if deduplication is needed.
- The `chunks_indexed` value in `UploadResponse` reflects only the chunks added in the
  current upload operation, not the cumulative total for that filename in ChromaDB.
- Chunk size (800 characters) and overlap (100 characters) are global settings from
  `config.py` and apply uniformly to all file types and roles.
- The magic byte check for TXT and CSV files is advisory (null bytes and script markers)
  rather than signature-based, since these are variable text formats.
- Vercel's 4 MB effective upload cap applies to admin users only when `VERCEL` env var is
  set. Guest cap (3 MB) is always enforced regardless of deployment platform.
- Path traversal prevention is delegated entirely to `validate_filename()` in
  `app.guardrails.safety`. The documents router trusts the sanitized name returned by that
  function.
- The `file` field name in the multipart upload form is fixed as `file` (FastAPI
  `File(...)` parameter). No alternative field names are supported.
- The `Authorization: Bearer <token>` scheme is the only supported authentication transport.
  Cookie-based auth is not implemented.
- The Vercel serverless body size limit (~4.5 MB) is the physical constraint behind the
  4 MB admin cap on Vercel. Requests exceeding this limit may be rejected by Vercel's edge
  before reaching the FastAPI handler.

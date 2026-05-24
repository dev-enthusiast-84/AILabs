# API Schemas: Documents

> [← Home](README.md) · [API Reference](api/API.md) · [API Schemas](api/API-SCHEMAS.md)

Schemas for document list, upload, delete, metadata, chunks, and content endpoints.

---

## DocumentListResponse

Returned by `GET /api/documents/`.

| Field | Type | Description |
|-------|------|-------------|
| `documents` | string[] | List of display filenames for indexed documents visible to the caller |
| `count` | integer | Total number of documents in the list |

---

## UploadResponse

Returned by `POST /api/documents/upload` (HTTP 201).

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | Sanitised filename as stored in the index |
| `chunks_indexed` | integer | Number of vector-store chunks created from the document |
| `message` | string | Human-readable confirmation message |

---

## DeleteResponse

Returned by `DELETE /api/documents/{filename}`.

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | Filename that was removed |
| `chunks_removed` | integer | Number of vector-store chunks deleted |

---

## DocumentMetadataItem

Returned in `documents[]` array from `GET /api/documents/metadata` (admin only).

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | Display filename (guest-session prefix stripped for admin docs) |
| `chunk_count` | integer | Number of indexed vector-store chunks for this document |
| `uploaded_at` | string \| null | Unix timestamp string recorded at upload time; `null` if not present |
| `owner_username` | string \| null | Username of the uploader; `null` if not stored |
| `availability` | `"usable"` \| `"stale"` \| `"unknown"` | `usable` — vector chunks and storage present; `stale` — vector entry exists but storage is missing; `unknown` — storage read failed |

---

## DocumentMetadataResponse

Returned by `GET /api/documents/metadata` (admin only).

| Field | Type | Description |
|-------|------|-------------|
| `documents` | DocumentMetadataItem[] | Enriched metadata list (excludes guest-owned documents) |
| `count` | integer | Total number of items returned |

---

## DocumentChunksResponse

Returned by `GET /api/documents/{filename}/chunks`.

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | Document filename |
| `chunks` | string[] | All indexed text chunks in sequence order |
| `total_chunks` | integer | Total number of chunks |

---

## DocumentContentResponse

Returned by `GET /api/documents/{filename}/content`.

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | Document filename |
| `content` | string | Full reconstructed document text with chunk-overlap deduplicated |
| `word_count` | integer | Approximate word count of the reconstructed content |

# Operational Limits
> [← Home](README.md) · [← Deployment](deployment/DEPLOYMENT.md)

Hard limits enforced in the backend. Exceeding any of these results in a 4xx response or a server-side truncation with a logged warning. Values are not runtime-configurable unless an env var is listed.

---

## Voice Export Limits
Limits enforced in `backend/app/api/voice_export.py`.

| Limit | Value | Notes |
|-------|-------|-------|
| Transcript input cap | 12,000 characters | Longer transcripts are truncated before export |
| Audio-synthesis cap | 4,000 characters | Text sent to TTS; remainder is truncated |
| Audio response cap | 10 MB | Max audio bytes returned per request |
| Async job TTL | 900 seconds (15 min) | Jobs expire after this; expired jobs return 410 |
| Artifact TTL | 600 seconds (10 min) | Audio artifact available for download after completion |

### Voice export flow summary
```
POST /api/voice/export
  → transcript truncated to 12,000 chars
  → redaction applied (guardrail engine)
  → TTS text truncated to 4,000 chars
  → audio synthesis (OpenAI TTS)
  → audio capped at 10 MB
  → async job stored with 900 s TTL
  → artifact stored with 600 s TTL
GET /api/voice/export/{job_id}
  → returns 410 if job TTL expired
  → returns audio bytes if artifact TTL not expired
```

---

## Upload and Document Limits
Limits enforced in `backend/app/api/documents.py` and `backend/app/config.py`.

| Limit | Local/Docker | Vercel |
|-------|-------------|--------|
| Admin upload cap | 20 MB | 4 MB (request-safe) |
| Guest upload cap | 3 MB TXT only | 3 MB TXT only |
| Admin document corpus cap | `MAX_INDEXED_DOCUMENTS` (default 10) | Same |
| Per-guest-session document cap | `GUEST_MAX_INDEXED_DOCUMENTS` (default 1) | Same |
| Allowed file types (admin) | PDF, TXT, CSV, XLSX | PDF, TXT, CSV, XLSX |
| Allowed file types (guest) | TXT only | TXT only |

---

## Rate Limits
Limits enforced via `slowapi` in the FastAPI routers.

| Endpoint | Limit | Scope |
|----------|-------|-------|
| `POST /api/auth/login` | 10 requests / min | Per IP |
| `POST /api/auth/guest` | 10 requests / min | Per IP |
| `POST /api/query/` | 10 requests / min | Per IP |
| `POST /api/documents/upload` (admin) | No hard rate limit | Governed by upload cap |
| `POST /api/documents/upload` (guest) | 5 requests / min | Per IP |

---

## LLM and Retrieval Limits
Limits enforced in `backend/app/config.py` and the agent pipeline.

| Limit | Env var | Default | Notes |
|-------|---------|---------|-------|
| Max LLM completion tokens | `MAX_COMPLETION_TOKENS` | 1024 | Hard cap on output tokens per response |
| Max chunk context | `MAX_CHUNK_CONTEXT` | (see config) | Limits total context sent to LLM |
| Top-k retrieval chunks | `RETRIEVER_K` | 4 | Chunks returned by similarity search |

---

## Auth Token Lifetimes

| Token type | Lifetime | Env var |
|------------|----------|---------|
| Admin JWT | 45 minutes | Not configurable |
| Guest JWT | 15 minutes | `GUEST_TOKEN_EXPIRE_MINUTES` |
| Guest settings one-time gate | Single use per JTI | Not configurable |

---

## Storage Limits
| Backend | Scope | Notes |
|---------|-------|-------|
| ChromaDB (local/Docker) | Local filesystem | Bounded only by disk; use `MAX_INDEXED_DOCUMENTS` |
| In-memory vector store | Process lifetime | Tests only; data lost on restart |
| Vercel Blob file store | Object store | Subject to Vercel plan storage quota |
| Pinecone vector store | Managed cloud | Subject to Pinecone plan index quota |

---

## ZIP and Archive Safety
Enforced in `backend/app/rag/scanner.py`.

| Check | Limit | Notes |
|-------|-------|-------|
| ZIP-bomb detection | Expansion ratio threshold | Rejects archives that exceed safe expansion factor |
| ClamAV scan | Per-file | Optional; enabled by setting `CLAMAV_HOST` |
| Stored prompt-injection check | Per-chunk | Regex-based; flags suspicious instruction patterns in uploaded text |

---

## Async Job Store Cleanup

The in-process `VoiceExportJobStore` evicts expired entries lazily on the next status check — there is no background sweep thread. In production at scale, use an external job store (Redis, database) to avoid unbounded memory growth. For the full job lifecycle state transitions, see [Voice Export API Schemas](api/API-SCHEMAS-VOICE.md).

---

## Notes on Limit Enforcement

- All hard limits are enforced server-side and cannot be overridden by client requests.
- Env vars controlling soft limits (e.g. `RETRIEVER_K`, `MAX_COMPLETION_TOKENS`) take effect on restart.
- Limits marked "not configurable" are compile-time constants.

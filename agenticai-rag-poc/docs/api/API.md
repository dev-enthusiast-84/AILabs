# API Reference

> [← Home](README.md)

Interactive docs at `http://localhost:8000/api/docs` (development only).  
For request/response schemas, AgentTrace, and rate limits → [API Schemas & Examples](api/API-SCHEMAS.md).

---

## Access Modes — Guest vs. Admin

| Capability | Guest | Admin |
|------------|:-----:|:-----:|
| **Chat** — query against indexed documents | ✅ | ✅ |
| **List documents** — see what is indexed | ✅ | ✅ |
| **Document metadata** (`GET /api/documents/metadata`) | ❌ 403 | ✅ |
| **Upload TXT** (1 file, max 2 MB) | ✅ | ✅ |
| **Upload PDF / CSV / XLSX / XLS** (up to 20 MB) | ❌ | ✅ |
| **Delete documents** | ❌ 403 | ✅ |
| **Settings — provide OpenAI API key** | ✅ any time | ✅ |
| **Settings — change LLM model** | ✅ once / session | ✅ unlimited |
| **Ragas evaluation scores** | ❌ 403 | ✅ |
| **Manage guardrail rules** | ❌ 403 | ✅ |
| Session duration | 15 min | 45 min |
| Rate limit (queries) | 10 / min | 10 / min |

### Guest Mode

A signed JWT with `role: "guest"` is issued with no credentials required. Click **"Continue as Guest"** on the login page. The token expires after 15 minutes (`GUEST_TOKEN_EXPIRE_MINUTES`).

```bash
# Obtain a guest token
TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/guest | jq -r .access_token)

# Chat — allowed
curl -s -X POST http://localhost:8000/api/query/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the core capabilities of generative AI?"}' | jq .

# Upload TXT — allowed for guests
curl -s -X POST http://localhost:8000/api/documents/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sample.txt"

# Delete — blocked (HTTP 403)
curl -s -X DELETE http://localhost:8000/api/documents/sample.txt \
  -H "Authorization: Bearer $TOKEN"
# → {"detail": "This action requires a full account. Please sign in."}
```

### Admin Credentials

Login with username `admin` and the password printed at server startup.

```bash
grep ADMIN_PASSWORD backend/.env
```

> **Never hardcode the admin password** in scripts or source code.

---

## Endpoints

| Method | Endpoint | Auth | Guest | Description |
|--------|----------|:----:|:-----:|-------------|
| `POST` | `/api/auth/login` | No | — | Obtain admin JWT |
| `POST` | `/api/auth/guest` | No | — | Obtain guest JWT (no credentials) |
| `POST` | `/api/auth/logout` | Bearer | ✅ | Revoke current JWT (adds JTI to blocklist) |
| `GET`  | `/api/auth/me` | Bearer | ✅ | Current user info and role |
| `GET`  | `/api/documents/` | Bearer | ✅ | List indexed document sources |
| `GET`  | `/api/documents/metadata` | Bearer | ❌ 403 | Enriched metadata for all admin documents (chunk count, availability). **Admin only.** |
| `GET`  | `/api/documents/{filename}/chunks` | Bearer | ✅ | All indexed text chunks for a document |
| `GET`  | `/api/documents/{filename}/content` | Bearer | ✅ | Reconstructed full document text |
| `GET`  | `/api/documents/{filename}/file` | Bearer | ✅ | Original uploaded file bytes (correct MIME) |
| `POST` | `/api/documents/upload` | Bearer | ✅ TXT/2MB | Upload + index a document. **409** if filename already indexed. |
| `DELETE` | `/api/documents/{filename}` | Bearer | ❌ 403 | Remove document + all vector-store chunks. **404** if not found. |
| `POST` | `/api/query/` | Bearer | ✅ | Run RAG query (`mode="agentic"` default or `mode="simple"`). **422** for unknown mode. |
| `POST` | `/api/chat/voice/redact` | Bearer | ✅ | Return backend-redacted export transcript without generating audio. |
| `POST` | `/api/chat/voice/export` | Bearer | ✅ | Generate redacted MP3 audio synchronously for small non-production exports, or return **202** deferred job metadata for production/large/deferred exports. |
| `GET` | `/api/chat/voice/export/jobs/{job_id}` | Bearer | ✅ | Poll a deferred voice export job. Succeeded jobs include an in-memory MP3 artifact until expiration. |
| `DELETE` | `/api/chat/voice/export/jobs/{job_id}` | Bearer | ✅ | Cancel a queued/running deferred voice export job and suppress any later artifact. |
| `GET`  | `/api/settings/` | Bearer | ✅ | Active model, masked API key, and pipeline flags (including `ragas_evaluation_enabled`) |
| `POST` | `/api/settings/` | Bearer | ✅ limited | Update API key (any time) or model (once per guest session). `ragas_evaluation_enabled` flag requires admin. |
| `POST` | `/api/settings/ragas-trigger` | Bearer | ❌ 403 | Trigger an async Ragas evaluation run (admin only). Rate-limited to 1 per 5 min per IP. |
| `GET`  | `/api/settings/ragas-scores` | Bearer | ❌ 403 | Last Ragas evaluation scores. **200** with `has_results: false` when no run yet. |
| `GET`  | `/api/guardrails/` | Bearer | ✅ | List all guardrail rules |
| `GET`  | `/api/guardrails/{id}` | Bearer | ✅ | Get a single guardrail rule |
| `POST` | `/api/guardrails/` | Bearer | ❌ 403 | Create a new guardrail rule |
| `PATCH` | `/api/guardrails/{id}` | Bearer | ❌ 403 | Update a guardrail rule |
| `DELETE` | `/api/guardrails/{id}` | Bearer | ❌ 403 | Delete a user-defined rule (built-ins cannot be deleted) |
| `POST` | `/api/guardrails/check` | Bearer | ✅ | Test text against the active rule set |
| `GET`  | `/api/health` | No | — | Health check |

> Guest documents are automatically removed from the index when the guest signs in as an admin during the same browser session.

### Voice Audio Export Jobs

Small non-production audio exports preserve the original synchronous response shape (`audio_base64`, `audio_mime_type`, `audio_format`, `transcript`, `redacted`). Production, explicitly deferred (`defer: true`), and large safe transcripts return `202 Accepted` with `job_id`, `status_url`, `cancel_url`, `expires_at`, `artifact_expires_at`, and a retry policy.

Deferred jobs use an in-memory process-local registry as the no-infrastructure fallback. Artifacts are scoped to the authenticated user/session, retained for 10 minutes, and then status becomes `expired` with no audio payload. This is not a durable queue or signed object-storage URL; deployments that need cross-instance durability should replace the registry with object storage and a real worker queue behind the same typed status contract.

Retry/timeout policy: each OpenAI speech request uses a 30 second timeout. Deferred jobs retry one timeout once after the advertised `retry_after_seconds`; synchronous exports keep the existing fail-fast 504 behavior for compatibility.

# Limitations & Development Challenges

> [← Home](README.md) · [← Project](project/PROJECT.md) · [Operational Limits](deployment/DEPLOY-LIMITS.md)

Architectural decisions, trade-offs, and known limitations. Retrieval and reranking decisions → [Retrieval & Reranking](project/CHALLENGES-RETRIEVAL.md). Hard operational limits → [Operational Limits](deployment/DEPLOY-LIMITS.md). Testing challenges → [Testing Challenges](testing/TESTING-CHALLENGES.md).

---

## Serverless Persistence (Core Challenge)

**Problem:** ChromaDB persists vectors to a local writable filesystem, which works in local dev and Docker Compose. Vercel serverless function instances share no filesystem — `/tmp` is not shared across concurrent instances and is wiped on cold start. A file-backed Chroma store therefore loses data between requests or across horizontal scale-out.

**Solution:** Production Vercel deployments use `VECTOR_STORE_TYPE=pinecone`. Pinecone provides a managed, durable vector layer shared by all function instances. Original uploaded files use `FILE_STORE_TYPE=blob` backed by Vercel Blob object storage. Both are configurable through the Settings UI without a redeploy.

**Remaining constraint:** Vercel's serverless request body limit caps uploads at ~4.5 MB; the backend enforces 4 MB for admin uploads on Vercel vs 20 MB locally. `VECTOR_STORE_TYPE=blob` is retained only as a small demo/fallback option.

---

## Document Format Variability

Each supported format (TXT, PDF, CSV, XLSX/XLS) requires different parsing, encoding handling, empty-content detection, and validation. The ingestion layer normalises all formats into plain text before chunking. Validation at the upload boundary: file type, MIME type, size, zip-bomb expansion ratio, stored prompt injection regex, and optional ClamAV scan.

---

## Agent Orchestration Complexity

The full agentic path has 7 nodes, optional branches (Grader, Reranker), and a retry loop. Mitigations:

- `mode="simple"` bypasses planning, HyDE, Grader, Reranker, and Validator — a single retrieve-generate step ~3× faster.
- Each node is independently configurable (model override, enable/disable) without code changes.
- LangSmith tracing via `LANGCHAIN_TRACING_V2=true` gives per-node visibility.

---

## Safe Configuration and Secrets

Provider credentials must be available at runtime but must not appear in logs, responses, or exported content. Mitigations:

- Production mode ignores env-supplied provider credentials; they must be entered through the Settings UI.
- Startup credential banner suppressed in `APP_ENV=production`.
- API responses use masked sources; raw keys are never returned.
- Settings UI is role-aware: guests configure keys exactly once per session; admins update without restriction.

**Test isolation:** Unit and integration tests run without real credentials using mocks. Live tests (`backend/tests/live/`) require real keys and are excluded from standard CI.

---

## Role and Session Isolation

Guest and admin sessions must not share documents, settings, or corpus state. Enforcement:

- Guest documents tagged with session JTI at index time; admin list/query/delete views filter them out.
- Guest settings stored per-session and expire with the guest JWT (15 min TTL).
- One-time settings gate: once a guest saves credentials, the endpoint rejects further updates.
- JTI blocklist prevents reuse of logged-out tokens (bounded LRU, 10 000 entries).

---

## Additional Design Controls

**Backend redaction as privacy boundary:** Frontend redaction provides UX feedback but is not a security control. Transcript export and voice synthesis both apply backend redaction (guardrail engine) before any data leaves the server. Tests assert sensitive pattern values do not appear in exported transcripts or TTS synthesis input.

**Multilingual retrieval quality:** Language selection is a presentation concern. The query API keeps the user's original question (any language) for embedding and retrieval; language instructions are injected only into the Generator prompt, preserving semantic retrieval quality across language boundaries.

**Voice and browser security:** Vercel production headers allow `Permissions-Policy: microphone=(self)` and disable camera/geolocation. CSP, `X-Content-Type-Options`, `X-Frame-Options`, referrer policy, and HSTS are enforced in production.

---

## Async Voice Export Jobs

The in-process async job store enforces TTL-based expiry (job TTL 900 s, artifact TTL 600 s). Expired entries are evicted lazily on the next status check — no background sweep thread.

**Constraint:** In long-lived processes with high job creation volume, memory grows until access-based eviction catches up. A production system at scale should use an external job store (Redis, database) with a background expiry sweep.

---

## Known Limitations

- **OpenAI dependency:** All embedding and generation require an OpenAI-compatible key; no offline fallback.
- **Vercel upload cap:** Admin uploads limited to 4 MB (serverless body constraint); 20 MB locally/Docker.
- **Reranker on Vercel:** Cross-encoder (`sentence-transformers` ~80 MB) disabled; `llm-judge` used instead. Semantic chunker falls back to recursive if `langchain-experimental` absent. See [Environment Variables Reference](deployment/DEPLOY-LOCAL-ENV.md) for all optional dep defaults.
- **In-memory/Blob vector stores:** `memory` is tests-only; `blob` is a small demo/fallback only.
- **Live/Ragas tests:** Require external services (OpenAI, Pinecone) and are excluded from standard CI.
- **Guest doc retention:** Guest documents expire after 1 hour but eviction is lazy — no background sweep.

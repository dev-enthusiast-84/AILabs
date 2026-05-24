# Environment Variables Reference

> [← Home](README.md) · [Local & Docker Deployment](deployment/DEPLOY-LOCAL.md) · [Vercel Deployment](deployment/DEPLOY-VERCEL.md)

All variables live in `backend/.env`, created by `setup.sh` from `backend/.env.example`. **Never commit `backend/.env`.**

Production ignores billing-bearing provider values (`OPENAI_API_KEY`, `PINECONE_API_KEY`, `BLOB_READ_WRITE_TOKEN`, `LANGCHAIN_API_KEY`, model and token controls). Enter those through the app **Settings UI** after deployment.

---

## Core

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `OPENAI_API_KEY` | — | **Yes** | LLM completions and text embeddings (local dev only; production uses Settings UI) |
| `SECRET_KEY` | insecure default | **Yes in prod** | JWT signing — generate with `openssl rand -hex 32` |
| `ADMIN_PASSWORD` | _(auto-generated)_ | **Yes** | Admin login password — printed at startup in dev |
| `APP_ENV` | `development` | No | `production` disables Swagger UI and the startup credential banner |
| `SESSION_COMPATIBILITY_VERSION` | `1` | No | Bump after incompatible deploys to force re-login for all sessions |
| `ALLOWED_ORIGINS` | `http://localhost:5173,...` | No | CORS allowed origins (comma-separated) |

---

## Storage

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `VECTOR_STORE_TYPE` | `chroma` | No | `chroma` (local/Docker), `pinecone` (production/Vercel), `memory` (tests only), `blob` (small Vercel demo only) |
| `FILE_STORE_TYPE` | `local` | No | `local` for local dev/Docker; `blob` to persist original uploaded files for preview/download on Vercel |
| `BLOB_READ_WRITE_TOKEN` | — | No | Vercel Blob read/write token (local dev only; production uses Settings UI) |

---

## Pinecone (when `VECTOR_STORE_TYPE=pinecone`)

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `PINECONE_API_KEY` | — | **Yes** | Pinecone API key (local dev only; production uses Settings UI) |
| `PINECONE_INDEX_NAME` | `agenticai-rag-poc-documents` | No | Index name; auto-created if absent (serverless, cosine) |
| `PINECONE_NAMESPACE` | `agenticai-rag-poc` | No | Namespace for multi-tenancy (optional) |
| `PINECONE_CLOUD` | `aws` | No | Serverless cloud provider: `aws` or `gcp` |
| `PINECONE_REGION` | `us-east-1` | No | Serverless region for index creation |

---

## Document & Upload Limits

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `MAX_INDEXED_DOCUMENTS` | `10` | No | Admin corpus cap to bound file/vector storage growth |
| `GUEST_MAX_INDEXED_DOCUMENTS` | `3` | No | Per-guest-session document cap |

---

## Rate Limiting & Sessions

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `QUERY_RATE_LIMIT_PER_MINUTE` | `10` | No | Per-IP cap on `POST /api/query/` |
| `GUEST_UPLOAD_RATE_LIMIT_PER_MINUTE` | `5` | No | Per-IP upload cap for guests (admins exempt) |
| `GUEST_TOKEN_EXPIRE_MINUTES` | `15` | No | Guest JWT lifetime in minutes |

---

## LLM & Token Budget

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `MAX_COMPLETION_TOKENS` | `1024` | No | Hard cap on LLM output tokens per response (production uses Settings UI) |
| `PLANNER_MODEL` | _(llm_model)_ | No | Per-node model override for the Planner node |
| `GENERATOR_MODEL` | _(llm_model)_ | No | Per-node model override for the Generator node (consider `gpt-4o` in prod) |
| `VALIDATOR_MODEL` | _(llm_model)_ | No | Per-node model override for the Validator node |

---

## Retrieval & Chunking

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `RETRIEVER_K` | `4` | No | Top-k chunks returned by similarity search |
| `RETRIEVER_FETCH_K` | `20` | No | Candidate pool size for MMR re-ranking (should be ≥ `RETRIEVER_K`) |
| `RETRIEVER_USE_MMR` | `false` | No | Use Max Marginal Relevance search (Chroma only) for diversity |
| `SIMILARITY_SCORE_THRESHOLD` | `0.0` | No | Min cosine similarity (0–1); chunks below threshold dropped. `0.0` = disabled |
| `RETRIEVER_FUSION_MODE` | `rrf` | No | Multi-query result fusion: `rrf` (Reciprocal Rank Fusion) or `dedup` |
| `RETRIEVER_RRF_K` | `60` | No | RRF constant — higher value reduces rank-position sensitivity |
| `RETRIEVER_HYBRID_BM25` | `true` | No | Fuse BM25 lexical search with dense results via RRF (requires `pip install rank-bm25`) |
| `RETRIEVER_BM25_WEIGHT` | `0.5` | No | BM25 weight hint (informational; RRF drives actual fusion weighting) |
| `RELEVANCE_GRADER_ENABLED` | `false` | No | Enable self-RAG relevance grader — drops irrelevant chunks before generation (adds one LLM call) |
| `CHUNKER_TYPE` | `recursive` | No | `recursive` (default) or `semantic` — semantic uses embedding-similarity boundaries |
| `SEMANTIC_BREAKPOINT_THRESHOLD_TYPE` | `percentile` | No | SemanticChunker threshold type: `percentile`, `standard_deviation`, `interquartile`, `gradient` |

---

## Reranker

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `RERANKER_TYPE` | `none` | No | `none` (disabled) or `cross-encoder` (requires `pip install sentence-transformers`) |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | No | Cross-encoder model used when `RERANKER_TYPE=cross-encoder` |
| `RERANKER_TOP_K` | `4` | No | Number of chunks to keep after reranking |

---

## Observability

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `LANGCHAIN_TRACING_V2` | `false` | No | Set `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | — | No | LangSmith API key (required when tracing enabled) |
| `LANGCHAIN_PROJECT` | `agenticai-rag-poc` | No | LangSmith project name for trace grouping |
| `RAGAS_SCORES_FILE` | `/tmp/ragas_scores.json` | No | Path where Ragas evaluation results are persisted; read by the admin dashboard |

---

## Antivirus (Docker only)

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `CLAMAV_HOST` | — | No | Hostname of a ClamAV daemon. If unset, only regex-based injection checks run. |
| `CLAMAV_PORT` | `3310` | No | TCP port for the ClamAV daemon. Only used when `CLAMAV_HOST` is set. |

---

## Guardrails

Built-in rules (prompt injection, SQL injection, PII, etc.) are seeded automatically on startup. To manage rules locally, use **Settings → Guardrails** in the UI or call `POST /api/guardrails/` directly. Custom rules are in-memory and reset on server restart.

See [Content Guardrails](security/GUARDRAILS.md) for rule types, built-in rules, and API examples.

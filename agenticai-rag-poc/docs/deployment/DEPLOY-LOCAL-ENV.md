# Environment Variables Reference

> [← Home](README.md) · [← Deployment](deployment/DEPLOYMENT.md)

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
| `ALGORITHM` | `HS256` | No | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `45` | No | Admin JWT lifetime in minutes |
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
| `PINECONE_NAMESPACE` | `agenticai-rag-poc` | No | Namespace for multi-tenancy |
| `PINECONE_CLOUD` | `aws` | No | Serverless cloud provider: `aws` or `gcp` |
| `PINECONE_REGION` | `us-east-1` | No | Serverless region for index creation |

---

## Upload & Rate Limits

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `MAX_UPLOAD_SIZE_MB` | `20` | No | Max upload for admins (auto-capped at 4 MB on Vercel) |
| `GUEST_MAX_UPLOAD_SIZE_MB` | `2` | No | Max upload for guests (plain-text files only) |
| `MAX_INDEXED_DOCUMENTS` | `10` | No | Admin corpus cap to bound file/vector storage growth |
| `GUEST_MAX_INDEXED_DOCUMENTS` | `3` | No | Per-guest-session document cap |
| `GUEST_DOC_RETENTION_SECONDS` | `3600` | No | How long guest documents stay indexed after session expiry |
| `MAX_QUERY_LENGTH` | `1000` | No | Maximum query characters — longer inputs → HTTP 422 |
| `RATE_LIMIT_PER_MINUTE` | `30` | No | Global per-IP rate limit applied to all endpoints |
| `QUERY_RATE_LIMIT_PER_MINUTE` | `10` | No | Per-IP cap on `POST /api/query/` |
| `GUEST_UPLOAD_RATE_LIMIT_PER_MINUTE` | `5` | No | Per-IP upload cap for guests (admins exempt) |
| `GUEST_TOKEN_EXPIRE_MINUTES` | `15` | No | Guest JWT lifetime in minutes |

---

## LLM & Token Budget

| Variable | Default | Required | Approx. cost | Purpose |
|----------|---------|----------|-------------|---------|
| `LLM_MODEL` | `gpt-4o-mini` | No | $0.15 / $0.60 per 1M in/out | Default OpenAI model (local dev only; production uses Settings UI) |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | No | $0.02 per 1M tokens | OpenAI embedding model for indexing and query vectors |
| `MAX_COMPLETION_TOKENS` | `1024` | No | — | Hard cap on LLM output tokens per response |
| `TOKEN_BUDGET_WARNING_THRESHOLD` | `800` | No | — | Soft warning logged when approaching the token cap |
| `MAX_CONTEXT_CHUNKS` | `4` | No | — | Maximum chunks included in the LLM prompt |
| `PLANNER_MODEL` | _(llm_model)_ | No | same as `LLM_MODEL` | Per-node model override for the Planner node |
| `GENERATOR_MODEL` | _(llm_model)_ | No | same as `LLM_MODEL` | Per-node model override for the Generator node |
| `VALIDATOR_MODEL` | _(llm_model)_ | No | same as `LLM_MODEL` | Per-node model override for the Validator node |

Per-node models (`PLANNER_MODEL`, `GENERATOR_MODEL`, `VALIDATOR_MODEL`) fall back to `LLM_MODEL` when unset. In production, env values are ignored — all model choices must be entered via the Settings UI; safe defaults apply if omitted. See [Billable Parameter Isolation](security/SECURITY.md#billable-parameter-isolation-runtimesettings_storepy).

The reranker judge model (`RERANKER_JUDGE_MODEL`) is configured separately — see [Pipeline & Retrieval Variables](deployment/DEPLOY-LOCAL-ENV-PIPELINE.md#reranker).

---

## Observability

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `LANGCHAIN_TRACING_V2` | `false` | No | Set `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | — | No | LangSmith API key (required when tracing enabled) |
| `LANGCHAIN_PROJECT` | `agenticai-rag-poc` | No | LangSmith project name for trace grouping |

---

## Antivirus & Guardrails

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `CLAMAV_HOST` | — | No | ClamAV daemon hostname; unset = regex-only injection checks |
| `CLAMAV_PORT` | `3310` | No | ClamAV daemon TCP port (used only when `CLAMAV_HOST` is set) |

Built-in guardrail rules are seeded on startup. Manage via **Settings → Guardrails** or `POST /api/guardrails/`. Custom rules are in-memory; reset on restart. See [Content Guardrails](security/GUARDRAILS.md).

---

## Pipeline & Retrieval Tuning

Retrieval, chunking, reranker, and Ragas evaluation variables → [Pipeline & Retrieval Variables](deployment/DEPLOY-LOCAL-ENV-PIPELINE.md).

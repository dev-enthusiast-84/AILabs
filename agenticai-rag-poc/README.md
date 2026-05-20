# Agentic RAG — Enterprise Document Q&A

> **Full documentation:** [GitHub Pages →](https://dev-enthusiast-84.github.io/AILabs/)

An AI agent–based knowledge and decision support system built for the **Edureka / Illinois Tech Generative AI & ML Capstone**.

Upload enterprise documents (PDF, TXT, CSV, Excel) and ask natural-language questions. A **LangGraph multi-agent pipeline** (Planner → HyDE → Retriever → Grader → Reranker → Generator → Validator) retrieves the most relevant content from the configured vector store and produces grounded, validated answers via OpenAI GPT-4o-mini.

---

## Quick Start

```bash
# Clone and install everything
git clone https://github.com/dev-enthusiast-84/AILabs && cd AILabs/agenticai-rag-poc
bash scripts/local/setup.sh   # auto-detects Python 3.11–3.13, installs deps, generates sample data

# Local only: you may set your OpenAI key in .env, or enter it in Settings UI
nano backend/.env             # optional local-only: OPENAI_API_KEY=<your-openai-api-key>

# Start both servers with hot reload
bash scripts/local/dev.sh --open   # → http://localhost:5173
```

Login: username `admin`, password shown in the startup banner.

```bash
make setup && make dev   # or via Makefile
docker compose up --build  # or via Docker (full stack on :3000 + :8000)
```

---

## Features

| | |
|--|--|
| **Document types** | PDF, TXT, CSV, XLSX / XLS |
| **7-node agent pipeline** | Planner → HyDE → Retriever → Grader → Reranker → Generator → Validator |
| **Voice + multilingual chat** | Voice input/playback, English/Spanish/French answer language, backend-redacted transcript/audio export |
| **Guest mode** | Chat and upload TXT with no credentials |
| **Content guardrails** | Block / redact / flag rules on input, output, export, and voice transcript surfaces |
| **Token transparency** | `tokens_used` field in every response |
| **Production hardening** | Role/session isolation, safe audit logs, readiness endpoint, CSP/Permissions-Policy, Pinecone/Blob deployment path |
| **One-command Vercel deploy** | `bash scripts/remote/deploy-vercel.sh` |

---

## Spec-Driven Development (SDD)

This project uses [Spec-Kit](https://github.com/github/spec-kit) as its SDD framework. Feature specs live in `.specify/specs/`. See [docs/SDD.md](docs/SDD.md) for the full guide, including slash commands, brownfield back-specs, and the 6-step workflow. Run `make spec-check` to validate specs in CI.

---

## Key Environment Variables

Production ignores billing-bearing provider env values such as `OPENAI_API_KEY`,
`PINECONE_API_KEY`, `BLOB_READ_WRITE_TOKEN`, `LANGCHAIN_API_KEY`, and model/token
cost controls. Use the app Settings UI for those values after deployment.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | — | Local development only; production uses Settings UI |
| `SECRET_KEY` | insecure default | JWT signing key — rotate in prod |
| `ADMIN_PASSWORD` | _(generated)_ | Admin login password |
| `VECTOR_STORE_TYPE` | `chroma` | `chroma` (local), `memory` (tests), `pinecone` (production/Vercel default), `blob` (small Vercel Blob vector demo/fallback only) |
| `FILE_STORE_TYPE` | `local` | Set to `blob` to persist original uploaded files for preview/download on Vercel |
| `BLOB_READ_WRITE_TOKEN` | — | Local development only; production uses Settings UI |
| `PINECONE_API_KEY` | — | Local development only; production uses Settings UI |
| `PINECONE_INDEX_NAME` | `agenticai-rag-poc-documents` | Pinecone index name; auto-created if absent (serverless, cosine) |
| `PINECONE_NAMESPACE` | `"agenticai-rag-poc"` | Pinecone namespace for multi-tenancy (optional) |
| `PINECONE_CLOUD` | `aws` | Serverless cloud: `aws` or `gcp` |
| `PINECONE_REGION` | `us-east-1` | Serverless region for index creation |
| `MAX_INDEXED_DOCUMENTS` | `10` | Admin corpus cap to bound file/vector storage growth |
| `GUEST_MAX_INDEXED_DOCUMENTS` | `3` | Per-guest-session document cap |
| `MAX_COMPLETION_TOKENS` | `1024` | Local development default; production uses Settings UI/runtime default |
| `GUEST_TOKEN_EXPIRE_MINUTES` | `15` | Guest session length |
| `QUERY_RATE_LIMIT_PER_MINUTE` | `10` | Per-IP cap on `POST /api/query/` |
| `GUEST_UPLOAD_RATE_LIMIT_PER_MINUTE` | `5` | Per-IP upload cap for guests (admins exempt) |
| `RETRIEVER_K` | `4` | Top-k chunks returned by similarity search |
| `SIMILARITY_SCORE_THRESHOLD` | `0.0` | Min cosine similarity (0–1); chunks below threshold dropped. `0.0` = disabled |
| `RETRIEVER_USE_MMR` | `false` | Use Max Marginal Relevance search (Chroma only) for diversity |
| `RETRIEVER_FETCH_K` | `20` | Candidate pool size for MMR re-ranking (should be ≥ `RETRIEVER_K`) |
| `CHUNKER_TYPE` | `recursive` | `recursive` or `semantic` — semantic uses embedding boundaries |
| `SEMANTIC_BREAKPOINT_THRESHOLD_TYPE` | `percentile` | SemanticChunker threshold: percentile, standard_deviation, interquartile, gradient |
| `PLANNER_MODEL` | _(llm_model)_ | Per-node model override for the Planner agent |
| `GENERATOR_MODEL` | _(llm_model)_ | Per-node model override for the Generator agent (consider `gpt-4o` in prod) |
| `VALIDATOR_MODEL` | _(llm_model)_ | Per-node model override for the Validator agent |
| `LANGCHAIN_TRACING_V2` | `false` | Set `true` to enable LangSmith tracing |
| `LANGCHAIN_API_KEY` | — | LangSmith API key (required when tracing enabled) |
| `LANGCHAIN_PROJECT` | `agenticai-rag-poc` | LangSmith project name for trace grouping |
| `RETRIEVER_FUSION_MODE` | `rrf` | Multi-query result fusion strategy: `rrf` (Reciprocal Rank Fusion) or `dedup` |
| `RETRIEVER_RRF_K` | `60` | RRF constant — higher value reduces rank-position sensitivity |
| `RETRIEVER_HYBRID_BM25` | `false` | Enable BM25 lexical search fused with dense results via RRF (requires `pip install rank-bm25`) |
| `RETRIEVER_BM25_WEIGHT` | `0.5` | BM25 weight hint (informational; RRF drives actual fusion weighting) |
| `RELEVANCE_GRADER_ENABLED` | `false` | Enable self-RAG relevance grader — drops irrelevant chunks before generation (adds one LLM call) |
| `RERANKER_TYPE` | `none` | Cross-encoder reranking: `none` (disabled) or `cross-encoder` (requires `pip install sentence-transformers`) |
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Cross-encoder model used when `RERANKER_TYPE=cross-encoder` |
| `RERANKER_TOP_K` | `4` | Number of chunks to keep after reranking |
| `RAGAS_SCORES_FILE` | `/tmp/ragas_scores.json` | Path where live Ragas evaluation results are persisted; read by the admin dashboard |

---

## Engineering Challenge: Persistence Across Environments

Local and Docker deployments use ChromaDB because it can persist embeddings to a normal writable filesystem. Vercel full-stack deployments are serverless: function instances are ephemeral, `/var/task` is read-only, and `/tmp` is not shared across instances. A file-backed Chroma store can therefore appear to work briefly, then disappear or diverge after reloads, cold starts, or cross-instance requests.

To handle that deployment constraint, production Vercel deployments default to `VECTOR_STORE_TYPE=pinecone`. The active vector store type is deployment configuration and is not changed from the UI. Pinecone stores vectors/chunks in managed durable storage so list, query, and delete operations survive serverless cold starts. The Settings UI may supply Pinecone connection details such as API key, index, namespace, cloud, and region when Pinecone is the configured store. Blob storage is still useful as `FILE_STORE_TYPE=blob` for durable original uploaded files such as PDF previews and downloads; its read/write token can also be supplied through Settings UI when Blob is enabled. `VECTOR_STORE_TYPE=blob` remains available only as a Vercel-native small-demo vector fallback; larger production RAG should pair Pinecone or another hosted vector database with Blob/S3-style object storage for originals.

---

## Documentation

| | |
|--|--|
| [**Pitch Proposal**](pitch.html) | One-page visual summary of capabilities beyond capstone requirements |
| [Capstone Audit](docs/CAPSTONE-AUDIT.md) | Edureka PDF task mapping, submission checklist, and engineering challenges |
| [Setup Guide](docs/SETUP.md) | Full install for macOS, Windows, Linux · Vercel &amp; Docker deployment |
| [Architecture](docs/ARCHITECTURE.md) | System design, data-flow diagrams, project structure |
| [API Reference](docs/API.md) | All endpoints, schemas, example `curl` commands |
| [Content Guardrails](docs/GUARDRAILS.md) | Rule types, built-in rules, API examples |
| [Spec-Driven Development](docs/SDD.md) | Spec-Kit SDD workflow, slash commands, brownfield specs |

---

## Stack

**Backend** — FastAPI · LangGraph · ChromaDB/Pinecone · OpenAI (GPT-4o-mini + text-embedding-3-small)  
**Frontend** — React 18 · TypeScript · Vite · Tailwind CSS · Zustand  
**Auth** — JWT (python-jose) · bcrypt  
**Testing** — pytest · Vitest · Playwright  
**Deploy** — Docker Compose · Vercel (serverless)

---

## Deployment

```bash
bash scripts/remote/deploy-vercel.sh        # Vercel: interactive (asks full-stack vs frontend-only)
bash scripts/remote/deploy-vercel.sh --fullstack                        # full-stack serverless (Pinecone vector default)
bash scripts/remote/deploy-vercel.sh --frontend-only \                  # frontend on Vercel + external backend
    --backend-url https://my-api.railway.app
bash scripts/remote/redeploy-vercel.sh --sample-data --sample-topic "Healthcare Policy"
bash scripts/remote/undeploy-vercel.sh      # remove the Vercel project

make docker                  # Docker Compose: full stack, persistent ChromaDB
make docker-sample-data TOPIC="Healthcare Policy"
```

The deploy script checks all prerequisites (Git, Python 3.11–3.13, Node.js ≥ 20, Vercel CLI) and installs or prompts for anything missing.

See [docs/SETUP.md § 4 — Deployment](docs/SETUP.md#4-deployment--vercel) for the full step-by-step guide, CI/non-interactive usage, teardown, and backend hosting options.

# Cost Analysis

> [← Home](README.md) · [← Project](project/PROJECT.md)

OpenAI API cost reference for the default model configuration. All 7 pipeline features are enabled by default.

---

## Default Model Configuration

| Node | Default Model | Role |
|------|--------------|------|
| Planner | `gpt-4o-mini` | Rewrites question → refined query + 2 variants |
| HyDE | `gpt-4o-mini` | Generates hypothetical document passage for embedding |
| Retriever | *(vector search — no LLM)* | RRF fusion across 4 query variants + BM25 |
| Grader | `gpt-4o-mini` | Self-RAG relevance filter |
| Reranker | `gpt-4.1-mini` | LLM-as-judge scores all chunks 0–10 in one batch call |
| Generator | `gpt-4o-mini` | Grounded answer generation |
| Validator | `gpt-4o-mini` | Classifies VALID or NEEDS_REVISION |
| Embeddings | `text-embedding-3-small` | Document indexing + query embedding |

> **Why `gpt-4.1-mini` for the reranker?**  
> The judge model intentionally uses a different model family from the pipeline (`gpt-4o-mini`). Using the same model to grade its own retrieval creates circular reasoning. `gpt-4.1-mini` offers stronger reranking judgment at ~$0.40/1M input — the most affordable model in the 4.1 family.

Models are overridable at runtime via the Settings UI (admin only) or environment variables — no restart required. See [Pipeline & Retrieval Vars](deployment/DEPLOY-LOCAL-ENV-PIPELINE.md) for env var names.

---

## Per-Query Cost (Default Configuration)

Estimates assume a medium-length question, 4 retrieved chunks, and a ~400-token answer.

| Node | Approx tokens (in / out) | Approx cost |
|------|--------------------------|-------------|
| Planner | ~300 in / ~80 out | ~$0.00009 |
| HyDE | ~200 in / ~150 out | ~$0.00012 |
| Grader | ~1,200 in / ~120 out | ~$0.00025 |
| Reranker (llm-judge) | ~1,500 in / ~128 out | ~$0.00082 |
| Generator | ~2,500 in / ~400 out | ~$0.00062 |
| Validator | ~1,000 in / ~60 out | ~$0.00019 |
| **Total — agentic mode** | | **~$0.002 – $0.004** |
| **Total — simple mode** | generator only | **~$0.0006 – $0.001** |

**Retry overhead**: If the Validator returns `NEEDS_REVISION`, the Generator and Validator re-run (up to 2 retries). Worst-case cost with 2 retries: ~$0.005 – $0.007 per query.

---

## Projected Cost at Scale

| Daily query volume | Agentic mode | Simple mode |
|-------------------|-------------|-------------|
| 100 queries / day | ~$0.20 – $0.40 / day · ~$6 – $12 / month | ~$0.06 – $0.10 / day · ~$2 – $3 / month |
| 1,000 queries / day | ~$2 – $4 / day · ~$60 – $120 / month | ~$0.60 – $1 / day · ~$18 – $30 / month |
| 10,000 queries / day | ~$20 – $40 / day · ~$600 – $1,200 / month | ~$6 – $10 / day · ~$180 – $300 / month |

For production monitoring and cost tracing (LangSmith, OpenAI dashboard, AgentTrace, Vercel logs) → [Cost Tracing Guide](project/COST-ANALYSIS-TRACING.md).

---

## Test Suite Cost

Running the standard test suite incurs no OpenAI cost.

| Suite | Command | Cost | How |
|-------|---------|------|-----|
| Unit + integration | `bash scripts/test/run-tests.sh` | **$0.00** | All LLM and vector store calls are mocked; `OPENAI_API_KEY` is set to a fake placeholder `sk-test-key` |
| Frontend unit + E2E | `npm test && npm run test:e2e` | **$0.00** | All API calls intercepted via `vi.mock` / Playwright `page.route()` |
| **Live tests** | `LIVE_TESTS=1 bash scripts/test/run-live-tests.sh` | **~$0.05 – $0.20 / run** | Real OpenAI calls; requires a genuine key; never run in CI |

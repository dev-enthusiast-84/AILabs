# Production Cost Tracing & Verification

> [← Cost Analysis](project/COST-ANALYSIS.md) · [← Project](project/PROJECT.md) · [← Home](README.md)

Four complementary options to verify and monitor actual API spend. Use them in combination for full observability.

---

### Option 1 — In-App Agent Trace (built-in, zero setup)

Every agentic query returns a full `AgentTrace` in the API response. The Chat UI renders it as a collapsible **Agent Trace** accordion beneath each assistant reply.

| Field | Description |
|-------|-------------|
| `hyde_tokens`, `grader_tokens`, `planner_tokens`, `generator_tokens`, `validator_tokens` | Per-node token counts for every LLM call |
| `hyde_latency_ms`, `grader_latency_ms`, `planner_latency_ms`, `generator_latency_ms`, `validator_latency_ms`, `reranker_latency_ms` | Per-node wall-clock latency |
| `planner_model`, `generator_model`, `validator_model` | Actual model name used per node |
| `retries` | Number of NEEDS_REVISION → generator loops triggered |
| `chunks_found`, `chunks_after_grading`, `chunks_after_rerank` | Retrieval funnel counts |

Read `tokens_used` from the top-level `QueryResponse` for a quick per-query total; drill into `AgentTrace` fields to identify which node consumes the most tokens. **Limitation:** Token data is in the API response only — not persisted server-side by default.

---

### Option 2 — LangSmith Tracing (recommended for remote/Vercel)

LangSmith traces every LangGraph node individually and aggregates cost across a project. No code changes required — flip one setting.

| Data point | Location in LangSmith UI |
|------------|--------------------------|
| Per-node token counts (input / output) | Node run → Metadata → Token Usage |
| Per-node latency | Run start/end timestamps |
| Full prompt sent to each LLM | Run inputs panel |
| Model name per node | Run metadata |
| Retry count (NEEDS_REVISION loops) | Child runs under the parent trace |
| Total query cost (auto-calculated) | Project → Cost column |
| p50 / p95 latency across all queries | Project → Latency distribution chart |

**Enabling LangSmith:**

*Option A — Settings UI (ephemeral on Vercel):* Admin → Settings → expand LangSmith Observability → toggle Enable tracing, enter API key and project name. Takes effect immediately.

*Option B — Environment variables (permanent; recommended for Vercel):*
```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...        # smith.langchain.com → Settings → API Keys
LANGCHAIN_PROJECT=agenticai-rag-poc
```
Add to Vercel under **Settings → Environment Variables** and redeploy.

| Estimate | How to verify in LangSmith |
|----------|---------------------------|
| Per-query cost (~$0.002–$0.004) | Project view → Cost column per trace |
| Retry overhead | Filter traces with > 1 `generator_node` child run |
| Reranker token spend | Sort by `reranker_node` token count |
| Monthly projection | Export → sum token counts × model prices |

---

### Option 3 — OpenAI Usage Dashboard

The OpenAI platform dashboard shows actual billed usage broken down by model, API key, and date — the authoritative source for invoice reconciliation.

1. Go to [platform.openai.com/usage](https://platform.openai.com/usage)
2. Filter by date range and API key
3. Expand by **model** to see `gpt-4o-mini` vs `gpt-4.1-mini` spend separately

Programmatic access: `curl https://api.openai.com/v1/usage?date=<YYYY-MM-DD> -H "Authorization: Bearer $OPENAI_API_KEY"` returns daily token counts grouped by model. **Limitation:** Aggregate across all callers of the API key — no per-query breakdown.

---

### Option 4 — Vercel Function Logs (remote only)

In the Vercel dashboard → project → **Logs** tab, filter by `/api/query` to isolate query invocations. Correlate request timestamps with OpenAI usage timestamps. **Limitation:** Logs are ephemeral; they do not contain token counts unless explicitly emitted. The `tokens_used` field in `AgentTrace` can be logged via a structlog call in `app/api/query.py` at no extra cost.

---

## Comparison Summary

| Option | Setup effort | Per-query detail | Persistent | Cost |
|--------|-------------|-----------------|-----------|------|
| In-App Agent Trace | None (built-in) | Full per-node breakdown | No (response only) | Free |
| LangSmith | Low (1 env var) | Full per-node + project aggregate | Yes | Free tier available |
| OpenAI Dashboard | None | Model-level aggregate | Yes (30 days) | Free |
| Vercel Logs | None | Request-level, no tokens by default | Ephemeral | Free |

For production cost verification, **LangSmith + OpenAI Dashboard** together give the most complete picture: LangSmith for per-query attribution, OpenAI dashboard for invoice reconciliation.

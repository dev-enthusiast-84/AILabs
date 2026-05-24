# API Schemas & Examples

> [← Home](README.md) · [API Reference](api/API.md)

Request/response schemas, AgentTrace field reference, token budget, and rate limits.

---

## Query Request & Response

**Request:**
```json
{ "question": "What are the core capabilities of generative AI?" }
{ "question": "What are the core capabilities of generative AI?", "mode": "simple" }
```

**Agentic response:**
```json
{
  "answer": "Generative AI can produce text, code, images, and structured data ...",
  "sources": ["sample.txt"],
  "citations": [
    { "source": "sample.txt", "chunk_index": 2, "text": "Generative AI can produce text, code ..." }
  ],
  "validation": "VALID",
  "tokens_used": 847,
  "mode": "agentic",
  "retry_count": 0,
  "latency_ms": 4231,
  "output_flagged": false,
  "trace": { ... }
}
```

**Simple response:**
```json
{
  "answer": "Generative AI can produce text, code, images, and structured data ...",
  "sources": ["sample.txt"],
  "citations": [
    { "source": "sample.txt", "chunk_index": 0, "text": "Generative AI can produce text, code ..." }
  ],
  "validation": "N/A",
  "tokens_used": 312,
  "mode": "simple",
  "retry_count": 0,
  "latency_ms": 1840,
  "output_flagged": false,
  "trace": null
}
```

### QueryResponse — `citations` field

`citations` is a list of chunk-level provenance objects, one per retrieved chunk used to generate the answer. Each object contains:

| Field | Type | Description |
|-------|------|-------------|
| `source` | `string` | Document filename (guest prefix stripped for guest users) |
| `chunk_index` | `integer` | Zero-based position of the chunk within the document |
| `text` | `string` | Raw chunk text, truncated to 300 characters |

**Invalid `mode` value → 422:**
```json
{ "question": "...", "mode": "turbo" }
// → HTTP 422 Unprocessable Entity
```

---

## AgentTrace Field Reference

Returned as `trace` in agentic-mode responses. `null` in simple mode. Full field list → [AgentTrace Reference](api/API-SCHEMAS-TRACE.md).

Key fields: `original_question`, `refined_query`, `hypothetical_answer` (HyDE passage), `query_variants` (two Planner rephrases), `chunks_found`, `validation_reason`, token/latency counters per node.

---

## Settings Request & Response

```json
// POST /api/settings/
{ "model": "gpt-4o", "api_key": "<your-openai-api-key>" }

// Response — key is always masked
{
  "model": "gpt-4o",
  "api_key_masked": "sk-****...abcd",
  "api_key_source": "runtime",
  "allowed_models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "o1-preview", "o1-mini"]
}
```

### SettingsResponse — pipeline flags

The response includes the following pipeline feature flags (all admin-settable via `POST /api/settings/`):

| Field | Type | Description |
|-------|------|-------------|
| `retriever_hybrid_bm25` | boolean | Whether BM25 + dense hybrid search is enabled |
| `relevance_grader_enabled` | boolean | Whether the self-RAG grader node filters low-relevance chunks |
| `ragas_evaluation_enabled` | boolean | Whether automatic Ragas evaluation is triggered after every N queries |
| `ragas_auto_trigger_interval` | integer | Number of queries between automatic Ragas evaluation runs (1–10000, default 50). **Admin-only field** — omitted from guest responses. |
| `admin_doc_retention_days` | integer | How many days admin documents are retained before cleanup (1–3650, default 30). **Admin-only field** — omitted from guest responses. |
| `reranker_type` | string | Active reranker (`"none"` or `"cross-encoder"`) |
| `chunker_type` | string | Active chunking strategy (`"recursive"` or `"semantic"`) |

> **Non-guest fields:** `ragas_auto_trigger_interval` and `admin_doc_retention_days` are only included in the response when the caller is authenticated as admin. Guest tokens receive `null` for these fields.

### SettingsUpdateRequest — admin-only fields

The following fields in `POST /api/settings/` require admin role:

| Field | Type | Validation | Description |
|-------|------|-----------|-------------|
| `ragas_auto_trigger_interval` | `int \| null` | 1–10000 | Override the number of queries between automatic Ragas runs |
| `admin_doc_retention_days` | `int \| null` | 1–3650 | Override the admin document retention window in days |

---

## Token Budget

Controlled via `backend/.env`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `MAX_COMPLETION_TOKENS` | `1024` | Hard cap on GPT-4o-mini output tokens per response |
| `TOKEN_BUDGET_WARNING_THRESHOLD` | `800` | Logs a warning when cumulative tokens exceed this |
| `MAX_CONTEXT_CHUNKS` | `4` | Max document chunks sent to the LLM |
| `MAX_INDEXED_DOCUMENTS` | `10` | Admin corpus cap for file/vector storage |
| `GUEST_MAX_INDEXED_DOCUMENTS` | `3` | Per-guest-session document cap |
| `RETRIEVER_K` | `4` | Number of top-k chunks returned by vector similarity search |

`tokens_used` in every query response:
- **Agentic mode** — sum across planner + generator + validator (+ grader if enabled)
- **Simple mode** — single generator call only

For document metadata schemas (`DocumentMetadataItem`, `DocumentMetadataResponse`) → [API Schemas: Documents](api/API-SCHEMAS-DOCUMENTS.md).  
For voice export job error schema → [Voice Export API Schemas](api/API-SCHEMAS-VOICE.md).

---

## Rate Limiting

Exceeding any limit returns `HTTP 429 Too Many Requests`. Full per-endpoint table with rationale → [Operational Limits](deployment/DEPLOY-LIMITS.md). Summary: login 10/min · query 10/min · guest upload 5/min · settings 20/min · ragas-trigger 1/5 min · all others 30/min (all per IP). On Vercel, `slowapi` counters are per function instance.

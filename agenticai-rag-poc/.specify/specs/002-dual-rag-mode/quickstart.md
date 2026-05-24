# Quickstart: Dual RAG Mode

## What changed

`POST /api/query/` now accepts an optional `mode` field:

```json
// Simple mode (fast, no validator)
{ "question": "What is RAG?", "mode": "simple" }

// Agentic mode (default — full pipeline)
{ "question": "What is RAG?", "mode": "agentic" }

// Omit mode for backward-compatible agentic behaviour
{ "question": "What is RAG?" }
```

The response now includes a `mode` echo and `validation` is `"N/A"` for simple mode:

```json
{
  "answer": "RAG grounds LLM answers in retrieved document chunks.",
  "sources": ["rag_overview.txt"],
  "validation": "N/A",
  "tokens_used": 312,
  "mode": "simple"
}
```

## Run after implementation

```bash
# Backend tests
cd backend && pytest tests/unit/ tests/integration/ -v

# Frontend tests
cd frontend && npm test

# Manual smoke test — simple mode
curl -s -X POST http://localhost:8000/api/query/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is RAG?", "mode": "simple"}' | jq .

# Manual smoke test — agentic mode (default)
curl -s -X POST http://localhost:8000/api/query/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is RAG?"}' | jq .
```

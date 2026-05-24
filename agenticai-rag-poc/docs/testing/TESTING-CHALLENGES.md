# Testing Challenges

> [← Testing](testing/TESTING.md) · [Limitations & Challenges](project/CHALLENGES.md)

Architectural testing challenges and trade-offs from the capstone implementation.

---

## Live Test Prerequisites

| Requirement | `test_live_api.py` | `test_live_ragas.py` |
|-------------|:------------------:|:--------------------:|
| `LIVE_TESTS=1` | Required | Required |
| `OPENAI_API_KEY` (real, not `sk-test*`) | Required | Required |
| `ADMIN_PASSWORD` | Required | Not needed |
| uvicorn running on `:8000` | Required | Not needed |
| At least one document indexed | Recommended | Auto-seeded by fixture |
| `HF_TOKEN` | Optional | Optional |

> **`HF_TOKEN`:** When `RERANKER_TYPE=cross-encoder`, the CrossEncoder model downloads from HuggingFace Hub on first query. Without `HF_TOKEN` the download is anonymous (rate-limited). The app explicitly passes `token=False` when unset so no warning appears in test output.

---

## ChromaDB Reset (503 or InternalError in live tests)

ChromaDB 1.5.x has a known SQLite compaction bug (`Rust type 'u64' incompatible with SQL type 'BLOB'`) that corrupts the local database when the schema changes. Reset with:

```bash
rm -rf backend/chroma_db && uvicorn app.main:app --reload --port 8000
```

The upload handler **peek check** fires before any ChromaDB I/O, so empty-file and bad-header rejections still return 422 even when ChromaDB is down.

---

## Test Isolation Without Live Providers

Unit and integration tests must run in CI without real API keys. Three layers:

- **Unit tests** (`backend/tests/unit/`) — fully mocked; no network calls; deterministic and idempotent.
- **Integration tests** (`backend/tests/integration/`) — FastAPI `TestClient` with mocked vector stores and LLM responses; no external provider calls.
- **Live tests** (`backend/tests/live/`) — real OpenAI, Pinecone, ChromaDB; excluded from standard CI; require credentials.

**Challenge:** Mocked tests can pass while the real integration silently breaks (e.g., embedding dimension mismatch after a provider update, Pinecone index schema change). The live test suite exists to catch this drift but is opt-in and not gated in CI.

---

## Coverage Guardrail

Backend coverage is gated at ≥ 98% (`pytest --cov=app`). Maintaining this while adding features with provider-dependent code paths (Pinecone, Blob, OpenAI) requires careful dependency injection so branches can be exercised with mocks. The cost is additional mock complexity in test setup.

---

## Frontend E2E Test Fragility

Playwright E2E tests run against a live stack. Tests that depend on LLM responses are non-deterministic by nature. The test suite focuses on structural assertions (element presence, status codes, access control) rather than response content to keep tests deterministic and reproducible.

---

## Ragas Evaluation

Ragas evaluation (`backend/tests/live/test_live_ragas.py`) requires a populated vector store and real API credentials. Not automated in CI because:
- It consumes OpenAI tokens.
- It requires pre-indexed documents.
- Scores are stored in `RAGAS_SCORES_FILE` and surfaced in the admin dashboard — not suited to per-commit CI gates.

---

## Determinism in Time-Sensitive Tests

JWT expiry, rate limiting, and guest session TTL tests are sensitive to clock timing. The test suite uses monkeypatching and explicit TTL injection rather than `time.sleep` to keep tests fast and deterministic.

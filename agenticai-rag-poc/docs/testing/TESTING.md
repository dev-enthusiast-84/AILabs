# Testing

> [← Home](README.md)

Unit, integration, frontend, and live test suites. All deterministic tests run without real LLM or network calls.

## Testing Documentation

| Document | Purpose |
|----------|---------|
| [Integration Tests](testing/TESTING-INTEGRATION.md) | Isolation patterns, test files, and production hardening coverage |
| [Frontend & E2E](testing/TESTING-FRONTEND.md) | Playwright, live dependency tests, Ragas evaluation, coverage summary |
| [Testing Challenges](testing/TESTING-CHALLENGES.md) | Live test prerequisites, ChromaDB reset, determinism constraints |
| [Coverage Matrix](testing/COVERAGE-MATRIX.md) | Guardrail, redaction, and role/session isolation coverage map |

---

## Test Layers Overview

| Layer | Tool | Scope | Mocks | Count |
|-------|------|-------|-------|-------|
| **Backend unit** | pytest | Pure functions, RAG helpers, stores, auth, guardrails, audit | LLM/vector clients | 300+ tests |
| **Backend integration** | pytest + FastAPI TestClient | HTTP endpoints end-to-end | Vector store + LLM | 250+ tests |
| **Frontend unit** | Vitest + Testing Library | React components, chat, export, settings, guardrails | API + Zustand store | 90+ tests |
| **Frontend E2E** | Playwright | Browser flows and structural UX checks | Optional route mocks | 55+ tests |
| **Live dependency** | pytest | Real OpenAI + ChromaDB + optional live API/Ragas | None | 20+ tests |

**Design principle:** Unit and integration tests never make real LLM or embedding calls. Live tests are always run separately.

---

## Running Tests

```bash
# All backend tests (unit + integration) — no API key needed
cd backend && pytest -v

# Subsets
cd backend && pytest tests/unit/ -v
cd backend && pytest tests/integration/ -v
cd backend && pytest tests/unit/test_auth.py::test_authenticate_user_success -v

# Frontend unit tests
cd frontend && npm test

# Full suite with HTML report
bash scripts/test/run-tests.sh

# Full suite including E2E (both servers must be running)
RUN_E2E=true bash scripts/test/run-tests.sh

```

**Makefile:** `make test` (backend unit+integration) · `make test-frontend` · `make test-e2e` (requires servers running)

## Quality Gates

Runs on PRs touching backend, frontend, or workflow files — no live credentials needed.

```bash
# Backend checks used by CI
cd backend
python -m compileall app tests
pytest tests/unit -q
pytest tests/integration -q

# Frontend checks used by CI
cd frontend
npm run build
npm run test:coverage
```

Live provider suites remain opt-in through `LIVE_TESTS=1` and are not part of the default quality workflow.

---

## Backend Unit Tests

**Location:** `backend/tests/unit/`

Test only pure functions — no I/O, no network, no LLM calls.

| File | What it tests |
|------|--------------|
| `test_auth.py` | `authenticate_user`, `create_access_token`, `verify_token`, `hash_password`, `verify_password`, `_build_users` RuntimeError when `ADMIN_PASSWORD` unset |
| `test_chunking.py` | `RecursiveCharacterTextSplitter` chunk sizes and overlap |
| `test_config.py` | `Settings.allowed_origins_list`, `max_upload_size_bytes`, `effective_max_upload_size_mb` (Vercel-aware 4 MB cap) |
| `test_file_store.py` | In-memory file store CRUD and deduplication |
| `test_guardrails.py` | `sanitize_query` (bleach XSS, injection regex), `validate_filename` (path traversal) |
| `test_ingestion.py` | Text extraction for TXT, CSV, XLSX, PDF (real sample files, no network) |
| `test_pipeline.py` | `format_context` formatter; `run_simple_rag` returns answer, sources, `validation="N/A"`, `mode="simple"` |
| `test_settings_store.py` | `get_effective_api_key`, `get_effective_model`, JTI one-time gate |
| `test_startup.py` | `_print_startup_banner` shown in `development`, suppressed in `production` and `test` |
| `test_vector_store_memory.py` | In-memory vector store add, search, delete, list |

**Key pattern — `_build_users` raises if `ADMIN_PASSWORD` unset:**

```python
def test_build_users_raises_when_password_unset():
    mock_s = MagicMock()
    mock_s.admin_password = ""
    with patch("app.auth.utils.get_settings", return_value=mock_s):
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            _build_users()
```

---

## Backend Integration Tests

**Location:** `backend/tests/integration/` — full HTTP stack tests with mocked providers.

See [Backend Integration Tests](testing/TESTING-INTEGRATION.md) for isolation patterns, test file descriptions, and production hardening coverage map.

---

## Live Dependency Tests

**Location:** `backend/tests/live/` — opt-in, not in CI. Full run commands → [Frontend & E2E Tests](testing/TESTING-FRONTEND.md); prerequisites and ChromaDB reset → [Testing Challenges](testing/TESTING-CHALLENGES.md).

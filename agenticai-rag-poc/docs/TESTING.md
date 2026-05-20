# Backend Testing

> [← Home](README.md) · [Frontend & E2E Tests](TESTING-FRONTEND.md)

Unit and integration test suite for the FastAPI backend. All tests run without real LLM or network calls.

For the enterprise guardrail/redaction/isolation map, see [Coverage Matrix](COVERAGE-MATRIX.md).

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

# Coverage report
cd backend && pytest --cov=app --cov-report=html

# Frontend unit tests
cd frontend && npm test

# Full suite with HTML report
bash scripts/test/run-tests.sh

# Full suite including E2E (both servers must be running)
RUN_E2E=true bash scripts/test/run-tests.sh

# Makefile shortcuts
make test           # backend unit + integration
make test-frontend  # frontend Vitest
make test-e2e       # Playwright (requires servers running)
```

## Quality Gates

The deterministic quality workflow runs on pull requests that touch backend, frontend, or workflow files. It does not require live OpenAI, Pinecone, Blob, LangSmith, Vercel, browser microphone, or local `.env` credentials.

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

**Key patterns:**

```python
# Settings override — avoids reading backend/.env in tests
def _s(**kwargs) -> Settings:
    return Settings(admin_password="x", **kwargs)

# _build_users raises if ADMIN_PASSWORD unset
def test_build_users_raises_when_password_unset():
    mock_s = MagicMock()
    mock_s.admin_password = ""
    with patch("app.auth.utils.get_settings", return_value=mock_s):
        with pytest.raises(RuntimeError, match="ADMIN_PASSWORD"):
            _build_users()
```

---

## Backend Integration Tests

**Location:** `backend/tests/integration/`

Uses FastAPI's `TestClient` to exercise the full HTTP stack — middleware, routing, auth guards, response schemas — without real LLM or embedding calls.

### Isolation

`backend/conftest.py` uses pytest session hooks to patch `get_vector_store` before any app module is imported:

```python
def pytest_sessionstart(session):
    if not _LIVE_MODE:
        _vs_patch.start()   # replaces ChromaDB with MagicMock for the entire session
```

Agent calls in query tests are additionally patched per test:

```python
with patch("app.api.query.run_agent", return_value=_MOCK_AGENT_RESULT):
    resp = client.post("/api/query/", ...)
```

> **Important:** Fixtures that call `POST /api/auth/login` or `POST /api/auth/guest` must be `scope="session"`. Per-test calls exhaust the 30 req/min rate limit.

### Integration Test Files

| File | What it tests |
|------|--------------|
| `test_api_auth.py` | Login success/failure, guest token, JWT expiry, rate limiting |
| `test_api_documents.py` | Upload (all formats), list, delete, size limits, guest restrictions, content safety, duplicate rejection (409) |
| `test_api_guardrails.py` | CRUD for rules, guest read-only, admin-only writes, regex validation |
| `test_api_query.py` | Query success, injection blocking, guest/admin isolation, simple vs agentic mode, multilingual retrieval/generation separation, output flagging |
| `test_api_settings.py` | Get/set OpenAI/Pinecone/Blob/LangSmith settings, role restrictions, guest one-time lock, Ragas trigger |
| `test_api_voice_export.py` | Backend-authoritative transcript redaction, audio export redaction, guest-scoped API key use, clear export failures |
| `test_api_readiness.py` | Safe readiness status for app config, OpenAI, vector store, file store, and export capability |
| `test_api_ragas.py` | Admin-only Ragas evaluation flow and degraded dependency handling |

### Production Hardening Coverage

| Concern | Tests |
|---------|-------|
| Role/session document isolation | `test_guest_list_excludes_admin_documents`, `test_admin_list_excludes_guest_documents`, `test_query_guest_user_cannot_query_admin_documents` |
| Settings permissions | `test_guest_cannot_update_*`, `test_guest_can_update_pinecone_settings_once`, `test_guest_can_update_blob_token_once` |
| Backend export redaction | `test_voice_redact_endpoint_returns_authoritative_redacted_transcript`, `test_voice_export_returns_redacted_playable_mp3_payload` |
| Multilingual retrieval quality | `test_query_accepts_language_without_polluting_agent_retrieval_question`, `test_query_simple_language_instruction_kept_out_of_retrieval_question` |
| Safe audit/readiness | `test_audit_event_redacts_sensitive_metadata`, `test_global_exception_log_omits_sensitive_exception_message`, `test_readiness_reports_components_without_secrets` |

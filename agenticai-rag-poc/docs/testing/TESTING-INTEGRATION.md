# Backend Integration Tests

> [← Testing](testing/TESTING.md)

Uses FastAPI's `TestClient` to exercise the full HTTP stack — middleware, routing, auth guards, response schemas — without real LLM or embedding calls.

---

## Isolation

`backend/conftest.py` patches `get_vector_store` before any app module is imported:

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

---

## Test Files

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

---

## Production Hardening Coverage

| Concern | Tests |
|---------|-------|
| Role/session document isolation | `test_guest_list_excludes_admin_documents`, `test_admin_list_excludes_guest_documents`, `test_query_guest_user_cannot_query_admin_documents` |
| Settings permissions | `test_guest_cannot_update_*`, `test_guest_can_update_pinecone_settings_once`, `test_guest_can_update_blob_token_once` |
| Backend export redaction | `test_voice_redact_endpoint_returns_authoritative_redacted_transcript`, `test_voice_export_returns_redacted_playable_mp3_payload` |
| Multilingual retrieval quality | `test_query_accepts_language_without_polluting_agent_retrieval_question`, `test_query_simple_language_instruction_kept_out_of_retrieval_question` |
| Safe audit/readiness | `test_audit_event_redacts_sensitive_metadata`, `test_global_exception_log_omits_sensitive_exception_message`, `test_readiness_reports_components_without_secrets` |

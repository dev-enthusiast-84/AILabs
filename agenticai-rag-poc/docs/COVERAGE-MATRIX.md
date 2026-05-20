# Coverage Matrix

> [Home](README.md) · [Backend Testing](TESTING.md) · [Frontend & E2E Tests](TESTING-FRONTEND.md)

Deterministic coverage map for the pending `005-enterprise-production-hardening` slice. These checks use mocked providers or local test doubles; they do not require live OpenAI, Pinecone, Blob, browser microphone permission, or deployment credentials.

## Guardrail And Redaction Surfaces

| Requirement | Surface | Deterministic coverage |
|-------------|---------|------------------------|
| FR-003 | Typed chat input | `backend/tests/integration/test_api_query.py::test_query_injection_blocked`; `frontend/tests/e2e/app.spec.ts` mocked typed chat flow |
| FR-003 | Voice transcript input | `frontend/tests/unit/ChatInterface.test.tsx::captures a voice transcript and submits it through normal chat`; voice transcripts enter the same query path as typed chat |
| FR-003 | Multilingual input and language instruction surface | `backend/tests/integration/test_api_query.py::test_query_guardrails_evaluate_language_instruction_surface`; `test_query_blocks_multilingual_input_before_agent_execution`; `frontend/tests/e2e/app.spec.ts::multilingual typed chat sends selected language through mocked query flow` |
| FR-003 | Translated query representation | No internal translation is currently implemented. Existing tests assert answer-language instructions stay out of retrieval questions: `test_query_accepts_language_without_polluting_agent_retrieval_question` and `test_query_simple_language_instruction_kept_out_of_retrieval_question`. |
| FR-003 | Generated answer before display/export | `backend/tests/integration/test_api_query.py::test_query_output_redaction_applies_before_response`; output flag badge coverage in `frontend/tests/unit/ChatInterface.test.tsx` |
| FR-003 | Browser playback text | `frontend/tests/unit/ChatInterface.test.tsx::plays assistant responses with redacted speech text`; `redacts generated answer secrets before browser playback` |
| FR-003 | Transcript export | `backend/tests/integration/test_api_voice_export.py::test_voice_redact_endpoint_returns_authoritative_redacted_transcript`; `frontend/tests/unit/ChatInterface.test.tsx::uses backend-redacted transcript export when the service is available`; `frontend/tests/e2e/app.spec.ts::transcript export calls backend redaction before download` |
| FR-003 | Audio export synthesis input | `backend/tests/integration/test_api_voice_export.py::test_voice_export_returns_redacted_playable_mp3_payload`; `test_voice_export_redacts_voice_transcript_before_audio_synthesis`; `frontend/tests/unit/ChatInterface.test.tsx::offers audio export for voice-only chat and sends structured messages for backend redaction` |

## Role And Session Isolation

| Requirement | Workflow | Deterministic coverage |
|-------------|----------|------------------------|
| FR-004 | Chat/query | `backend/tests/integration/test_api_query.py::test_query_guest_user_cannot_query_admin_documents`; `test_query_guest_user_allowed` |
| FR-004 | Voice/export | `backend/tests/integration/test_api_voice_export.py::test_voice_export_uses_guest_runtime_api_key_scope`; audio/transcript export endpoints require bearer auth |
| FR-004 | Multilingual chat | `backend/tests/integration/test_api_query.py::test_query_accepts_language_without_polluting_agent_retrieval_question` runs through authenticated query with the same role/session document filter |
| FR-004 | Document list/access | `backend/tests/integration/test_api_documents.py::test_guest_list_only_includes_current_guest_session_documents`; `test_admin_list_excludes_guest_documents`; `test_get_content_uses_guest_session_source_key`; `test_get_file_admin_does_not_read_guest_session_key` |
| FR-004 | Settings | `backend/tests/integration/test_api_settings.py::test_guest_cannot_update_retrieval_settings`; `test_guest_can_update_pinecone_settings_once`; `test_guest_can_update_blob_token_once`; `test_guest_settings_view_does_not_expose_admin_runtime_key` |

## Production-Critical E2E Or Mocked Unit Coverage

| Requirement | Flow | Deterministic coverage |
|-------------|------|------------------------|
| FR-021 / SC-009 | Typed chat | `frontend/tests/e2e/app.spec.ts::query response enables transcript export in chat window` |
| FR-021 / SC-009 | Voice chat | `frontend/tests/unit/ChatInterface.test.tsx::captures a voice transcript and submits it through normal chat` with mocked `SpeechRecognition` |
| FR-021 / SC-009 | Multilingual retrieval | `frontend/tests/e2e/app.spec.ts::multilingual typed chat sends selected language through mocked query flow` and backend retrieval-question assertions |
| FR-021 / SC-009 | Document access | `frontend/tests/e2e/app.spec.ts::source document access opens mocked document content`; backend role/session document access tests |
| FR-021 / SC-009 | Settings prerequisites | `frontend/tests/e2e/app.spec.ts::missing OpenAI settings prerequisite opens settings instead of querying`; frontend unit settings prerequisite tests for OpenAI, Pinecone, and Blob |
| FR-021 / SC-009 | Transcript export | `frontend/tests/e2e/app.spec.ts::transcript export calls backend redaction before download`; frontend unit backend-redaction export test |
| FR-021 / SC-009 | Audio export | `frontend/tests/unit/ChatInterface.test.tsx::offers audio export for voice-only chat and sends structured messages for backend redaction`; backend audio synthesis input redaction tests |
| FR-021 / SC-009 | Degraded dependency path | Backend readiness/export failure tests: `test_voice_export_missing_api_key_returns_clear_error`, `test_voice_export_timeout_returns_safe_retry_message`, `test_upload_indexing_failure_returns_503`, and readiness degraded dependency tests in `test_api_readiness.py` |

## Notes

- Async export polling, cancellation, owner scoping, retry, timeout, and artifact expiration are covered by backend integration tests. Frontend behavior remains deterministic through mocked unit/E2E flows.
- Additional no-paid-service production-hardening recommendations and cloud extension points are tracked in `docs/SPEC-005-COMPLIANCE.md`.
- Live provider coverage remains opt-in under the live test suite and is not required for this matrix.

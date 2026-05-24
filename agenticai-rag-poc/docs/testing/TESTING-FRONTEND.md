# Frontend & E2E Tests

> [← Home](README.md) · [← Testing](testing/TESTING.md)

Frontend unit tests, Playwright E2E, live dependency tests, Ragas evaluation, and coverage summary.

For the enterprise guardrail/redaction/isolation map, see [Coverage Matrix](testing/COVERAGE-MATRIX.md).

---

## Frontend Unit Tests

**Location:** `frontend/tests/unit/` · **Tool:** Vitest + `@testing-library/react` · All deps mocked with `vi.mock()`.

```bash
cd frontend
npm test
npm run test:coverage
```

`npm run test:coverage` enforces Vitest coverage thresholds. Coverage excludes Vite config, generated reports, E2E specs, test setup, type-only files, and bootstrap entrypoints. Reports written to `test-reports/frontend-coverage/`.

| File | What it tests |
|------|--------------|
| `App.test.tsx` | `<Analytics />` and `<SpeedInsights />` mounted on every route |
| `LoginPage.test.tsx` | Renders inputs, disables submit when empty, calls `authApi.login` on submit |
| `SettingsModal.test.tsx` | Renders OpenAI/Pinecone/Blob/LangSmith settings, shows masked keys, validates inputs, handles guest one-time lock |
| `ChatInterface.test.tsx` | Empty/loaded doc states, content-derived suggestions, mode toggle, multilingual chat, voice capture/playback, backend-redacted transcript/audio export, validation badge, agent trace accordion |
| `validation.test.ts` | Client-side query validation helpers (empty, too-long) |
| `GuardrailsModal.test.tsx` | Lists rules, toggles enabled state, creates/deletes custom rules |
| `DocumentViewerModal.test.tsx` | Displays reconstructed document content, handles empty state |

---

## Frontend E2E Tests (Playwright)

**Location:** `frontend/tests/e2e/app.spec.ts` · **Requires both servers:** `bash scripts/local/dev.sh`, then `cd frontend && npm run test:e2e`

| Test | Flow |
|------|------|
| Unauthenticated redirect | Navigate to `/` → redirected to `/login` |
| Login form renders | Username input, password input, sign-in button all visible |
| Login button disabled | Disabled while fields are empty |
| Invalid credentials | Wrong password → error appears |
| Logo navigates home | Click logo → URL becomes `/` |
| Document upload area | Dashboard shows dropzone element |
| Query input visible + max length | Shows query input with `maxlength="1000"` |
| Settings modal opens | Gear icon → dialog with model select and API key input |
| API key field masked | Input has `type="password"` by default |
| Settings modal close | Cancel button and Escape both close the dialog |
| API key XSS blocked | `<script>` value → "Invalid format" validation error |
| Chat language + export controls | Language selector and disabled transcript export visible before conversation |
| Query enables export | Mocked query response appears and enables transcript export |

---

## Live Dependency Tests

**Location:** `backend/tests/live/` · **Run via:** `bash scripts/test/run-live-tests.sh` · Never run in CI by default.

**Prerequisites:** Real `OPENAI_API_KEY` (not `sk-test`); running backend + matching `ADMIN_PASSWORD` for the API suite.

```bash
export OPENAI_API_KEY=<your-openai-api-key>
bash scripts/test/run-live-tests.sh                        # all suites (Ragas skipped)
bash scripts/test/run-live-tests.sh openai                 # connectivity + embeddings
bash scripts/test/run-live-tests.sh chromadb               # ChromaDB CRUD
bash scripts/test/run-live-tests.sh agent                  # full 7-node pipeline
bash scripts/test/run-live-tests.sh api                    # end-to-end HTTP
bash scripts/test/run-live-tests.sh ragas                  # Ragas quality metrics
RUN_RAGAS_EVAL=false bash scripts/test/run-live-tests.sh   # skip Ragas in 'all' run
```

| File | What it tests |
|------|--------------|
| `test_live_openai.py` | API key validity, embedding generation, LLM completion, token callback |
| `test_live_chromadb.py` | Add, similarity search, metadata filter, delete in ephemeral collection |
| `test_live_agent.py` | Planner, Retriever, Generator, Validator nodes individually + full compiled graph; `run_simple_rag()` |
| `test_live_api.py` | Health, auth, upload/list/delete, end-to-end query, guardrail blocks, readiness, backend redaction endpoint |
| `test_live_ragas.py` | Ragas quality metrics: faithfulness, answer relevancy, context precision, recall |

**Timeout controls:** `LIVE_SESSION_TIMEOUT` (default `300` s — entire session) · `LIVE_STAGE_TIMEOUT` (default `30` s — per interactive prompt before auto-proceeding).

---

## Ragas RAG Quality Evaluation

**Location:** `backend/tests/live/test_live_ragas.py` · Scores saved to `/tmp/ragas_scores.json` and displayed in the admin Settings panel.

| Metric | Threshold | What it checks |
|--------|-----------|----------------|
| **Faithfulness** | ≥ 0.5 | Is the answer grounded in retrieved context? Penalises hallucinated claims. |
| **Answer relevancy** | ≥ 0.5 | Does the answer address the question? Penalises evasive responses. |
| **Context precision** | ≥ 0.3 | Are retrieved chunks relevant? Penalises retrieval noise. |
| **Context recall** | ≥ 0.3 | Did retrieval surface the needed information? Requires `ground_truth`. |

> **Cost:** ~100–500 tokens per run. Edit `_EVAL_SAMPLES` in `test_live_ragas.py` with your actual documents and reference answers.

---

## Coverage Summary

| Module group | Coverage | Notes |
|-------------|----------|-------|
| `api/` (documents, guardrails, query, settings) | 100% | |
| `auth/` (router, utils) | 100% | `_build_users` RuntimeError path covered |
| `config.py` · `guardrails/` · `rag/` (chunking, ingestion, pipeline, scanner, bm25) | 100% | |
| `rag/vector_store.py` | 67% | ChromaDB paths via live tests only |
| `agents/rag_agent.py` | 42% | LLM nodes via live tests only |
| `main.py` | 96% | |
| **TOTAL** | **~91%** | Remaining gaps are intentional (LLM / DB runtime paths) |

For sample queries to use during manual testing, see [Coverage Matrix](testing/COVERAGE-MATRIX.md).

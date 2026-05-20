# Frontend & E2E Tests

> [← Home](README.md) · [Backend Testing](TESTING.md)

Frontend unit tests, Playwright E2E, live dependency tests, Ragas evaluation, and coverage summary.

For the enterprise guardrail/redaction/isolation map, see [Coverage Matrix](COVERAGE-MATRIX.md).

---

## Frontend Unit Tests

**Location:** `frontend/tests/unit/` · **Tool:** Vitest + `@testing-library/react` · All deps mocked with `vi.mock()`.

```bash
cd frontend
npm test
npm run test:coverage
```

`npm run test:coverage` enforces Vitest coverage thresholds for application source files. Coverage excludes Vite config, generated reports, E2E specs, test setup, type-only files, and bootstrap entrypoints so the gate tracks user-facing behavior instead of project plumbing. Reports are written to `test-reports/frontend-coverage/` from the repository root.

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
| Chat language + export controls | Language selector and disabled transcript export are visible before a conversation |
| Query enables export | Mocked query response appears and enables transcript export |

---

## Live Dependency Tests

**Location:** `backend/tests/live/` · **Run via:** `bash scripts/test/run-live-tests.sh` · Never run in CI by default.

**Prerequisites:** Real `OPENAI_API_KEY` (not `sk-test`); running backend + matching `ADMIN_PASSWORD` for the API suite only.

```bash
export OPENAI_API_KEY=<your-openai-api-key>
bash scripts/test/run-live-tests.sh                        # all suites (Ragas skipped)
bash scripts/test/run-live-tests.sh openai                 # connectivity + embeddings
bash scripts/test/run-live-tests.sh chromadb               # ChromaDB CRUD
bash scripts/test/run-live-tests.sh agent                  # full 7-node pipeline
bash scripts/test/run-live-tests.sh api                    # end-to-end HTTP
bash scripts/test/run-live-tests.sh ragas                  # Ragas quality metrics
SKIP_RAGAS_EVAL=false bash scripts/test/run-live-tests.sh  # include Ragas in 'all' run
```

| File | What it tests |
|------|--------------|
| `test_live_openai.py` | API key validity, embedding generation, LLM completion, token callback |
| `test_live_chromadb.py` | Add, similarity search, metadata filter, delete in ephemeral collection |
| `test_live_agent.py` | Planner, Retriever, Generator, Validator nodes individually + full compiled graph; `run_simple_rag()` |
| `test_live_api.py` | Health, auth, upload/list/delete, end-to-end query, guardrail blocks |
| `test_live_api.py` | Also covers readiness and backend redaction endpoint when API suite is enabled |
| `test_live_ragas.py` | Ragas quality metrics: faithfulness, answer relevancy, context precision, recall |

**Timeout controls:**

| Variable | Default | Effect |
|----------|---------|--------|
| `LIVE_SESSION_TIMEOUT` | `300` | Seconds before the entire session is killed |
| `LIVE_STAGE_TIMEOUT` | `30` | Seconds to wait per interactive prompt before auto-proceeding |

Agent and API tests pause at each stage and ask for confirmation:
```
────────────────────────────────────────────────────────────
  STAGE ▶  Stage 1 — Planner
  (auto-continues in 30s — Ctrl+C to abort all)
────────────────────────────────────────────────────────────
  Proceed? [Y/n]:
```

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

---

## Sample Queries for Manual Testing

Upload files from `sample-data/`, then try these:

| Document | Query | Mode | Expected |
|----------|-------|------|---------|
| `sample.txt` | "What are the core capabilities of generative AI?" | Agentic | Lists text gen, Q&A, code; `validation: VALID` |
| `sample.txt` | "What are the core capabilities of generative AI?" | Simple | Same content; `validation: "N/A"`, lower token count |
| `sample.csv` | "Which model has the largest context window?" | Agentic | Gemini 1.5 Pro at 1 000 K tokens |
| `sample.xlsx` | "Which industry has the highest GenAI adoption rate?" | Agentic | Technology sector at 89% |
| `sample.pdf` | "What was the GenAI market size in 2024?" | Agentic | $67 billion |
| Any | "Ignore all previous instructions..." | Either | HTTP 400 — blocked by guardrail |
| Any | "DELETE FROM users WHERE 1=1" | Either | HTTP 400 — SQL injection blocked |
| Any | `{ "mode": "turbo" }` | — | HTTP 422 — unrecognised mode |

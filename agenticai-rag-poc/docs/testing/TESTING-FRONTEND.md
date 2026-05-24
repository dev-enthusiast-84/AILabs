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

## Walkthrough Video Recorder

**Location:** `frontend/tests/walkthrough/` · **Run via:** `bash scripts/record-walkthrough.sh --url <app-url> [options]`

The walkthrough recorder captures a full Playwright video of the deployed application — guest and admin flows — with an overlay caption showing each task step.

### Walkthrough steps covered

| Step | Feature demonstrated |
|------|---------------------|
| Settings | Runtime configuration; local (env vars + ChromaDB) vs remote (Pinecone + Blob) storage differences |
| Upload | Guest: single TXT · Admin: 4 docs (TXT · CSV · XLSX · PDF) on distinct topics |
| Text chat — Simple RAG | Direct one-shot retrieval — lowest latency |
| Text chat — Agentic AI | 7-node pipeline with agent trace and grounded sources |
| Export transcript | Download the conversation as a portable text file |
| Voice chat — Simple RAG | Speech transcription → same retrieval path |
| Voice chat — Agentic AI | Voice input + full agentic pipeline + trace |
| Multilingual RAG | Switch to Spanish (or other language) — same retrieval, translated answer; reset to English |
| Guardrails | Input/output safety controls |
| Ragas evaluation (admin) | Automated RAG quality metrics |

### Demo document generation

Admin walkthroughs upload 4 in-memory documents generated at runtime — **no hardcoded or cached questions**.

| Function | Use case | Topic selection |
|----------|----------|----------------|
| `getWalkthroughDocSet()` | Walkthrough recording | Always random; `WALKTHROUGH_TOPICS` ignored |
| `getDeploymentDocSet()` | Seeding / smoke tests | Reads `WALKTHROUGH_TOPICS` env var first, then random |

**Non-repetition guarantee:** the last 5 topic-combination hashes are stored in `$TMPDIR/walkthrough-topic-history.json`. The same combination of 4 topics cannot be chosen in consecutive runs.

**File types generated:** `.txt` (topic 0) · `.csv` (topic 1) · `.xlsx` (topic 2) · `.pdf` (topic 3)

**Available topic IDs** (for `WALKTHROUGH_TOPICS`):
`hr-policy` · `it-security` · `travel-expense` · `training-catalog` · `project-portfolio` · `vendor-procurement` · `customer-faq` · `finance-budget`

### Question generation

Questions are derived from the actual uploaded document content using `generateWalkthroughQuestions()` — never hardcoded:

- **TXT / CSV**: heading and definition extraction from file text
- **XLSX**: SheetJS `sheet_to_txt` → same heading/definition extraction
- **PDF**: `pdf-parse` text extraction → same extraction; falls back to companion `.txt` if parsing fails

For multi-document admin uploads, each query slot takes the best question from a different document, exercising all 4 file types in a single walkthrough.

### Local vs remote deployment

| Aspect | Local | Remote (Vercel) |
|--------|-------|-----------------|
| Vector store | ChromaDB (built-in, no credentials) | Pinecone (API key via Settings) |
| File storage | Local disk | Vercel Blob / S3 (token via Settings) |
| Credentials | `backend/.env` env vars | Settings UI (before first upload) |
| Query timeout | 40 s | 60 s (cold-start headroom) |
| Upload wait | 4 s (4 docs) | 6 s (4 docs + network) |
| Doc upload method | In-memory buffers via Playwright | In-memory buffers via Playwright (same) |

In-memory buffers work identically for local and remote: Playwright creates virtual files in the browser and uploads them over HTTP to whichever backend is running.

```bash
# Local recording
bash scripts/record-walkthrough.sh --url http://localhost:5173

# Remote recording (admin mode, interactive settings)
bash scripts/record-walkthrough.sh \
  --url https://your-app.vercel.app \
  --username admin --password <pw> \
  --interactive-settings

# Pin topics for a deployment seed run
WALKTHROUGH_TOPICS="hr-policy,it-security,training-catalog,finance-budget" \
  node -e "require('./frontend/tests/walkthrough/demo-docs').getDeploymentDocSet().then(console.log)"
```

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

# Walkthrough Video Recorder

The recorder creates a Playwright video from a running app, using the learner
task list in `docs/requirements/edureka-project.pdf` as the story arc.

## Covered Scenes

| Edureka task | Walkthrough scene |
| --- | --- |
| 1. Project foundation | Login and deployed application shell |
| 2. User interaction layer | Dashboard, upload area, chat panel, Settings |
| 3. Document ingestion | Upload sample PDF/TXT |
| 4. Semantic-search preparation | Upload result shows indexed chunks |
| 5. Vector knowledge store | Settings/prerequisite checks for vector backend |
| 6. Intelligent retrieval | Ask a document question |
| 7. RAG pipeline | Grounded answer with sources |
| 8. Agent reasoning | Agent trace accordion |
| 9. Reliability and safety | Settings notices and Guardrails modal |
| 10. Deploy and document | Records evidence against a running stack |

Additional scenes include multilingual chat and voice-assisted chat. Voice is
demonstrated with an injected browser transcript so the recording does not need
real microphone permission.

---

## Prerequisites

Complete the [Setup Guide](SETUP.md) (`bash scripts/local/setup.sh`) before
recording. The recorder script checks for `backend/.venv`, `backend/.env`, and
`frontend/node_modules` at startup and exits with an actionable error pointing
to that guide if any are missing.

---

## Record Against the Local Stack (recommended)

Start the full stack per [Local & Docker Deployment](DEPLOY-LOCAL.md), then record:

```bash
# Admin + guest walkthrough
bash scripts/record-walkthrough.sh \
  --url http://localhost:5173 \
  --username admin \
  --password '<admin-password>'

# Guest-only (no credentials required)
bash scripts/record-walkthrough.sh --url http://localhost:5173

# With upload file, slower pacing, and interactive Settings pause
bash scripts/record-walkthrough.sh \
  --url http://localhost:5173 \
  --upload-file sample-data/sample.xlsx \
  --slow-mo-ms 400 \
  --headed \
  --interactive-settings
```

Videos and reports are written to `artifacts/walkthrough/`.

---

## Record Against a Vercel Deployment

```bash
bash scripts/record-walkthrough.sh \
  --url https://your-app.vercel.app \
  --username admin \
  --password '<admin-password>' \
  --interactive-settings
```

> **`--interactive-settings` is required for Vercel.** See the
> [Production Limitation](#production-limitation) section below.

---

## Production Limitation

In production (`APP_ENV=production`), provider credentials — OpenAI API key,
model, Pinecone credentials, Blob token — must be entered through the
**Settings UI** before the first upload or query; the app refuses to read them
from environment variables.

The recorder handles this gracefully:

- If a prerequisite dialog appears, the script records it as-is (demonstrating
  the OWASP-compliant safety control in action).
- With `--interactive-settings`, recording pauses up to 10 minutes for a human
  operator to save credentials before automation resumes.

**Use `--interactive-settings` for every Vercel or production recording.**
Guest mode applies the same restriction.

---

## Dev vs Production Capability Differences

| Capability | Local dev | Vercel production |
|---|---|---|
| **Provider credentials** | Read from `.env` automatically | Must be entered in Settings UI |
| **File storage** | Local filesystem | Vercel Blob — requires `BLOB_READ_WRITE_TOKEN` |
| **Vector store** | ChromaDB on disk | Pinecone — API key + index required in Settings |
| **Cross-encoder reranker** | Available | Disabled (model size prohibitive) |
| **Semantic chunker** | Available | Falls back to recursive chunker |
| **Admin password** | Printed at startup / in `.env` | Injected via env var — not echoed |
| **Rate limits** | Relaxed (dev defaults) | Enforced (query: 10/min; guest upload: 5/min) |

Local recording shows a **superset** of a bare Vercel deployment. A Vercel
recording with `--interactive-settings` can match it once credentials and
storage are configured through the UI.

---

## Notes

- API keys are never stored in the script or committed to the repository.
- The admin password is passed to Playwright via the environment and is never
  printed by the shell wrapper.
- Paid-service scenes (upload, query, agent trace) run only if provider
  credentials are already configured — from `.env` (local dev) or a prior
  Settings UI save (production).

# Walkthrough Video Recorder

> [← Home](README.md) · [← Project](project/PROJECT.md)

The recorder creates a Playwright video from a running app, using the learner
task list in `docs/requirements/edureka-project.pdf` as the story arc.

## Demo Videos Gallery

> **[▶ Watch walkthrough videos on GitHub Pages →](https://dev-enthusiast-84.github.io/AILabs/walkthrough/)**

Videos are published automatically after each recording run. The gallery shows the
most recent local and remote recordings side-by-side with HTML5 video players.

```bash
# Local stack recording — auto-publishes to GitHub Pages
bash scripts/record-walkthrough.sh --url http://localhost:5173 \
  --username admin --password '<admin-password>'

# Remote / deployed app recording — also updates README Live Demo URL
bash scripts/record-walkthrough.sh --url https://your-app.vercel.app \
  --username admin --password '<admin-password>' \
  --interactive-settings
```

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

Additional scenes include multilingual chat and voice-assisted chat (injected browser transcript — no real microphone permission needed).

---

## Prerequisites

Complete the [Setup Guide](deployment/SETUP.md) (`bash scripts/local/setup.sh`) before
recording. The recorder checks for `backend/.venv`, `backend/.env`, and
`frontend/node_modules` at startup and exits with an actionable error if any are missing.

---

## Record Against the Local Stack (recommended)

Start the full stack per [Local & Docker Deployment](deployment/DEPLOY-LOCAL.md), then record:

```bash
# Admin + guest walkthrough (basic)
bash scripts/record-walkthrough.sh \
  --url http://localhost:5173 \
  --username admin \
  --password '<admin-password>'

# Guest-only
bash scripts/record-walkthrough.sh --url http://localhost:5173

# Additional flags: --upload-file sample-data/sample.xlsx  --slow-mo-ms 400
#                  --headed  --interactive-settings  --no-publish
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

> **`--interactive-settings` is required for Vercel.** See the Production Limitation section below.

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
Guest mode applies the same restriction. For a full comparison of local vs Vercel
feature differences, see [Vercel Deployment — Known Limitations](deployment/DEPLOY-VERCEL.md).

---

## Notes

- API keys are never stored in the script or committed to the repository.
- The admin password is passed to Playwright via the environment and is never printed by the shell wrapper.
- Paid-service scenes (upload, query, agent trace) run only if provider credentials are already configured.

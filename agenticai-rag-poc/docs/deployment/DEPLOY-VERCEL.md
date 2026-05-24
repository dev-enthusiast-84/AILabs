# Vercel Deployment

> [← Home](README.md) · [← Deployment](deployment/DEPLOYMENT.md)

Deploy the app publicly — full-stack on Vercel or React SPA on Vercel CDN + a persistent backend elsewhere.

## Prerequisites

| Requirement | Version | How to obtain |
|-------------|---------|--------------|
| Git | any | pre-installed or `brew install git` |
| Python | 3.11–3.13 | `brew install python@3.13` |
| Node.js + npm | 20 LTS+ | `brew install node@20` |
| Vercel CLI | any | `npm install -g vercel` *(script installs this automatically if missing)* |
| Vercel account | free tier OK | [vercel.com/signup](https://vercel.com/signup) |
| OpenAI API key | — | Not needed at deploy time — enter via Settings UI after first login |

---

## Deployment Modes

| Mode | Command | Persistence | Best for |
|------|---------|-------------|---------|
| **Full-stack** | `bash scripts/remote/deploy-vercel.sh --fullstack` | ✅ Pinecone for vectors; Vercel Blob optional for original files | Demos, evaluations |
| **Frontend-only** | `bash scripts/remote/deploy-vercel.sh --frontend-only --backend-url <url>` | ✅ ChromaDB on remote host | Production |
| **Interactive** | `bash scripts/remote/deploy-vercel.sh` | Depends on choice | First-time deploy |

**Full-stack trade-offs:** FastAPI runs as a serverless function (cold start ~2 s); local ChromaDB file persistence is not reliable on Vercel, so production full-stack deploys use `VECTOR_STORE_TYPE=pinecone` for durable vector/chunk storage. `VECTOR_STORE_TYPE` is environment/deployment configuration only. Pinecone connection details can be set in Vercel env vars or the app Settings UI. Use `FILE_STORE_TYPE=blob` with Vercel Blob when original uploaded files must persist for preview/download. Upload limit is 4 MB.

**Frontend-only trade-offs:** React SPA served from Vercel's global CDN; FastAPI on Railway/Render/Docker with persistent ChromaDB; full 20 MB upload limit.

---

## Step-by-Step: First Deploy

```bash
# Step 1 — Clone (skip if already done)
git clone https://github.com/dev-enthusiast-84/AILabs && cd AILabs/agenticai-rag-poc

# Step 2 — Run the interactive deploy script
bash scripts/remote/deploy-vercel.sh
```

The script automatically:
1. Checks git, Node ≥ 20, npm, Python 3.11–3.13
2. Installs Vercel CLI if missing (asks confirmation)
3. Runs `vercel login` if not authenticated (opens browser)
4. Asks: Full-stack or Frontend-only?
5. Auto-generates `ADMIN_PASSWORD` (or uses your supplied value) and `SECRET_KEY`
6. Sets all environment variables in the Vercel project
7. Deploys and prints the public URL

**After deploying:**
1. Open the printed URL → sign in as `admin` with the password shown
2. Click **Settings** (gear icon) → paste your **OpenAI API key** → Save
3. Upload a document and ask a question

> **Billing safety:** Production ignores provider credentials and model/token cost controls from Vercel env vars. Enter OpenAI, Pinecone, Blob, LangSmith, model, and token settings through the app Settings UI after login.

---

## Environment Variables on Vercel

Set automatically by `deploy-vercel.sh`. View/update in **Project → Settings → Environment Variables**.

| Variable | Set by script | Purpose |
|----------|:------------:|---------|
| `OPENAI_API_KEY` | No — enter via Settings UI | Ignored from env in production |
| `SECRET_KEY` | Yes — auto-generated | JWT signing key |
| `ADMIN_USERNAME` | Yes — defaults to `admin` | Admin login username |
| `ADMIN_PASSWORD` | Yes — generated or supplied | Admin login password |
| `APP_ENV` | Yes — `production` | Disables Swagger UI and credential banner |
| `SESSION_COMPATIBILITY_VERSION` | Optional | Bump on non-backward-compatible deploys to force admin/guest re-login |
| `VECTOR_STORE_TYPE` | Yes — `pinecone` (full-stack) | Durable Pinecone-backed vector/chunk storage |
| `PINECONE_API_KEY` | No — enter via Settings UI | Ignored from env in production |
| `PINECONE_INDEX_NAME` | Optional | Defaults to `agenticai-rag-poc-documents`; auto-created if absent |
| `FILE_STORE_TYPE` | Optional — `blob` | Persists original uploaded files for preview/download |
| `BLOB_READ_WRITE_TOKEN` | No — enter via Settings UI | Ignored from env in production |
| `ALLOWED_ORIGINS` | Yes — Vercel domain | CORS allowed origin |
| `BACKEND_URL` | Yes (frontend-only) | Points React app to backend |

---

For CI/non-interactive deploy, redeployment, teardown, and backend hosting alternatives → [Vercel Operations](deployment/DEPLOY-VERCEL-OPS.md).

---

## Limitations on Vercel

| Limitation | Workaround |
|------------|------------|
| Original file previews lost on cold start (full-stack without Blob) | Set `FILE_STORE_TYPE=blob` and connect Vercel Blob |
| 4 MB upload limit (serverless body constraint) | Use frontend-only mode with a separate backend |
| Cold start ~2 s after idle | Re-enter provider settings in the app Settings UI |
| Rate limits per-instance, not global | Deploy backend separately with a shared rate-limit store |
| `RERANKER_TYPE=cross-encoder` not supported (`sentence-transformers` exceeds function size) | Keep `RERANKER_TYPE=none` (default) |
| `VECTOR_STORE_TYPE=blob` is small demo only — does not scale | Use `VECTOR_STORE_TYPE=pinecone` for production |
| ClamAV not available — `CLAMAV_HOST` has no effect | Regex injection checks in `rag/scanner.py` still run on all uploads |

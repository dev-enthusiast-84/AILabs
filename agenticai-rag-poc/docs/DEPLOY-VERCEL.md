# Vercel Deployment

> [← Home](README.md) · [Local & Docker](DEPLOY-LOCAL.md)

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

## CI / Non-Interactive Deploy

```bash
export ADMIN_PASSWORD="<your-strong-password>"
export VERCEL_TOKEN="<from vercel.com/account/tokens>"
export PROJECT_NAME="my-rag-app"

bash scripts/remote/deploy-vercel.sh --fullstack --yes
# or
export BACKEND_URL="https://my-backend.railway.app"
bash scripts/remote/deploy-vercel.sh --frontend-only --backend-url "$BACKEND_URL" --yes
```

| Flag | Description |
|------|-------------|
| `--fullstack` | Deploy backend + frontend on Vercel |
| `--frontend-only` | Deploy React SPA only |
| `--backend-url <url>` | Backend URL for frontend-only mode |
| `--project-name <name>` | Override the Vercel project name |
| `--yes` | Skip all interactive prompts |

---

## Updating & Teardown

```bash
# Push code updates (keeps env vars)
bash scripts/remote/redeploy-vercel.sh
bash scripts/remote/redeploy-vercel.sh --admin-password gen     # rotate admin password
bash scripts/remote/redeploy-vercel.sh --secret-key "$(openssl rand -hex 32)"
bash scripts/remote/redeploy-vercel.sh --sample-data --sample-topic "Healthcare Policy"
make vercel-redeploy SAMPLE_DATA=1 TOPIC="Healthcare Policy"

# Teardown
bash scripts/remote/undeploy-vercel.sh                          # interactive
bash scripts/remote/undeploy-vercel.sh --project-name my-app   # specify project
bash scripts/remote/undeploy-vercel.sh --yes                    # skip confirmation
make vercel-undeploy
```

`undeploy-vercel.sh` removes all deployments + aliases, all env vars set by the deploy script, and the local `frontend/.vercel/` directory. It does **not** remove your source code or any separately hosted backend.

Provider credentials such as OpenAI, Pinecone, Blob, and LangSmith keys are not
set by deploy/redeploy scripts. Enter them in the app Settings UI after signing
in so they do not become default production environment variables.

---

## Backend Hosting Options (Frontend-Only Mode)

| Platform | Deploy | Persistent disk | Free tier | Notes |
|----------|--------|----------------|-----------|-------|
| **Railway** | `railway up` | Yes | 500 h/month | Set `VECTOR_STORE_TYPE=chroma` |
| **Render** | Docker deploy | Yes (~$7/mo) | 750 h/month | Attach a persistent disk |
| **Fly.io** | `fly deploy` | Yes (volumes) | 3 shared VMs | Requires `fly.toml` |
| **VPS / Docker** | `docker compose up` | Yes | — | See [Local & Docker](DEPLOY-LOCAL.md) |

---

## Known Limitations

| Limitation | Applies to | Workaround |
|------------|-----------|------------|
| Original file previews lost on cold start | Full-stack without Blob | Set `FILE_STORE_TYPE=blob` and connect Vercel Blob |
| 4 MB upload limit | Full-stack | Use frontend-only mode |
| Cold start ~2 s after idle | Full-stack | Re-enter provider settings in the app Settings UI |
| Rate limits not global across instances | Full-stack | Deploy backend separately |

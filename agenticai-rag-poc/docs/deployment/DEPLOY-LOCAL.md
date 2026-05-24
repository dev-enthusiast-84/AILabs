# Local & Docker Deployment

> [← Home](README.md) · [← Deployment](deployment/DEPLOYMENT.md) · [Setup Guide](deployment/SETUP.md)

Three local run modes: **dev** (hot reload), **production-like build**, and **Docker Compose**.

## 1. Local Dev (Hot Reload)

**Prerequisites:** Complete [Setup Guide](deployment/SETUP.md) first — Python 3.11–3.13, Node 20+, `setup.sh` run.

```bash
# Recommended: single command
bash scripts/local/dev.sh            # backend :8000 + frontend :5173
bash scripts/local/dev.sh --open     # same + opens browser

# Advanced flags
bash scripts/local/dev.sh --backend-only                            # FastAPI only
bash scripts/local/dev.sh --frontend-only                           # Vite only
bash scripts/local/dev.sh --port-backend 9000 --port-frontend 3000 # custom ports
```

**Hot-reload behaviour:**

| Layer | Mechanism | Triggered by |
|-------|-----------|-------------|
| Backend | `uvicorn --reload` | Any `.py` file saved under `backend/app/` |
| Frontend | Vite HMR | Any `.tsx`, `.ts`, or `.css` file — instant browser update |

## 2. `deploy-local.sh` — Dev and Production-Preview Modes

`scripts/local/deploy-local.sh` is the full-featured launcher. It handles first-time setup automatically, manages ephemeral credentials, and supports both dev and production-preview modes via the `--prod` flag.

```bash
bash scripts/local/deploy-local.sh          # dev mode (hot reload) — backend :8000 · frontend :5173
bash scripts/local/deploy-local.sh --prod   # production preview     — backend :8000 · frontend :4173
bash scripts/local/deploy-local.sh --open   # same + opens browser
bash scripts/local/deploy-local.sh --skip-build  # reuse existing dist/ (--prod only, faster restart)
bash scripts/local/deploy-local.sh --sample-data --sample-topic "Healthcare Policy"
make deploy-local                           # Makefile shortcut
```

| | `deploy-local.sh` (default) | `deploy-local.sh --prod` |
|---|---|---|
| Frontend | Vite dev server on `:5173` (HMR) | `npm run build` → preview on `:4173` |
| Backend | `uvicorn --reload` | `uvicorn --workers 1` (no watcher) |
| Hot reload | ✅ Both layers | ❌ None |
| Bind host | `127.0.0.1` | `0.0.0.0` (LAN accessible) |
| Use case | Active development | Demo, presentation, pre-Vercel validation |

Credentials are ephemeral in both modes — written to `backend/.env` for the session and wiped automatically on Ctrl-C.

## 3. Hot Reload Quick Reference

| Command | Backend hot reload | Frontend hot reload | Notes |
|---------|-------------------|---------------------|-------|
| `bash scripts/local/dev.sh` | ✅ `uvicorn --reload` watches `backend/app/` | ✅ Vite HMR — instant browser update | Scoped watcher; avoids false restarts from test/chroma files |
| `bash scripts/local/deploy-local.sh` | ✅ `uvicorn --reload` | ✅ Vite HMR on `:5173` | Default dev mode; also handles setup and ephemeral credentials |
| `bash scripts/local/deploy-local.sh --prod` | ❌ No reload | ❌ Static nginx-style preview on `:4173` | Production-parity build; requires `--build` or existing `dist/` |
| `docker compose up` | ❌ No reload | ❌ Static nginx build on `:3000` | No source volume mounts; code changes require `docker compose up --build` |

**When to use each:**

- **`dev.sh`** — fastest iteration; assumes setup already done; no credential management.
- **`deploy-local.sh`** (default) — same hot reload, but auto-runs setup on first use and manages ephemeral credentials.
- **`deploy-local.sh --prod`** — demos and pre-Vercel validation; matches production build pipeline.
- **`docker compose up`** — full-stack integration testing; production parity including ClamAV; not for active development.

---

## 4. Environment Variables

`OPENAI_API_KEY`, `SECRET_KEY` (prod), `ADMIN_PASSWORD` required; all others have defaults. Full reference → [Environment Variables](deployment/DEPLOY-LOCAL-ENV.md) · [Pipeline & Retrieval Vars](deployment/DEPLOY-LOCAL-ENV-PIPELINE.md).

---

## 5. Docker Compose

Runs the full stack with ChromaDB data stored in a named Docker volume that survives container restarts.

**Prerequisites:** Docker Desktop 26+ running (whale icon solid in menu bar).

> **No hot reload.** The backend Dockerfile starts uvicorn without `--reload` and the frontend Dockerfile runs `npm run build` served by nginx. There are no source volume mounts — any code change requires `docker compose up --build`.

```bash
# First run: set required env vars
cp backend/.env.example backend/.env
nano backend/.env   # set OPENAI_API_KEY, ADMIN_PASSWORD, SECRET_KEY

# Build and start (first run ~2 min; subsequent starts fast)
docker compose up --build

# Access
#   Frontend  →  http://localhost:3000
#   Backend   →  http://localhost:8000
#   Swagger   →  http://localhost:8000/api/docs

# Stop (ChromaDB data preserved in Docker volume)
docker compose down

# Stop + delete all data
docker compose down -v

# Makefile shortcuts
make docker       # docker compose up --build
make docker-down  # docker compose down
make docker-sample-data TOPIC="Healthcare Policy"  # generate files to upload
```

**ChromaDB persistence:**

| Command | Containers | `chroma_data` volume |
|---------|-----------|---------------------|
| `docker compose down` | Removed | **Kept** — data intact |
| `docker compose down -v` | Removed | **Deleted** |
| `docker compose up` | Recreated | **Reused** — previous data available |

---

## 6. ClamAV Antivirus (Docker only)

The Compose stack includes a `clamav` service that scans every uploaded file before indexing.

> **First start:** ClamAV downloads virus definitions (~300 MB) — startup takes 2–3 min longer than usual. Subsequent starts reuse cached definitions.

To **disable AV scanning**: remove `CLAMAV_HOST`/`CLAMAV_PORT` from the backend environment block, remove the `clamav` service, and remove its `depends_on` entry.

---

## 7. Ragas Evaluation (Optional)

Trigger via **Settings → Ragas Evaluation** (`POST /api/settings/ragas-trigger`) or `LIVE_TESTS=1 OPENAI_API_KEY=<key> pytest tests/live/test_live_ragas.py -v`. Scores persist to `RAGAS_SCORES_FILE` (default `/tmp/ragas_scores.json`). See [Frontend & E2E Tests](testing/TESTING-FRONTEND.md) for full Ragas details.

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `docker: command not found` | Docker Desktop not installed |
| `Cannot connect to the Docker daemon` | Docker Desktop not running — open the app |
| `port 3000 already in use` | `lsof -i :3000` (macOS/Linux) · `netstat -ano \| findstr 3000` (Windows) |
| `exec format error` | `docker compose build --no-cache --platform linux/amd64` |
| Backend crashes immediately | `OPENAI_API_KEY`, `ADMIN_PASSWORD`, `SECRET_KEY` all required in `backend/.env` |
| Backend takes >3 min on first run | ClamAV downloading virus DB — `docker compose logs clamav` |

# Local & Docker Deployment

> [← Home](README.md) · [Setup Guide](deployment/SETUP.md) · [Vercel Deployment](deployment/DEPLOY-VERCEL.md)

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

## 2. Local Production Run

Use `scripts/local/deploy-local.sh` for production-like builds — demos, presentations, or validating the built frontend before deploying to Vercel.

| | `dev.sh` | `deploy-local.sh` |
|---|---|---|
| Frontend | Vite dev server on `:5173` | Production build served on `:4173` |
| Backend | `uvicorn --reload` | `uvicorn --workers 1` (no watcher) |
| Bind host | `127.0.0.1` | `0.0.0.0` (LAN accessible) |

```bash
bash scripts/local/deploy-local.sh          # backend :8000 · frontend :4173
bash scripts/local/deploy-local.sh --open   # same + opens browser
bash scripts/local/deploy-local.sh --skip-build  # reuse existing dist/ (faster restart)
bash scripts/local/deploy-local.sh --sample-data --sample-topic "Healthcare Policy"
make deploy-local                           # Makefile shortcut
```

`deploy-local.sh` can generate sample PDF/TXT/CSV/XLSX files before the app starts. If you do not pass `--sample-topic`, it prompts for a topic and writes the files to `sample-data/` for upload through the UI.

## 3. Environment Variables Reference

Full variable reference including `CLAMAV_HOST`, `CLAMAV_PORT`, and guardrails notes → [Environment Variables](deployment/DEPLOY-LOCAL-ENV.md).

Required variables: `OPENAI_API_KEY`, `SECRET_KEY` (prod), `ADMIN_PASSWORD`. All others have defaults.

---

## 4. Docker Compose

Runs the full stack with ChromaDB data stored in a named Docker volume that survives container restarts.

**Prerequisites:** Docker Desktop 26+ running (whale icon solid in menu bar).

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

## 5. ClamAV Antivirus (Docker only)

The Compose stack includes a `clamav` service that scans every uploaded file before indexing.

> **First start:** ClamAV downloads virus definitions (~300 MB) — startup takes 2–3 min longer than usual. Subsequent starts reuse cached definitions.

To **disable AV scanning**: remove `CLAMAV_HOST`/`CLAMAV_PORT` from the backend environment block, remove the `clamav` service, and remove its `depends_on` entry.

---

## 6. Ragas Evaluation (Optional)

After documents are indexed, trigger a Ragas evaluation via **Settings → Ragas Evaluation** in the UI (`POST /api/settings/ragas-trigger`), or run the live test suite:

```bash
cd backend && source .venv/bin/activate
LIVE_TESTS=1 OPENAI_API_KEY=<key> pytest tests/live/test_live_ragas.py -v
```

`RAGAS_SCORES_FILE` (default `/tmp/ragas_scores.json`) controls where scores are persisted. See [Testing](testing/TESTING.md) for the full live-test reference.

---

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `docker: command not found` | Docker Desktop not installed — see [Section 4](#4-docker-compose) |
| `Cannot connect to the Docker daemon` | Docker Desktop installed but not running — open the app |
| `port 3000 already in use` | `lsof -i :3000` (macOS/Linux) · `netstat -ano \| findstr 3000` (Windows) |
| `exec format error` | `docker compose build --no-cache --platform linux/amd64` |
| Backend crashes immediately | Check `backend/.env` — `OPENAI_API_KEY`, `ADMIN_PASSWORD`, `SECRET_KEY` all required |
| Backend takes >3 min on first run | ClamAV downloading virus DB — watch `docker compose logs clamav` |

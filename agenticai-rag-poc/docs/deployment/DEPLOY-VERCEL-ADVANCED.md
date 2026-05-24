# Vercel Deployment: Advanced Options

> [← Home](README.md) · [Vercel Deployment](deployment/DEPLOY-VERCEL.md) · [Local & Docker](deployment/DEPLOY-LOCAL.md)

Teardown, redeployment, and backend hosting alternatives for frontend-only mode.

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

Provider credentials such as OpenAI, Pinecone, Blob, and LangSmith keys are not set by deploy/redeploy scripts. Enter them in the app Settings UI after signing in so they do not become default production environment variables.

---

## Backend Hosting Options (Frontend-Only Mode)

| Platform | Deploy | Persistent disk | Free tier | Notes |
|----------|--------|----------------|-----------|-------|
| **Railway** | `railway up` | Yes | 500 h/month | Set `VECTOR_STORE_TYPE=chroma` |
| **Render** | Docker deploy | Yes (~$7/mo) | 750 h/month | Attach a persistent disk |
| **Fly.io** | `fly deploy` | Yes (volumes) | 3 shared VMs | Requires `fly.toml` |
| **VPS / Docker** | `docker compose up` | Yes | — | See [Local & Docker](deployment/DEPLOY-LOCAL.md) |

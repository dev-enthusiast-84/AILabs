# Deployment

> [← Home](README.md)

All deployment paths — local development, Docker Compose, Vercel serverless, environment configuration, and operational limits. Start with [Setup Guide](deployment/SETUP.md) for first-time installation.

## Deployment Guides

| Guide | Purpose |
|-------|---------|
| [Setup Guide](deployment/SETUP.md) | First-time setup: prerequisites, Python/Node install, venv, .env generation |
| [Setup Verification](deployment/SETUP-VERIFY.md) | Visual checklist and GitHub Pages verification after setup |
| [Local & Docker](deployment/DEPLOY-LOCAL.md) | Dev server hot reload, production-like build, Docker Compose |
| [Vercel Deployment](deployment/DEPLOY-VERCEL.md) | Full-stack serverless deploy, one-command setup, limitations |
| [Vercel Operations](deployment/DEPLOY-VERCEL-OPS.md) | CI/non-interactive deploy, redeployment, teardown, backend hosting |
| [Environment Variables](deployment/DEPLOY-LOCAL-ENV.md) | Auth, upload, rate limits, vector store, API key, and session variables |
| [Pipeline & Retrieval Vars](deployment/DEPLOY-LOCAL-ENV-PIPELINE.md) | Retrieval tuning, chunking strategies, reranker, and Ragas evaluation vars |
| [Operational Limits](deployment/DEPLOY-LIMITS.md) | All hard-coded upload caps, voice export limits, rate limits, async job TTLs |

## Quick Deployment Reference

| Target | Command |
|--------|---------|
| Local dev server | `bash scripts/local/dev.sh --open` |
| Docker Compose | `docker compose up --build` |
| Vercel full-stack | `bash scripts/remote/deploy-vercel.sh --fullstack` |
| Vercel frontend only | `bash scripts/remote/deploy-vercel.sh --frontend-only --backend-url <url>` |

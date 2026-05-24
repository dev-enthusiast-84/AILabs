.PHONY: setup dev dev-backend dev-frontend deploy-local test test-e2e test-deploy docker docker-backend docker-down \
        deploy deploy-fullstack deploy-frontend vercel-redeploy vercel-undeploy sample-data docker-sample-data \
        spec-check spec-validate spec-install spec-new docs-readme docs-serve help

# ── One-command setup ──────────────────────────────────────────────────────────
setup:
	bash scripts/local/setup.sh
	$(MAKE) docs-readme

# ── Development servers ────────────────────────────────────────────────────────
dev:
	bash scripts/local/dev.sh

dev-open:
	bash scripts/local/dev.sh --open

dev-backend:
	bash scripts/local/dev.sh --backend-only

dev-frontend:
	bash scripts/local/dev.sh --frontend-only

# ── Local production deployment ───────────────────────────────────────────────
deploy-local:
	bash scripts/local/deploy-local.sh

deploy-local-open:
	bash scripts/local/deploy-local.sh --open

# ── Tests ──────────────────────────────────────────────────────────────────────
test:
	bash scripts/test/run-tests.sh

test-e2e:
	RUN_E2E=true bash scripts/test/run-tests.sh

test-backend-unit:
	cd backend && source .venv/bin/activate && pytest tests/unit/ -v

test-backend-integration:
	cd backend && source .venv/bin/activate && pytest tests/integration/ -v

test-frontend:
	cd frontend && npm test

test-deploy:
	bash scripts/test/test_deploy_scripts.sh

# ── Docker ─────────────────────────────────────────────────────────────────────
docker:
	docker compose up --build

docker-backend:
	docker compose up --build backend

docker-down:
	docker compose down -v

# ── Vercel deployment ──────────────────────────────────────────────────────────
# deploy            — interactive mode selector (prompts full-stack vs frontend-only)
# deploy-fullstack  — frontend + backend as a single Vercel serverless project
# deploy-frontend   — static frontend on Vercel; requires BACKEND_URL
# vercel-undeploy   — remove the Vercel project (all deployments + env vars)
deploy:
	bash scripts/remote/deploy-vercel.sh

deploy-fullstack:
	bash scripts/remote/deploy-vercel.sh --fullstack

deploy-frontend:
	bash scripts/remote/deploy-vercel.sh --frontend-only $(if $(BACKEND_URL),--backend-url $(BACKEND_URL),)

vercel-redeploy:
	bash scripts/remote/redeploy-vercel.sh $(if $(SAMPLE_DATA),--sample-data,) $(if $(TOPIC),--sample-topic "$(TOPIC)",)

vercel-undeploy:
	bash scripts/remote/undeploy-vercel.sh

# ── Sample data ────────────────────────────────────────────────────────────────
# TOPIC variable sets the document topic (default: "Generative AI and Agentic AI")
# Examples:
#   make sample-data
#   make sample-data TOPIC="Healthcare Policy"
sample-data:
	cd backend && source .venv/bin/activate && pip install -q reportlab openpyxl && \
	  cd .. && python sample-data/generate_samples.py $(if $(TOPIC),--topic "$(TOPIC)",)

# Generate sample data then show instructions to upload to a running Docker stack
docker-sample-data:
	cd backend && source .venv/bin/activate && pip install -q reportlab openpyxl && \
	  cd .. && \
	  if [ -n "$(TOPIC)" ]; then \
	    python sample-data/generate_samples.py --topic "$(TOPIC)"; \
	  else \
	    read -r -p "  Topic for sample documents [Generative AI and Agentic AI]: " topic; \
	    if [ -n "$$topic" ]; then \
	      python sample-data/generate_samples.py --topic "$$topic"; \
	    else \
	      python sample-data/generate_samples.py; \
	    fi; \
	  fi
	@echo ""
	@echo "  Sample files ready in sample-data/"
	@echo "  Upload them at http://localhost:3000 (drag & drop)"
	@echo "  or via Swagger at http://localhost:8000/api/docs → POST /api/documents/"
	@echo ""

# ── Docs ──────────────────────────────────────────────────────────────────────
# Generates docs/README.md (Docsify homepage) from the root README by stripping
# the docs/ prefix from link hrefs so paths resolve correctly under docs/.
# CI runs this automatically before deploying to GitHub Pages.
# Run locally once after cloning, and after any edits to root README.md.
docs-readme:
	sed 's|](docs/|](|g' README.md > docs/README.md

# ── Spec-Kit (SDD) ──────────────────────────────────────────────────────────
spec-check:
	bash .specify/scripts/bash/spec-check.sh

spec-new:
	@echo "Run /speckit-specify in your Claude Code session to create a new feature spec."
	@echo "Specs will be created under .specify/specs/[feature-name]/"

spec-validate: spec-check
	@echo "All specs valid."

spec-install:
	pip3 install "git+https://github.com/github/spec-kit.git"

# ── Help ───────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  ── Setup & local dev ───────────────────────────────────────────"
	@echo "  make setup              One-command local setup (venv, npm, .env, sample data prompt)"
	@echo "  make dev                Start backend + frontend with hot reload (single terminal)"
	@echo "  make dev-open           Same, and open browser automatically"
	@echo "  make dev-backend        Backend only (port 8000, uvicorn --reload)"
	@echo "  make dev-frontend       Frontend only (port 5173, Vite HMR)"
	@echo "  make deploy-local       Production-mode local run (built frontend, no hot reload)"
	@echo "  make deploy-local-open  Same, and open browser automatically"
	@echo ""
	@echo "  ── Tests ────────────────────────────────────────────────────────"
	@echo "  make test               Run all unit + integration tests with HTML reports"
	@echo "  make test-e2e           Run all tests including Playwright E2E"
	@echo "  make sample-data        Generate sample PDF/TXT/CSV/XLSX test files"
	@echo ""
	@echo "  ── Docker ───────────────────────────────────────────────────────"
	@echo "  make docker             Build and start full stack (backend :8000 + frontend :3000)"
	@echo "  make docker-backend     Backend service only (port 8000)"
	@echo "  make docker-down        Stop Docker stack and remove volumes"
	@echo ""
	@echo "  ── Sample data ──────────────────────────────────────────────────"
	@echo "  make sample-data                       Generate sample files (default topic)"
	@echo "  make sample-data TOPIC=\"GenAI\"          Generate with custom topic"
	@echo "  make docker-sample-data                Generate + show upload instructions (Docker)"
	@echo "  make docker-sample-data TOPIC=\"GenAI\"  Same, custom topic"
	@echo ""
	@echo "  ── Vercel deployment ────────────────────────────────────────────"
	@echo "  make deploy             Interactive: choose full-stack or frontend-only"
	@echo "  make deploy-fullstack   Full-stack on Vercel (frontend + serverless backend)"
	@echo "  make deploy-frontend    Frontend on Vercel with external backend"
	@echo "                          Usage: make deploy-frontend BACKEND_URL=https://my-api.railway.app"
	@echo "  make vercel-redeploy    Redeploy Vercel project; add SAMPLE_DATA=1 or TOPIC=\"GenAI\""
	@echo "  make vercel-undeploy    Remove the Vercel project (all deployments + env vars)"
	@echo "  make test-deploy        Smoke-test deploy/undeploy scripts (no network calls)"
	@echo ""
	@echo "  ── Docs ─────────────────────────────────────────────────────────────────────"
	@echo "  make docs-readme        Generate docs/README.md from root README (Docsify homepage)"
	@echo "                          Run once after clone; re-run after editing README.md"
	@echo ""
	@echo "  ── Spec-Kit (SDD) ───────────────────────────────────────────────────────────"
	@echo "  make spec-install           Install specify-cli (one-time setup)"
	@echo "  make spec-check             Validate all spec files in .specify/specs/"
	@echo "  make spec-validate          Same as spec-check with summary output"
	@echo "  make spec-new               Show instructions to create a new feature spec"
	@echo ""

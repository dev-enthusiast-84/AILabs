#!/usr/bin/env bash
# Packages the Edureka Capstone Project submission as a zip file.
#
# What is included:
#   - All source code (backend/app, backend/tests, frontend/src, frontend/tests)
#   - Configuration files (requirements.txt, package.json, docker-compose.yml, etc.)
#   - Scripts (scripts/: setup, dev, test runners, deploy scripts)
#   - Sample data (sample-data/)
#   - Documentation (docs/: ARCHITECTURE.md, API.md, SETUP.md, DEPLOYMENT.md,
#                         GUARDRAILS.md, SECURITY.md, TESTING.md, SDD.md,
#                         requirements/edureka-project.pdf +
#                         README.md)
#   - Capstone overview (docs/capstone-project-overview.html)
#
# What is excluded (intentionally):
#   - artifacts/            — walkthrough videos, Playwright reports, and trace assets
#   - backend/.env          — contains real API keys / secrets
#   - .env/.env.local       — local environment files with secrets/tokens
#   - real env files       — backend/.env, .env.local, and deployment-specific env files
#   - private keys/certificates (*.pem, *.key, *.p12, *.pfx, *.crt)
#   - backend/.venv/        — recreated by setup.sh
#   - chroma_db/            — runtime vector DB data, not source (root and backend/)
#   - backend/uploads/      — runtime user-uploaded files, not source
#   - backend/__pycache__/  — compiled bytecode
#   - backend/.coverage     — generated test artefact
#   - backend/.pytest_cache/
#   - frontend/node_modules/ — reinstalled by npm install
#   - frontend/dist/        — build artefact, rebuilt by npm run build
#   - test-reports/         — generated HTML reports
#   - frontend/playwright-report/ and frontend/test-results/ — generated browser test artefacts
#   - coverage/, htmlcov/, .coverage* — generated coverage artefacts
#   - .vercel/              — local Vercel project metadata
#   - .git/                 — version control internals
#   - .claude/              — local Claude Code settings
#   - .specify/             — local spec-kit working directory
#   - assistant discovery folders (.agents/, .cursor/, .clinerules/, .roo/,
#                                  .windsurf/, .continue/) — local AI tooling
#   - .github/copilot-instructions.md — local AI assistant instructions
#   - CLAUDE.md/PENDING_TASKS.md/ONBOARDING.md — internal working notes, not submission material
#   - local IDE/editor folders and transient logs/caches

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_NAME="agentic-rag-poc-submission.zip"
OUTPUT_PATH="${SCRIPT_DIR}/${OUTPUT_NAME}"

echo "Packaging submission..."
echo "  Source : ${SCRIPT_DIR}"
echo "  Output : ${OUTPUT_PATH}"
echo ""

require_tool() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "ERROR: required tool not found: $1" >&2
        exit 1
    fi
}

require_tool zip
require_tool unzip
require_tool python3

# --- Pre-flight: warn if real uploads are present ---
UPLOAD_COUNT=$(find "${SCRIPT_DIR}/backend/uploads" -type f ! -name '.gitkeep' 2>/dev/null | wc -l | tr -d ' ')
if [ "${UPLOAD_COUNT}" -gt 0 ]; then
    echo "WARNING: backend/uploads/ contains ${UPLOAD_COUNT} runtime file(s)."
    echo "         These will be excluded from the zip automatically."
    echo "         To clean them: find backend/uploads -type f ! -name .gitkeep -delete"
    echo ""
fi

# --- Pre-flight: warn about local secret-bearing files that will be excluded ---
LOCAL_SECRET_FILES=$(find "${SCRIPT_DIR}" \
    \( -path "${SCRIPT_DIR}/.git" -o -path "${SCRIPT_DIR}/frontend/node_modules" -o -path "${SCRIPT_DIR}/backend/.venv" \) -prune -o \
    -type f \( \
        -name ".env" -o -name ".env.local" -o -name ".env.production" -o -name ".env.preview" -o \
        -name "*.pem" -o -name "*.key" -o \
        -name "*.p12" -o -name "*.pfx" -o -name "*.crt" -o -name "id_rsa" -o -name "id_ed25519" \
    \) -print)
if [ -n "${LOCAL_SECRET_FILES}" ]; then
    echo "NOTICE: local secret/certificate files were found and will be excluded:"
    printf '%s\n' "${LOCAL_SECRET_FILES}" | sed "s#${SCRIPT_DIR}/#  - #"
    echo ""
fi

# --- Remove any previous zip so we get a clean build ---
rm -f "${OUTPUT_PATH}"

cd "${SCRIPT_DIR}"

# Generate docs/README.md (Docsify homepage) — gitignored, must be created before zipping
echo "Generating docs/README.md from root README..."
sed 's|](docs/|](|g' README.md > docs/README.md

zip -r "${OUTPUT_PATH}" . \
    --exclude "*.DS_Store" \
    --exclude ".git/*" \
    --exclude ".git" \
    --exclude ".vercel/*" \
    --exclude ".vercel" \
    --exclude ".claude/*" \
    --exclude ".claude" \
    --exclude "*/.claude/*" \
    --exclude "*/.claude" \
    --exclude ".specify/*" \
    --exclude ".specify" \
    --exclude ".agents/*" \
    --exclude ".agents" \
    --exclude ".cursor/*" \
    --exclude ".cursor" \
    --exclude ".clinerules/*" \
    --exclude ".clinerules" \
    --exclude ".roo/*" \
    --exclude ".roo" \
    --exclude ".windsurf/*" \
    --exclude ".windsurf" \
    --exclude ".continue/*" \
    --exclude ".continue" \
    --exclude ".github/copilot-instructions.md" \
    --exclude "CLAUDE.md" \
    --exclude "PENDING_TASKS.md" \
    --exclude "ONBOARDING.md" \
    --exclude ".env*" \
    --exclude "backend/.env" \
    --exclude "*/.env" \
    --exclude "*/.env.local" \
    --exclude "*/.env.production" \
    --exclude "*/.env.preview" \
    --exclude "*/.env.development.local" \
    --exclude "*/.env.production.local" \
    --exclude "*/.env.test.local" \
    --exclude "*.pem" \
    --exclude "*.key" \
    --exclude "*.p12" \
    --exclude "*.pfx" \
    --exclude "*.crt" \
    --exclude "id_rsa" \
    --exclude "id_ed25519" \
    --exclude "backend/.venv/*" \
    --exclude "backend/.venv" \
    --exclude "chroma_db/*" \
    --exclude "chroma_db" \
    --exclude "backend/chroma_db/*" \
    --exclude "backend/chroma_db" \
    --exclude "backend/uploads/*" \
    --exclude "backend/.coverage*" \
    --exclude "backend/.pytest_cache/*" \
    --exclude "backend/.pytest_cache" \
    --exclude "backend/htmlcov/*" \
    --exclude "backend/htmlcov" \
    --exclude "*/__pycache__/*" \
    --exclude "*.pyc" \
    --exclude "*.pyo" \
    --exclude "frontend/node_modules/*" \
    --exclude "frontend/dist/*" \
    --exclude "frontend/playwright-report/*" \
    --exclude "frontend/playwright-report" \
    --exclude "frontend/test-results/*" \
    --exclude "frontend/test-results" \
    --exclude "node_modules/*" \
    --exclude "playwright-report/*" \
    --exclude "playwright-report" \
    --exclude "test-results/*" \
    --exclude "test-results" \
    --exclude "test-reports/*" \
    --exclude "test-reports" \
    --exclude "coverage/*" \
    --exclude "coverage" \
    --exclude "artifacts/*" \
    --exclude "artifacts" \
    --exclude "htmlcov/*" \
    --exclude "htmlcov" \
    --exclude ".coverage*" \
    --exclude ".pytest_cache/*" \
    --exclude ".pytest_cache" \
    --exclude ".benchmarks/*" \
    --exclude ".benchmarks" \
    --exclude "*/.benchmarks/*" \
    --exclude "*/.benchmarks" \
    --exclude ".mypy_cache/*" \
    --exclude ".mypy_cache" \
    --exclude ".ruff_cache/*" \
    --exclude ".ruff_cache" \
    --exclude ".cache/*" \
    --exclude ".cache" \
    --exclude ".idea/*" \
    --exclude ".idea" \
    --exclude ".vscode/*" \
    --exclude ".vscode" \
    --exclude "*.log" \
    --exclude "npm-debug.log*" \
    --exclude "yarn-debug.log*" \
    --exclude "yarn-error.log*" \
    --exclude "${OUTPUT_NAME}"

# Add the safe env template after the broad root .env* exclusion. The template
# contains placeholders only and is required by setup.sh.
zip -q "${OUTPUT_PATH}" backend/.env.example

echo ""
echo "Done. Submission zip created:"
echo "  ${OUTPUT_PATH}"
echo "  $(du -sh "${OUTPUT_PATH}" | cut -f1) on disk"
echo ""

# --- Verification checks ---
echo "Verification checks:"
ARCHIVE_LIST="$(mktemp)"
trap 'rm -f "${ARCHIVE_LIST}"' EXIT
unzip -Z1 "${OUTPUT_PATH}" > "${ARCHIVE_LIST}"

# Key source files
for f in \
    "docs/capstone-project-overview.html" \
    "docs/README.md" \
    "scripts/local/setup.sh" \
    "scripts/local/dev.sh" \
    "scripts/record-walkthrough.sh" \
    "scripts/remote/deploy-vercel.sh" \
    "docs/requirements/edureka-project.pdf" \
    "backend/app/agents/rag_agent.py" \
    "backend/app/rag/scanner.py" \
    "backend/app/rag/bm25.py" \
    "backend/app/config.py" \
    "backend/.env.example" \
    "docs/architecture/ARCHITECTURE.md" \
    "docs/security/SECURITY.md" \
    "docs/api/API.md" \
    "docs/project/CAPSTONE-AUDIT.md" \
    "frontend/tests/e2e/guest.spec.ts" \
    "frontend/tests/e2e/guardrails.spec.ts"; do
    if grep -qx "${f}" "${ARCHIVE_LIST}"; then
        echo "  [OK]   ${f}"
    else
        echo "  [MISS] ${f} — NOT FOUND in zip"
    fi
done


echo ""

# Exclusion checks (must NOT be present)
FAIL=0
for pat in \
    '(^|/)\.env$' \
    '(^|/)\.env\.(local|production|preview|development\.local|production\.local|test\.local)$' \
    '(^|/)\.vercel/' \
    '(^|/)backend/\.venv/' \
    '(^|/)frontend/node_modules/' \
    '(^|/)frontend/dist/' \
    '(^|/)frontend/playwright-report/' \
    '(^|/)frontend/test-results/' \
    '(^|/)test-reports/' \
    '(^|/)artifacts/' \
    '(^|/)chroma_db/' \
    '(^|/)\.claude/' \
    '(^|/)\.agents/' \
    '(^|/)\.cursor/' \
    '(^|/)\.clinerules/' \
    '(^|/)\.roo/' \
    '(^|/)\.windsurf/' \
    '(^|/)\.continue/' \
    '(^|/)\.github/copilot-instructions\.md$' \
    '(^|/)\.git/' \
    '(^|/)\.DS_Store$' \
    '\.(pem|key|p12|pfx|crt)$' \
    '(^|/)id_(rsa|ed25519)$' \
    '\.log$'; do
    if grep -Eq "${pat}" "${ARCHIVE_LIST}"; then
        echo "  [WARN] Sensitive/excluded path present: ${pat}"
        FAIL=1
    fi
done

# Check for user uploads (excluding .gitkeep)
if grep -E '(^|/)backend/uploads/' "${ARCHIVE_LIST}" | grep -qv ".gitkeep"; then
    echo "  [WARN] backend/uploads/ contains runtime files"
    FAIL=1
fi

# Scan extracted text files for real-looking secrets. Placeholder values and
# test fixtures are allowed; concrete local credentials are not.
SECRET_SCAN_OUTPUT=$(python3 - "${OUTPUT_PATH}" <<'PYEOF'
from __future__ import annotations

import re
import sys
import zipfile

archive = sys.argv[1]
text_suffixes = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".sh", ".yml",
    ".yaml", ".txt", ".cfg", ".ini", ".toml", ".env", ".html", ".css",
}

patterns = [
    ("OpenAI API key", re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{32,}")),
    ("Vercel token", re.compile(r"\b[A-Za-z0-9]{24,}_[A-Za-z0-9_-]{20,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b")),
]

allowed_fragments = (
    "<your-openai-api-key>",
    "sk-test",
    "sk-fake",
    "sk-proj-\" +",
    "\"sk-\" +",
    "'sk-' +",
    "OPENAI_API_KEY",
    # Deterministic test fixtures used in redaction unit tests — not real credentials
    "sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "MIIEpAIBAAKCAQEA...",
    "BEGIN EC PRIVATE KEY-----\ndata",
    "BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA",
)

findings: list[str] = []
with zipfile.ZipFile(archive) as zf:
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename
        if not any(name.endswith(suffix) for suffix in text_suffixes):
            continue
        if info.file_size > 1_000_000:
            continue
        try:
            text = zf.read(info).decode("utf-8", errors="ignore")
        except Exception:
            continue
        for label, pattern in patterns:
            # Private-key scan is skipped for test fixture files — fake keys are
            # deliberately embedded in redaction unit tests and are not real credentials.
            if label == "private key block" and "/tests/" in name:
                continue
            for match in pattern.finditer(text):
                line_start = text.rfind("\n", 0, match.start()) + 1
                line_end = text.find("\n", match.end())
                if line_end == -1:
                    line_end = len(text)
                line = text[line_start:line_end].strip()
                if any(fragment in line for fragment in allowed_fragments):
                    continue
                findings.append(f"{name}: {label}: {line[:160]}")

if findings:
    print("\n".join(findings))
    raise SystemExit(1)
PYEOF
) || {
    echo "  [WARN] Secret scan found real-looking sensitive values:"
    printf '%s\n' "${SECRET_SCAN_OUTPUT}" | sed 's/^/         /'
    FAIL=1
}

if [ "${FAIL}" -eq 0 ]; then
    echo "  [OK]   No secrets, local env files, runtime data, build artifacts, or user uploads detected"
else
    echo ""
    echo "ERROR: package verification failed; remove the flagged content and rerun."
    exit 1
fi

echo ""
echo "Contents summary:"
zip -sf "${OUTPUT_PATH}" | grep -E '\.(py|ts|tsx|js|json|md|sh|yml|yaml|txt|cfg|ini|toml|csv|xlsx|pdf|html)$' | \
    awk '{print "  " $0}' | head -80
echo ""
TOTAL=$(zip -sf "${OUTPUT_PATH}" | tail -1)
echo "  ${TOTAL}"

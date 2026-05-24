#!/usr/bin/env bash
# Record the capstone walkthrough video with the frontend Playwright recorder.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${SCRIPT_DIR}/frontend"

BASE_URL="${WALKTHROUGH_BASE_URL:-}"
USERNAME="${WALKTHROUGH_USERNAME:-}"
PASSWORD="${WALKTHROUGH_PASSWORD:-}"
UPLOAD_FILE="${WALKTHROUGH_UPLOAD_FILE:-}"
SLOW_MO_MS="${WALKTHROUGH_SLOW_MO_MS:-250}"
INTERACTIVE_SETTINGS="${WALKTHROUGH_INTERACTIVE_SETTINGS:-false}"
INTERACTIVE_TIMEOUT_MS="${WALKTHROUGH_INTERACTIVE_TIMEOUT_MS:-600000}"
ENV_LABEL="${WALKTHROUGH_ENV:-}"
HEADED=false
DRY_RUN=false
PUBLISH="${WALKTHROUGH_PUBLISH:-true}"
# GitHub token: WALKTHROUGH_GH_TOKEN → GH_TOKEN → GITHUB_TOKEN (CI standard)
_RESOLVED_GH_TOKEN="${WALKTHROUGH_GH_TOKEN:-${GH_TOKEN:-${GITHUB_TOKEN:-}}}"

usage() {
    cat <<'EOF'
Usage:
  scripts/record-walkthrough.sh --url <app-url> [options]

Prerequisites (run once before recording):
  bash scripts/local/setup.sh

  The setup script will:
    • Detect Python 3.11–3.13 and create backend/.venv
    • Install backend Python dependencies (pip install -r requirements-dev.txt)
    • Create backend/.env from .env.example (set OPENAI_API_KEY inside)
    • Install frontend dependencies (npm ci)
    • Optionally generate sample data files for upload

  After setup, start both servers before recording a local URL:
    Terminal 1:  cd backend && source .venv/bin/activate
                 uvicorn app.main:app --reload --port 8000
    Terminal 2:  cd frontend && npm run dev
    App URL:     http://localhost:5173

Options:
  --url <url>                    Local or deployed app URL to record.
  --env local|remote             Tag artifacts as local or remote. Auto-detected
                                 from --url when omitted (localhost/127.0.0.1 → local,
                                 everything else → remote).
  --username <name>              Admin username. When provided with --password,
                                 both guest and admin walkthroughs are recorded.
                                 Omit to record guest mode only.
  --password <password>          Admin password. Never printed.
  --upload-file <path>           Optional file to upload during the walkthrough.
  --slow-mo-ms <number>          Browser action delay in milliseconds. Default: 250.
  --interactive-settings         Pause so the user can update Settings before recording continues.
  --timeout-ms <number>          Interactive settings timeout. Default: 600000.
  --headed                       Show the browser while recording.
  --gh-token <token>             GitHub Personal Access Token (PAT) with repo scope, used to
                                 upload walkthrough videos to GitHub Releases without gh auth login.
                                 Also accepted via WALKTHROUGH_GH_TOKEN, GH_TOKEN, or GITHUB_TOKEN.
  --dry-run                      Validate inputs and print the safe execution summary only.
  --help                         Show this help.

Artifacts are saved to:
  artifacts/walkthrough/local/   — when --env local (or localhost URL)
  artifacts/walkthrough/remote/  — when --env remote (or deployed URL)

After a successful recording the script automatically publishes videos to
  docs/walkthrough/{local,remote}/
and commits + pushes to origin, triggering GitHub Pages deployment.
Pass --no-publish to skip this step.

Equivalent environment variables:
  WALKTHROUGH_BASE_URL, WALKTHROUGH_ENV, WALKTHROUGH_USERNAME, WALKTHROUGH_PASSWORD,
  WALKTHROUGH_UPLOAD_FILE, WALKTHROUGH_SLOW_MO_MS,
  WALKTHROUGH_INTERACTIVE_SETTINGS, WALKTHROUGH_INTERACTIVE_TIMEOUT_MS,
  WALKTHROUGH_PUBLISH (set to 'false' to skip GitHub Pages publish)
EOF
}

die() {
    echo "ERROR: $1" >&2
    exit 1
}

require_file() {
    [[ -f "$1" ]] || die "required file not found: $1"
}

# ── GitHub Pages video publish helpers ────────────────────────────────────────
#
# Videos are uploaded to a GitHub Release (tag: walkthrough-local / walkthrough-remote)
# as release assets — they are NEVER committed to the git repository.
# Only docs/walkthrough/index.html, _meta.json, README.md, and WALKTHROUGH-VIDEO.md
# are committed (tiny text/HTML files).  The gallery HTML embeds the permanent
# release asset download URLs directly in <video> tags.
#
# Authentication (token priority): WALKTHROUGH_GH_TOKEN > GH_TOKEN > GITHUB_TOKEN
#   • If gh CLI is installed the token is forwarded via GH_TOKEN env var.
#   • Without gh CLI the script falls back to the GitHub REST API via curl.
# Generate a PAT at: https://github.com/settings/tokens  (scope: repo)

_GH_REPO="dev-enthusiast-84/AILabs"
_GH_PAGES_GALLERY="https://dev-enthusiast-84.github.io/AILabs/walkthrough/"
_RELEASE_BASE="https://github.com/${_GH_REPO}/releases/download"
_GH_API="https://api.github.com"

# ── curl helpers (used when gh CLI is absent) ──────────────────────────────────

# Thin wrapper: GitHub REST API call via curl.
# Usage: _gh_curl <METHOD> <url> <token> [extra curl args...]
_gh_curl() {
    local method="$1" url="$2" token="$3"
    shift 3
    curl -sf -X "$method" \
        -H "Authorization: Bearer ${token}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "$@" "$url"
}

# Return the numeric release ID for $tag, or "" if it doesn't exist yet.
_release_id_curl() {
    local token="$1" tag="$2"
    _gh_curl GET "${_GH_API}/repos/${_GH_REPO}/releases/tags/${tag}" "$token" 2>/dev/null \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))" 2>/dev/null \
        || true
}

# Create a pre-release with the given tag; return its numeric ID.
_create_release_curl() {
    local token="$1" tag="$2" title="$3" notes="$4"
    local payload
    payload=$(python3 -c "
import json, sys
print(json.dumps({'tag_name': sys.argv[1], 'name': sys.argv[2],
                  'body': sys.argv[3], 'prerelease': True}))" \
        "$tag" "$title" "$notes")
    _gh_curl POST "${_GH_API}/repos/${_GH_REPO}/releases" "$token" \
        -H "Content-Type: application/json" -d "$payload" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])"
}

# Delete an existing release asset by name (enables clobber semantics).
_delete_asset_if_exists_curl() {
    local token="$1" release_id="$2" asset_name="$3"
    local asset_id
    asset_id=$(_gh_curl GET \
        "${_GH_API}/repos/${_GH_REPO}/releases/${release_id}/assets" "$token" 2>/dev/null \
        | python3 -c "
import json,sys
assets=json.load(sys.stdin)
name=sys.argv[1]
for a in assets:
    if a['name']==name: print(a['id']); break
" "$asset_name" 2>/dev/null || true)
    if [[ -n "$asset_id" ]]; then
        _gh_curl DELETE \
            "${_GH_API}/repos/${_GH_REPO}/releases/assets/${asset_id}" \
            "$token" > /dev/null 2>&1 || true
    fi
}

# Upload one .webm file to the release; return the browser_download_url.
_upload_asset_curl() {
    local token="$1" release_id="$2" filepath="$3"
    local asset_name
    asset_name="$(basename "$filepath")"
    _delete_asset_if_exists_curl "$token" "$release_id" "$asset_name"
    local upload_url="${_GH_API}/repos/${_GH_REPO}/releases/${release_id}/assets?name=${asset_name}"
    # GitHub's upload endpoint requires uploads.github.com but the API returns it;
    # construct directly for simplicity.
    local up_url="https://uploads.github.com/repos/${_GH_REPO}/releases/${release_id}/assets?name=${asset_name}"
    curl -sf -X POST \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: video/webm" \
        --data-binary "@${filepath}" \
        "$up_url" \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('browser_download_url',''))" \
        2>/dev/null || true
}

# ── Main upload orchestrator ───────────────────────────────────────────────────

# Rename and upload .webm files to the matching GitHub Release.
# Prints uploaded asset basenames, one per line, to stdout.
_upload_release_assets() {
    local env_label="$1"
    local src_results="$2"
    local token="$3"
    local tag="walkthrough-${env_label}"
    local tmpdir
    tmpdir="$(mktemp -d)"

    # Rename Playwright output files to friendly names in a temp dir.
    local uploaded=()
    while IFS= read -r -d '' video; do
        local test_dir asset_name
        test_dir="$(basename "$(dirname "$video")")"
        if [[ "$test_dir" == *admin* ]]; then
            asset_name="admin-walkthrough.webm"
        else
            asset_name="guest-walkthrough.webm"
        fi
        cp "$video" "${tmpdir}/${asset_name}"
        uploaded+=("${tmpdir}/${asset_name}")
    done < <(find "$src_results" -maxdepth 2 -name "video.webm" -print0 2>/dev/null)

    if [[ ${#uploaded[@]} -eq 0 ]]; then
        echo "  No .webm videos found in ${src_results}" >&2
        rm -rf "$tmpdir"
        return 1
    fi

    local release_title release_notes
    release_notes="Auto-generated demo recordings. Gallery: ${_GH_PAGES_GALLERY}"
    if [[ "$env_label" == "remote" ]]; then
        release_title="Walkthrough Demo — Deployed App"
    else
        release_title="Walkthrough Demo — Local Stack"
    fi

    if command -v gh &>/dev/null; then
        # ── Path A: gh CLI + token (no interactive login needed) ──────────────
        if GH_TOKEN="$token" gh release view "$tag" \
                --repo "$_GH_REPO" &>/dev/null 2>&1; then
            echo "  Uploading to existing release '${tag}' via gh CLI ..." >&2
            GH_TOKEN="$token" gh release upload "$tag" "${uploaded[@]}" \
                --repo "$_GH_REPO" --clobber >&2
        else
            echo "  Creating release '${tag}' via gh CLI ..." >&2
            GH_TOKEN="$token" gh release create "$tag" \
                --title "$release_title" \
                --notes "$release_notes" \
                --prerelease \
                --repo "$_GH_REPO" \
                "${uploaded[@]}" >&2
        fi
    else
        # ── Path B: pure curl + GitHub REST API (no gh CLI required) ──────────
        echo "  gh CLI not found — using GitHub REST API (curl) ..." >&2
        local release_id
        release_id=$(_release_id_curl "$token" "$tag")
        if [[ -z "$release_id" ]]; then
            echo "  Creating release '${tag}' via REST API ..." >&2
            release_id=$(_create_release_curl "$token" "$tag" "$release_title" "$release_notes")
        else
            echo "  Uploading to existing release '${tag}' via REST API ..." >&2
        fi
        for filepath in "${uploaded[@]}"; do
            local dl_url
            dl_url=$(_upload_asset_curl "$token" "$release_id" "$filepath")
            echo "  Asset uploaded: ${dl_url}" >&2
        done
    fi

    # Stdout: only asset basenames (consumed by _publish_videos via $(...)).
    for f in "${uploaded[@]}"; do
        echo "$(basename "$f")"
    done

    rm -rf "$tmpdir"
}

# (Re)generate docs/walkthrough/index.html using release asset URLs from _meta.json.
_generate_walkthrough_html() {
    local docs_walk="${SCRIPT_DIR}/docs/walkthrough"
    local meta_file="${docs_walk}/_meta.json"

    local remote_url="" local_url="" remote_assets="" local_assets=""
    if [[ -f "$meta_file" ]]; then
        remote_url=$(python3    -c "import json; d=json.load(open('${meta_file}')); print(d.get('remote_url',''))"    2>/dev/null || true)
        local_url=$(python3     -c "import json; d=json.load(open('${meta_file}')); print(d.get('local_url',''))"     2>/dev/null || true)
        remote_assets=$(python3 -c "import json; d=json.load(open('${meta_file}')); print(' '.join(d.get('remote_assets',[])))" 2>/dev/null || true)
        local_assets=$(python3  -c "import json; d=json.load(open('${meta_file}')); print(' '.join(d.get('local_assets',[])))"  2>/dev/null || true)
    fi

    local sections_html=""
    for env in local remote; do
        local app_url="" assets_str=""
        [[ "$env" == "local" ]]  && { app_url="$local_url";  assets_str="$local_assets";  }
        [[ "$env" == "remote" ]] && { app_url="$remote_url"; assets_str="$remote_assets"; }
        [[ -z "$assets_str" ]] && continue

        local heading="Local Stack"
        [[ "$env" == "remote" ]] && heading="Deployed App (Vercel)"

        local link_html=""
        [[ -n "$app_url" ]] && \
            link_html="<a href=\"${app_url}\" target=\"_blank\" rel=\"noopener noreferrer\">Open live app &#x2197;</a>"

        local cards_html="" tag="${_RELEASE_BASE}/walkthrough-${env}"
        for asset_name in $assets_str; do
            local vname vtitle video_url
            vname="${asset_name%.webm}"
            vtitle=$(echo "$vname" | tr '-' ' ' | \
                     awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2); print}')
            video_url="${tag}/${asset_name}"
            cards_html+="
          <div class=\"card\">
            <h3>${vtitle}</h3>
            <video controls preload=\"metadata\" width=\"100%\">
              <source src=\"${video_url}\" type=\"video/webm\" />
              <p>WebM not supported. <a href=\"${video_url}\">Download video</a></p>
            </video>
            <p class=\"dl\"><a href=\"${video_url}\">&#x2B07; Download ${asset_name}</a></p>
          </div>"
        done

        [[ -z "$cards_html" ]] && continue
        sections_html+="
    <section>
      <h2>${heading}${link_html:+ }${link_html}</h2>
      <div class=\"grid\">${cards_html}
      </div>
    </section>"
    done

    mkdir -p "$docs_walk"
    cat > "${docs_walk}/index.html" <<HTMLEOF
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Walkthrough Videos — Agentic RAG</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, -apple-system, sans-serif; background: #f8fafc; color: #0f172a; line-height: 1.6; }
    header { background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 45%, #1e40af 100%); color: #fff; padding: 2rem 2.5rem; }
    header h1 { font-size: 1.75rem; margin-bottom: .3rem; }
    header p { opacity: .8; font-size: .95rem; }
    header a { color: #93c5fd; }
    main { max-width: 1100px; margin: 2rem auto; padding: 0 1.5rem 3rem; }
    section { margin-bottom: 3rem; }
    h2 { display: flex; align-items: center; flex-wrap: wrap; gap: 1rem;
         font-size: 1.25rem; color: #1e3a5f; border-bottom: 2px solid #dbeafe;
         padding-bottom: .5rem; margin-bottom: 1.5rem; }
    h2 a { font-size: .825rem; background: #2563eb; color: #fff;
            padding: .2rem .7rem; border-radius: 4px; text-decoration: none; }
    h2 a:hover { background: #1d4ed8; }
    h3 { font-size: .95rem; margin-bottom: .5rem; color: #374151; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 1.5rem; }
    .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
            padding: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
    video { display: block; border-radius: 4px; max-height: 400px; }
    .dl { margin-top: .5rem; font-size: .8rem; }
    .dl a { color: #2563eb; }
    footer { text-align: center; padding: 1.5rem; color: #64748b; font-size: .875rem; }
    footer a { color: #2563eb; }
  </style>
</head>
<body>
  <header>
    <h1>&#x1F3A5; Agentic RAG — Walkthrough Videos</h1>
    <p>Enterprise document Q&amp;A demo &middot;
       <a href="../index.html">Full Docs &#x2197;</a> &middot;
       <a href="https://github.com/${_GH_REPO}">GitHub &#x2197;</a></p>
  </header>
  <main>${sections_html}
  </main>
  <footer>
    Videos hosted on <a href="https://github.com/${_GH_REPO}/releases">GitHub Releases</a> &mdash;
    gallery published to <a href="${_GH_PAGES_GALLERY}">GitHub Pages</a> by
    <code>scripts/record-walkthrough.sh</code>
  </footer>
</body>
</html>
HTMLEOF
    echo "  Generated: docs/walkthrough/index.html"
}

# Idempotently update the <!-- REMOTE-APP-URL --> marker in README.md.
_update_readme_demo_url() {
    local url="$1"
    local readme="${SCRIPT_DIR}/README.md"

    if grep -q "REMOTE-APP-URL" "$readme"; then
        python3 - "$readme" "$url" <<'PYEOF'
import sys, re
path, url = sys.argv[1], sys.argv[2]
content = open(path).read()
updated = re.sub(
    r'<!-- REMOTE-APP-URL -->.*?<!-- /REMOTE-APP-URL -->',
    f'<!-- REMOTE-APP-URL -->[Live App ↗]({url})<!-- /REMOTE-APP-URL -->',
    content,
    flags=re.DOTALL
)
if updated != content:
    open(path, 'w').write(updated)
    print(f"  Updated README.md Live Demo URL: {url}")
else:
    print("  README.md Live Demo URL unchanged.")
PYEOF
    else
        echo "  README.md has no <!-- REMOTE-APP-URL --> marker — skipping URL update." >&2
    fi
}

# Upload videos to GitHub Releases, regenerate gallery HTML, commit+push docs.
_publish_videos() {
    local env_label="$1"
    local app_url="$2"
    local docs_walk="${SCRIPT_DIR}/docs/walkthrough"
    local src_results="${SCRIPT_DIR}/artifacts/walkthrough/${env_label}/results"

    echo ""
    echo "── Publishing ${env_label} walkthrough videos ───────────────────────────────"

    # Require a GitHub token (PAT with repo scope).
    local token="$_RESOLVED_GH_TOKEN"
    if [[ -z "$token" ]]; then
        echo "  ✗ GitHub token not set. Provide one of:" >&2
        echo "      --gh-token <PAT>                   (command-line)" >&2
        echo "      export WALKTHROUGH_GH_TOKEN=<PAT>  (env var, project-specific)" >&2
        echo "      export GH_TOKEN=<PAT>              (env var, gh CLI standard)" >&2
        echo "  Generate a PAT at: https://github.com/settings/tokens  (scope: repo)" >&2
        echo "  Skipping publish — videos remain in artifacts/walkthrough/${env_label}/" >&2
        return 0
    fi

    # Upload to GitHub Release (not committed to git).
    local uploaded_names
    uploaded_names=$(_upload_release_assets "$env_label" "$src_results" "$token") || {
        echo "  No videos uploaded — skipping gallery update." >&2
        return 0
    }

    echo "  Uploaded to GitHub Release 'walkthrough-${env_label}':"
    while IFS= read -r name; do
        [[ -n "$name" ]] && echo "    ${_RELEASE_BASE}/walkthrough-${env_label}/${name}"
    done <<< "$uploaded_names"

    # Update _meta.json with app URL and asset list (for HTML generation).
    mkdir -p "$docs_walk"
    python3 - "${docs_walk}/_meta.json" "$env_label" "$app_url" "$uploaded_names" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone
path, env, url = sys.argv[1], sys.argv[2], sys.argv[3]
assets = [n for n in sys.argv[4].splitlines() if n.strip()]
meta = {}
if os.path.exists(path):
    try:
        meta = json.loads(open(path).read())
    except Exception:
        pass
meta[f'{env}_url'] = url
meta[f'{env}_assets'] = assets
meta[f'last_recorded_{env}'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
open(path, 'w').write(json.dumps(meta, indent=2) + '\n')
print(f"  Updated _meta.json ({env}_assets={assets})")
PYEOF

    # Regenerate gallery HTML (references release asset URLs, no video files in git).
    _generate_walkthrough_html

    # Update README with remote app URL (idempotent).
    if [[ "$env_label" == "remote" && -n "$app_url" ]]; then
        _update_readme_demo_url "$app_url"
    fi

    # Commit only the lightweight docs (HTML + JSON + MD) — no binary video files.
    if ! git -C "$SCRIPT_DIR" rev-parse --is-inside-work-tree &>/dev/null; then
        echo "  Not inside a git repo — skipping docs commit." >&2
        return 0
    fi

    git -C "$SCRIPT_DIR" add \
        "docs/walkthrough/" \
        "docs/WALKTHROUGH-VIDEO.md" \
        "README.md" 2>/dev/null || true

    if git -C "$SCRIPT_DIR" diff --cached --quiet 2>/dev/null; then
        echo "  docs/walkthrough/ already up-to-date — nothing to commit."
    else
        git -C "$SCRIPT_DIR" commit \
            -m "walkthrough: update ${env_label} gallery page $(date -u '+%Y-%m-%d')"
        echo ""
        echo "  Pushing docs update to origin ..."
        local branch
        branch="$(git -C "$SCRIPT_DIR" rev-parse --abbrev-ref HEAD)"
        if git -C "$SCRIPT_DIR" push origin "$branch"; then
            echo "  ✓ Pushed — deploy-docs.yml will refresh GitHub Pages."
            echo "  Gallery: ${_GH_PAGES_GALLERY}"
        else
            echo "  ✗ Push failed — commit created locally. Run: git push origin ${branch}"
        fi
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --url)
            [[ $# -ge 2 ]] || die "--url requires a value"
            BASE_URL="$2"
            shift 2
            ;;
        --username)
            [[ $# -ge 2 ]] || die "--username requires a value"
            USERNAME="$2"
            shift 2
            ;;
        --password)
            [[ $# -ge 2 ]] || die "--password requires a value"
            PASSWORD="$2"
            shift 2
            ;;
        --upload-file)
            [[ $# -ge 2 ]] || die "--upload-file requires a value"
            UPLOAD_FILE="$2"
            shift 2
            ;;
        --env)
            [[ $# -ge 2 ]] || die "--env requires a value (local or remote)"
            ENV_LABEL="$2"
            [[ "$ENV_LABEL" == "local" || "$ENV_LABEL" == "remote" ]] || die "--env must be 'local' or 'remote'"
            shift 2
            ;;
        --slow-mo-ms)
            [[ $# -ge 2 ]] || die "--slow-mo-ms requires a value"
            SLOW_MO_MS="$2"
            shift 2
            ;;
        --interactive-settings)
            INTERACTIVE_SETTINGS=true
            shift
            ;;
        --timeout-ms)
            [[ $# -ge 2 ]] || die "--timeout-ms requires a value"
            INTERACTIVE_TIMEOUT_MS="$2"
            shift 2
            ;;
        --headed)
            HEADED=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --gh-token)
            [[ $# -ge 2 ]] || die "--gh-token requires a value"
            _RESOLVED_GH_TOKEN="$2"
            shift 2
            ;;
        --no-publish)
            PUBLISH=false
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            die "unknown option: $1"
            ;;
    esac
done

[[ -n "$BASE_URL" ]] || die "set --url or WALKTHROUGH_BASE_URL"
[[ "$BASE_URL" =~ ^https?:// ]] || die "--url must start with http:// or https://"
[[ "$SLOW_MO_MS" =~ ^[0-9]+$ ]] || die "--slow-mo-ms must be a non-negative integer"
[[ "$INTERACTIVE_TIMEOUT_MS" =~ ^[0-9]+$ ]] || die "--timeout-ms must be a non-negative integer"

# Auto-detect env label from URL when not explicitly set
if [[ -z "$ENV_LABEL" ]]; then
    if [[ "$BASE_URL" =~ ^https?://(localhost|127\.0\.0\.1)(:[0-9]+)?(/|$) ]]; then
        ENV_LABEL="local"
    else
        ENV_LABEL="remote"
    fi
fi

# ── Prerequisites pre-flight ──────────────────────────────────────────────────
SETUP_NEEDED=false
if [[ ! -d "${SCRIPT_DIR}/backend/.venv" ]]; then
    echo "MISSING: backend/.venv — Python virtual environment not found." >&2
    SETUP_NEEDED=true
fi
if [[ ! -f "${SCRIPT_DIR}/backend/.env" ]]; then
    echo "MISSING: backend/.env — backend environment file not found." >&2
    SETUP_NEEDED=true
fi
if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    echo "MISSING: frontend/node_modules — frontend dependencies not installed." >&2
    SETUP_NEEDED=true
fi
if [[ "$SETUP_NEEDED" == true ]]; then
    echo "" >&2
    echo "Run the setup script first, then re-run the walkthrough recorder:" >&2
    echo "  bash scripts/local/setup.sh" >&2
    echo "" >&2
    exit 1
fi
# ─────────────────────────────────────────────────────────────────────────────

require_file "${FRONTEND_DIR}/package.json"
require_file "${FRONTEND_DIR}/playwright.walkthrough.config.ts"
require_file "${FRONTEND_DIR}/tests/walkthrough/capstone-walkthrough.spec.ts"

command -v npm >/dev/null 2>&1 || die "npm is required to run the walkthrough recorder"

# --interactive-settings requires a visible browser window.
# Auto-enable --headed and tell the user so there is no silent hang.
if [[ "$INTERACTIVE_SETTINGS" == true && "$HEADED" == false ]]; then
    echo "NOTE: --interactive-settings requires a visible browser. Enabling --headed automatically."
    HEADED=true
fi

MODE="guest only"
if [[ -n "$USERNAME" || -n "$PASSWORD" ]]; then
    [[ -n "$USERNAME" && -n "$PASSWORD" ]] || die "provide both --username and --password for admin mode"
    MODE="guest + admin"
fi

if [[ -n "$UPLOAD_FILE" ]]; then
    [[ -f "$UPLOAD_FILE" ]] || die "upload file not found: $UPLOAD_FILE"
    UPLOAD_FILE="$(cd "$(dirname "$UPLOAD_FILE")" && pwd)/$(basename "$UPLOAD_FILE")"
fi

echo "Walkthrough recorder"
echo "  URL        : ${BASE_URL}"
echo "  Env        : ${ENV_LABEL}"
echo "  Mode       : ${MODE}"
echo "  Browser    : $([[ "$HEADED" == true ]] && echo headed || echo headless)"
echo "  Settings   : $([[ "$INTERACTIVE_SETTINGS" == true ]] && echo interactive || echo automatic)"
echo "  Artifacts  : artifacts/walkthrough/${ENV_LABEL}/"
if [[ -n "$UPLOAD_FILE" ]]; then
    echo "  Upload file: ${UPLOAD_FILE}"
fi
echo ""

CMD=(npm run walkthrough:record)
if [[ "$HEADED" == true ]]; then
    CMD+=(-- --headed)
fi

if [[ "$DRY_RUN" == true ]]; then
    echo "Dry run only. Would run from frontend/: ${CMD[*]}"
    exit 0
fi

cd "$FRONTEND_DIR"

export WALKTHROUGH_BASE_URL="$BASE_URL"
export WALKTHROUGH_ENV="$ENV_LABEL"
export WALKTHROUGH_SLOW_MO_MS="$SLOW_MO_MS"
export WALKTHROUGH_INTERACTIVE_SETTINGS="$INTERACTIVE_SETTINGS"
export WALKTHROUGH_INTERACTIVE_TIMEOUT_MS="$INTERACTIVE_TIMEOUT_MS"

# Export credentials when provided; guest test ignores them, admin test uses them.
if [[ -n "$USERNAME" ]]; then
    export WALKTHROUGH_USERNAME="$USERNAME"
    export WALKTHROUGH_PASSWORD="$PASSWORD"
else
    unset WALKTHROUGH_USERNAME
    unset WALKTHROUGH_PASSWORD
fi

if [[ -n "$UPLOAD_FILE" ]]; then
    export WALKTHROUGH_UPLOAD_FILE="$UPLOAD_FILE"
else
    unset WALKTHROUGH_UPLOAD_FILE
fi

"${CMD[@]}"

if [[ "$PUBLISH" == true ]]; then
    _publish_videos "$ENV_LABEL" "$BASE_URL"
else
    echo ""
    echo "Publish skipped (--no-publish). To publish manually:"
    echo "  bash scripts/record-walkthrough.sh --url ${BASE_URL} --dry-run"
fi

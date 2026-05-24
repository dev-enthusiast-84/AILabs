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
HEADED=true
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

# Always (re)generate docs/walkthrough/index.html from _meta.json.
# Paths are derived from the fixed release tag + filename pattern so they never
# drift between re-recordings.  The script always overwrites the file so that
# the embed URLs are guaranteed identical to what was actually published.
_generate_walkthrough_html() {
    local docs_walk="${SCRIPT_DIR}/docs/walkthrough"
    local meta_file="${docs_walk}/_meta.json"
    local html_file="${docs_walk}/index.html"

    mkdir -p "$docs_walk"

    python3 - "$html_file" "$meta_file" \
              "$_RELEASE_BASE" "$_GH_REPO" "$_GH_PAGES_GALLERY" <<'PYEOF'
import json, os, sys

html_path, meta_path, release_base, gh_repo, gallery_url = sys.argv[1:6]

meta = {}
if os.path.exists(meta_path):
    try:
        meta = json.load(open(meta_path))
    except Exception:
        pass

local_assets  = set(meta.get('local_assets',  []))
remote_assets = set(meta.get('remote_assets', []))
local_url     = meta.get('local_url',  'http://localhost:5173')
remote_url    = meta.get('remote_url', 'https://agenticai-rag-poc.vercel.app')

FNAMES = ('guest-walkthrough.webm', 'admin-walkthrough.webm')

def slot(env, fname, assets):
    role      = 'Guest' if 'guest' in fname else 'Admin'
    icon      = '&#x1F464;' if role == 'Guest' else '&#x1F511;'
    badge_cls = 'guest' if role == 'Guest' else 'admin'
    note      = 'No login needed' if role == 'Guest' else 'Login required'
    src       = f'{release_base}/walkthrough-{env}/{fname}'
    active    = fname in assets
    ph_attr   = '' if active else '\n               data-placeholder="true"'
    ov_cls    = 'video-overlay clickable' if active else 'video-overlay'
    ov_role   = 'role="button" tabindex="0"' if active else 'aria-hidden="true"'
    play_dim  = '' if active else ' style="opacity:.3"'
    body      = (
        '<div class="ov-label">Click to watch</div>'
        '<div class="ov-progress-wrap"><div class="ov-progress-fill"></div></div>'
        '<div class="ov-progress-pct"></div>'
    ) if active else (
        '<div class="ov-placeholder-msg">'
        '<div class="ov-main">Recording not yet generated</div>'
        '<div class="ov-sub">Run the command below to produce this video</div>'
        '</div>'
    )
    return f'''\
        <div class="video-slot">
          <div class="slot-label">{icon} {role} Walkthrough
            <span class="role-badge {badge_cls}">{note}</span></div>
          <div class="video-wrap"
               data-src="{src}"
               data-filename="{fname}"{ph_attr}>
            <video controls preload="none"></video>
            <div class="{ov_cls}" {ov_role}>
              <div class="ov-play-btn"{play_dim}>&#9654;</div>
              {body}
            </div>
          </div>
        </div>'''

def env_col(env, app_url, badge_label, badge_cls, assets, local_cmd_note, pw_note):
    icon   = '&#x1F4BB;' if env == 'local' else '&#x1F310;'
    title  = 'Local Demo'   if env == 'local' else 'Live Demo'
    url_a  = f'<a href="{app_url}" target="_blank" rel="noopener noreferrer">{app_url.split("//")[1]}</a>'
    slots  = '\n'.join(slot(env, f, assets) for f in FNAMES)
    cmd_pw = '&lt;password from backend/.env&gt;' if env == 'local' else '&lt;password from Vercel env&gt;'
    return f'''\
    <section class="env-col" aria-labelledby="{env}-heading">
      <div class="env-head">
        <span class="env-icon">{icon}</span>
        <h2 class="env-title" id="{env}-heading">{title}</h2>
        <span class="badge {badge_cls}">{badge_label}</span>
      </div>
      <div class="env-url-strip">
        <span class="url-dot"></span>{url_a}
      </div>
      <div class="video-slots">
{slots}
      </div>
      <div class="record-section">
        <div class="record-label">Record command</div>
        <div class="record-cmd"><span class="cmd-comment"># Records both guest + admin walkthrough videos</span>
bash scripts/record-walkthrough.sh \\
  --url {app_url} \\
  --username admin \\
  --password {cmd_pw}</div>
      </div>
    </section>'''

cols = '\n'.join([
    env_col('local',  local_url,  'LOCALHOST',     'badge',         local_assets,  'npm run dev', 'backend/.env'),
    env_col('remote', remote_url, '&#x26A1; VERCEL', 'badge badge-vercel', remote_assets, 'Vercel URL',   'Vercel env'),
])

HTML = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Demo Recordings &#x2014; Agentic RAG</title>
  <style>
    :root{{--bg:#FAF6EE;--surface:#F2E8D0;--surface2:#EDE0C4;--border:rgba(139,103,20,.16);--border-hi:rgba(139,103,20,.32);--gold:#8B6914;--sage:#4C7A4C;--tan:#C4A46B;--text:#2C1A08;--text-dim:#6B5240;--text-soft:#8B7355;--grad:linear-gradient(135deg,#8B6914,#C4A46B);--r:10px;--r-sm:7px}}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    html{{font-size:14px;scroll-behavior:smooth}}
    body{{font-family:'Inter','Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);line-height:1.6;min-height:100vh}}
    .page{{max-width:1020px;margin:24px auto 48px;border-radius:16px;overflow:hidden;border:1px solid var(--border-hi);box-shadow:0 24px 64px rgba(60,40,15,.18)}}
    .demo-header{{background:var(--surface);padding:28px 36px 22px;border-bottom:1px solid var(--border);position:relative;overflow:hidden}}
    .demo-header::before{{content:'';position:absolute;inset:0;background-image:radial-gradient(circle,rgba(196,164,107,.2) 1px,transparent 1px);background-size:26px 26px;mask-image:linear-gradient(to bottom,transparent,rgba(0,0,0,.35) 50%,transparent);pointer-events:none}}
    .header-inner{{position:relative;z-index:1}}
    .eyebrow{{display:inline-flex;align-items:center;gap:7px;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--gold);background:rgba(139,103,20,.1);border:1px solid rgba(139,103,20,.22);border-radius:20px;padding:4px 12px;margin-bottom:12px}}
    .eyebrow-dot{{width:6px;height:6px;border-radius:50%;background:var(--gold);animation:pulse 2.2s ease-in-out infinite;flex-shrink:0}}
    @keyframes pulse{{0%,100%{{opacity:1;transform:scale(1)}}50%{{opacity:.4;transform:scale(.7)}}}}
    .demo-header h1{{font-size:22px;font-weight:900;background:var(--grad);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin-bottom:8px}}
    .header-links{{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}}
    .hlink{{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:var(--text-dim);text-decoration:none;background:rgba(139,103,20,.06);border:1px solid var(--border);border-radius:6px;padding:4px 10px;transition:border-color .15s,color .15s}}
    .hlink:hover{{border-color:var(--border-hi);color:var(--text)}}
    .hlink.hl-live{{color:var(--sage);border-color:rgba(76,122,76,.3);background:rgba(76,122,76,.08)}}
    .demo-grid{{display:grid;grid-template-columns:1fr 1fr}}
    .env-col{{padding:22px 24px 24px;border-right:1px solid var(--border)}}
    .env-col:last-child{{border-right:none}}
    .env-head{{display:flex;align-items:center;gap:9px;margin-bottom:12px}}
    .env-icon{{font-size:17px;line-height:1}}
    .env-title{{font-size:13.5px;font-weight:800;color:var(--text);flex:1}}
    .badge{{font-size:9px;font-weight:800;letter-spacing:.1em;text-transform:uppercase;padding:3px 9px;border-radius:20px;background:var(--text);color:var(--bg)}}
    .badge-vercel{{background:linear-gradient(135deg,#111 0%,#2a2a2a 100%)}}
    .env-url-strip{{display:flex;align-items:center;gap:7px;background:rgba(139,103,20,.06);border:1px solid var(--border);border-radius:var(--r-sm);padding:6px 11px;margin-bottom:14px;font-size:11px}}
    .url-dot{{width:6px;height:6px;border-radius:50%;background:var(--sage);box-shadow:0 0 6px rgba(76,122,76,.7);flex-shrink:0;animation:pulse 2s ease-in-out infinite}}
    .env-url-strip a{{color:var(--gold);font-weight:600;text-decoration:none}}
    .env-url-strip a:hover{{text-decoration:underline}}
    .video-slots{{display:flex;flex-direction:column;gap:12px;margin-bottom:16px}}
    .video-slot{{border:1px solid var(--border);border-radius:var(--r-sm);overflow:hidden;background:var(--surface)}}
    .slot-label{{display:flex;align-items:center;gap:7px;padding:7px 12px;background:var(--surface2);border-bottom:1px solid var(--border);font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:var(--text-dim)}}
    .role-badge{{margin-left:auto;font-size:9px;font-weight:700;padding:2px 7px;border-radius:10px;text-transform:uppercase;letter-spacing:.05em}}
    .role-badge.guest{{background:rgba(76,122,76,.12);color:#2E5A2E;border:1px solid rgba(76,122,76,.3)}}
    .role-badge.admin{{background:rgba(181,83,42,.12);color:#7A2E10;border:1px solid rgba(181,83,42,.3)}}
    .video-wrap{{position:relative;background:#140d04;aspect-ratio:16/9}}
    .video-wrap video{{width:100%;height:100%;display:none;object-fit:contain}}
    .video-overlay{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;background:radial-gradient(ellipse at 50% 40%,rgba(196,164,107,.12) 0%,rgba(20,13,4,.94) 75%)}}
    .video-overlay.clickable{{cursor:pointer;transition:background .2s}}
    .video-overlay.clickable:hover{{background:radial-gradient(ellipse at 50% 40%,rgba(196,164,107,.22) 0%,rgba(20,13,4,.88) 75%)}}
    .video-overlay.clickable:hover .ov-play-btn{{transform:scale(1.09);background:rgba(196,164,107,.28)}}
    .ov-play-btn{{width:48px;height:48px;border-radius:50%;background:rgba(196,164,107,.14);border:2px solid rgba(196,164,107,.38);display:flex;align-items:center;justify-content:center;font-size:18px;color:var(--tan);transition:transform .2s,background .2s}}
    .ov-label{{font-size:10.5px;font-weight:700;text-transform:uppercase;letter-spacing:.07em;color:rgba(196,164,107,.75)}}
    .ov-placeholder-msg{{text-align:center}}
    .ov-placeholder-msg .ov-main{{font-size:11px;color:rgba(196,164,107,.55);font-weight:600}}
    .ov-placeholder-msg .ov-sub{{font-size:10px;color:rgba(196,164,107,.38);margin-top:3px}}
    .ov-progress-wrap{{width:62%;height:3px;background:rgba(196,164,107,.18);border-radius:2px;overflow:hidden;display:none}}
    .ov-progress-fill{{height:100%;width:0%;background:var(--grad);border-radius:2px;transition:width .25s}}
    .ov-progress-pct{{font-size:9.5px;color:rgba(196,164,107,.5);margin-top:1px}}
    .dl-strip{{padding:9px 12px;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;gap:10px}}
    .dl-btn{{display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:700;color:var(--tan);border:1px solid rgba(196,164,107,.38);border-radius:20px;padding:4px 14px;text-decoration:none;background:transparent;cursor:pointer;transition:background .15s}}
    .dl-btn:hover{{background:rgba(196,164,107,.1)}}
    .dl-err{{font-size:10px;color:rgba(196,164,107,.5)}}
    .record-section{{margin-top:2px}}
    .record-label{{font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text-soft);margin-bottom:6px}}
    .record-cmd{{background:#1a1007;border:1px solid rgba(139,103,20,.22);border-radius:var(--r-sm);padding:10px 13px;font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:var(--tan);line-height:1.75;overflow-x:auto;white-space:pre}}
    .cmd-comment{{color:rgba(196,164,107,.4)}}
    .demo-footer{{background:var(--surface);border-top:1px solid var(--border);padding:11px 36px;display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:8px;font-size:11px;color:var(--text-dim)}}
    .demo-footer a{{color:var(--gold);text-decoration:none;border-bottom:1px dashed rgba(139,103,20,.3)}}
    .demo-footer a:hover{{border-bottom-color:var(--gold)}}
    @media(max-width:680px){{.demo-grid{{grid-template-columns:1fr}}.env-col{{border-right:none;border-bottom:1px solid var(--border)}}.env-col:last-child{{border-bottom:none}}.page{{margin:0;border-radius:0}}}}
    @media(prefers-reduced-motion:reduce){{*,*::before,*::after{{animation-duration:.01ms!important;transition-duration:.01ms!important}}}}
  </style>
</head>
<body>
<div class="page">
  <header class="demo-header">
    <div class="header-inner">
      <div class="eyebrow"><span class="eyebrow-dot"></span>Demo Recordings</div>
      <h1>Agentic RAG &#x2014; Walkthrough Videos</h1>
      <nav class="header-links">
        <a class="hlink hl-live" href="{remote_url}" target="_blank" rel="noopener noreferrer">&#x1F310; Live App</a>
        <a class="hlink" href="https://dev-enthusiast-84.github.io/AILabs/" target="_blank" rel="noopener noreferrer">&#x1F4D6; Documentation</a>
        <a class="hlink" href="https://github.com/{gh_repo}" target="_blank" rel="noopener noreferrer">&#x1F4E6; GitHub</a>
        <a class="hlink" href="https://github.com/{gh_repo}/releases" target="_blank" rel="noopener noreferrer">&#x1F3AC; All Releases</a>
      </nav>
    </div>
  </header>
  <div class="demo-grid" role="main">
{cols}
  </div>
  <footer class="demo-footer">
    <span>Videos on <a href="https://github.com/{gh_repo}/releases">GitHub Releases</a></span>
    <span>Gallery: <a href="{gallery_url}">GitHub Pages</a></span>
    <span>Auto-produced by <code>scripts/record-walkthrough.sh</code></span>
  </footer>
</div>
<script>
(function(){{
  'use strict';
  function fmtB(b){{return b>1048576?(b/1048576).toFixed(1)+' MB':(b/1024).toFixed(0)+' KB'}}
  function showVideo(wrap,blobUrl){{
    var v=wrap.querySelector('video'),ov=wrap.querySelector('.video-overlay');
    v.src=blobUrl;v.style.display='block';if(ov)ov.remove();
    v.play().catch(function(){{}});
  }}
  function showFallback(wrap,src,fname){{
    var ov=wrap.querySelector('.video-overlay');if(ov)ov.remove();
    var v=wrap.querySelector('video');v.src=src;v.style.display='block';v.load();
    v.play().catch(function(){{
      v.remove();
      var s=document.createElement('div');s.className='dl-strip';
      s.innerHTML='<span class="dl-err">Inline playback unavailable.</span>'
        +'<a class="dl-btn" href="'+src+'" download="'+(fname||'walkthrough.webm')+'">&#x2B07; Download to watch</a>';
      wrap.appendChild(s);
    }});
  }}
  function loadBlob(wrap){{
    var src=wrap.dataset.src,fname=wrap.dataset.filename||'walkthrough.webm';
    var ov=wrap.querySelector('.video-overlay');
    ov.classList.remove('clickable');ov.style.cursor='wait';
    var pb=ov.querySelector('.ov-play-btn'),lb=ov.querySelector('.ov-label');
    var pw=ov.querySelector('.ov-progress-wrap'),pf=ov.querySelector('.ov-progress-fill'),pp=ov.querySelector('.ov-progress-pct');
    if(pb)pb.textContent='&#x29D7;';if(lb)lb.textContent='Loading…';if(pw)pw.style.display='block';
    fetch(src,{{mode:'cors'}})
      .then(function(r){{
        if(!r.ok)throw new Error('HTTP '+r.status);
        var cl=parseInt(r.headers.get('content-length')||'0',10),rd=r.body.getReader(),ch=[],rx=0;
        function pump(){{return rd.read().then(function(x){{
          if(x.done)return ch;
          ch.push(x.value);rx+=x.value.length;
          var p=cl?Math.min(99,Math.round(rx/cl*100)):0;
          if(pf)pf.style.width=p+'%';if(pp)pp.textContent=p>0?p+'% of '+fmtB(cl):'';
          return pump();
        }});}}
        return pump().then(function(c){{return new Blob(c,{{type:'video/webm'}});}});
      }})
      .then(function(b){{showVideo(wrap,URL.createObjectURL(b));}} )
      .catch(function(e){{console.warn('Blob fetch failed:',e.message);showFallback(wrap,src,fname);}});
  }}
  function attachClick(wrap){{
    var ov=wrap.querySelector('.video-overlay');if(!ov)return;
    function go(){{ov.removeEventListener('click',go);ov.removeEventListener('keydown',kd);loadBlob(wrap);}}
    function kd(e){{if(e.key==='Enter'||e.key===' '){{e.preventDefault();go();}}}}
    ov.addEventListener('click',go);ov.addEventListener('keydown',kd);
  }}
  function probe(wrap){{
    fetch(wrap.dataset.src,{{method:'HEAD',mode:'cors'}})
      .then(function(r){{
        if(!r.ok)return;
        var ov=wrap.querySelector('.video-overlay');if(!ov)return;
        ov.removeAttribute('aria-hidden');
        ov.innerHTML='<div class="ov-play-btn">&#9654;</div>'
          +'<div class="ov-label">Click to watch</div>'
          +'<div class="ov-progress-wrap"><div class="ov-progress-fill"></div></div>'
          +'<div class="ov-progress-pct"></div>';
        ov.classList.add('clickable');wrap.removeAttribute('data-placeholder');
        attachClick(wrap);
      }}).catch(function(){{}});
  }}
  document.addEventListener('DOMContentLoaded',function(){{
    document.querySelectorAll('.video-wrap[data-src]').forEach(function(w){{
      w.dataset.placeholder==='true'?probe(w):attachClick(w);
    }});
  }});
}}());
</script>
</body>
</html>'''

open(html_path, 'w').write(HTML)
print(f"  (Re)generated docs/walkthrough/index.html")
PYEOF
    echo "  Gallery: ${_GH_PAGES_GALLERY}"
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

# Export WALKTHROUGH_BASE_URL from --url immediately after arg parsing so the
# Playwright spec (which checks process.env.WALKTHROUGH_BASE_URL) always sees it.
export WALKTHROUGH_BASE_URL="$BASE_URL"

echo "Walkthrough recorder"
echo "  URL        : ${WALKTHROUGH_BASE_URL}"
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

# ── GitHub token prompt (publish enabled, token missing) ──────────────────────
# Prompt before the browser launches so the operator can enter the token
# interactively without interrupting the recording mid-session.
if [[ "$PUBLISH" == true && -z "$_RESOLVED_GH_TOKEN" ]]; then
    echo "┌─────────────────────────────────────────────────────────────────────┐"
    echo "│  GitHub token required to publish walkthrough videos               │"
    echo "│                                                                     │"
    echo "│  Generate a Personal Access Token (PAT) with 'repo' scope:         │"
    echo "│    https://github.com/settings/tokens                              │"
    echo "│                                                                     │"
    echo "│  Then paste it at the prompt below, or press Enter to skip.        │"
    echo "│  (To skip permanently, pass --no-publish when running the script.) │"
    echo "└─────────────────────────────────────────────────────────────────────┘"
    # Read silently (no echo) so the token doesn't appear in terminal history.
    read -r -s -p "  GitHub PAT (or Enter to skip): " _INPUT_GH_TOKEN
    echo ""
    if [[ -n "$_INPUT_GH_TOKEN" ]]; then
        _RESOLVED_GH_TOKEN="$_INPUT_GH_TOKEN"
        echo "  Token accepted."
    else
        echo "  No token entered — videos will be saved locally only."
        echo "  Artifacts: artifacts/walkthrough/${ENV_LABEL}/"
        PUBLISH=false
    fi
    echo ""
fi

cd "$FRONTEND_DIR"

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

# Run the walkthrough recorder; kill the whole process group on interrupt so
# that headed Chrome windows (and chromium sub-processes) are always cleaned up.
_WALKTHROUGH_PID=""
_cleanup_walkthrough() {
    local sig="${1:-INT}"
    echo "" >&2
    echo "Walkthrough interrupted — closing browser and cleaning up..." >&2
    if [[ -n "$_WALKTHROUGH_PID" ]]; then
        # Kill the npm/Playwright process group; this closes headed Chrome too.
        kill -- "-${_WALKTHROUGH_PID}" 2>/dev/null \
            || kill "$_WALKTHROUGH_PID" 2>/dev/null \
            || true
        wait "$_WALKTHROUGH_PID" 2>/dev/null || true
    fi
    # Belt-and-suspenders: close any orphaned Playwright-launched Chromium instances.
    pkill -f "playwright.*chromium" 2>/dev/null || true
    exit 130
}
trap '_cleanup_walkthrough INT'  INT
trap '_cleanup_walkthrough TERM' TERM

"${CMD[@]}" &
_WALKTHROUGH_PID=$!
wait "$_WALKTHROUGH_PID"
_PLAYWRIGHT_EXIT=$?
trap - INT TERM
_WALKTHROUGH_PID=""

if [[ $_PLAYWRIGHT_EXIT -ne 0 ]]; then
    exit $_PLAYWRIGHT_EXIT
fi

if [[ "$PUBLISH" == true ]]; then
    _publish_videos "$ENV_LABEL" "$BASE_URL"
else
    echo ""
    echo "Publish skipped (--no-publish). To publish manually:"
    echo "  bash scripts/record-walkthrough.sh --url ${BASE_URL} --dry-run"
fi

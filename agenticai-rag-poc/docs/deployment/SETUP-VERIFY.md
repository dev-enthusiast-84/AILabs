# Docs Portal Verification

> [← Deployment](deployment/DEPLOYMENT.md) · [Setup Guide](deployment/SETUP.md)

Visual and functional checks for the documentation portal, both locally and on GitHub Pages.

---

## Browse the Docs Locally

From the `agenticai-rag-poc/` directory:

```bash
make docs-serve   # generates docs/README.md then opens http://localhost:3001
```

`npx` fetches `docsify-cli` automatically on first run. Live reload applies to all `.md` files under `docs/`. If you edit root `README.md`, stop the server, re-run `make docs-serve` to regenerate `docs/README.md`, then restart.

---

## Visual Verification Checklist

Open [http://localhost:3001](http://localhost:3001) and confirm each item:

| What to check | Where | Expected |
|---|---|---|
| Oat background | Every page | Warm cream (`#FAF6EE`) — not white, not blue |
| Cover page readable | Home `/` | Dark oat-brown gradient; light cream text visible |
| Sidebar — no double arrows | Any sidebar link | Single `›` chevron only; no extra `→` or `▶` symbols |
| Pitch page theme | **Capability Showcase** sidebar link | Dark nav bar, dark hero section, oat-toned sections |
| Walkthrough placeholders | **Walkthrough Videos** sidebar link | Two cards (Local + Live) each with placeholder and record command |
| All sidebar links resolve | Click every sidebar item | No 404 or blank page |

If the cover gradient is missing or text is unreadable, hard-reload (`Cmd+Shift+R` / `Ctrl+Shift+R`) to clear the Docsify cache.

---

## Verify Against GitHub Pages (after merge to main)

```bash
# 1. One-time: Settings → Pages → Source → "GitHub Actions" → Save
#    (GITHUB_TOKEN cannot enable Pages — one manual step per repo)

# 2. Merge a commit touching docs/, README.md, or .github/workflows/deploy-docs.yml

# 3. Watch the run
gh run list --workflow=deploy-docs.yml --limit 5
gh run watch

# 4. Open the published site
open https://dev-enthusiast-84.github.io/AILabs/
```

Run through the visual checklist above against the live URL once deployed (typically under 2 minutes).

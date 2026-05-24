import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'
import { generateWalkthroughQuestions, type WalkthroughQuestions } from './questions'
import { getWalkthroughDocSet, getGuestDocSet, type AdminDocSet, type DemoDoc } from './demo-docs'

const username = process.env.WALKTHROUGH_USERNAME
const password = process.env.WALKTHROUGH_PASSWORD
const interactiveSettings = process.env.WALKTHROUGH_INTERACTIVE_SETTINGS === 'true'
const interactiveTimeoutMs = Number(process.env.WALKTHROUGH_INTERACTIVE_TIMEOUT_MS ?? 600_000)

// Local: credentials come from env vars; ChromaDB + local file storage.
// Remote: credentials must be entered via Settings UI; Pinecone/Blob storage.
const isRemote = (process.env.WALKTHROUGH_ENV ?? 'local') === 'remote'

// Remote LLM + vector-store calls take longer due to network round-trips.
// Increase timeouts to avoid intermittent failures on cold remote deployments.
const QUERY_RESPONSE_TIMEOUT = isRemote ? 60_000 : 40_000
// 4-doc admin upload takes longer to index; remote Pinecone/Blob adds extra latency.
const uploadPostWaitMs = (role: 'guest' | 'admin') =>
  role === 'admin' ? (isRemote ? 6_000 : 4_000) : 2_500

function resolveGuestUploadFile(): string {
  if (process.env.WALKTHROUGH_UPLOAD_FILE) {
    return path.resolve(process.env.WALKTHROUGH_UPLOAD_FILE)
  }
  return path.resolve(process.cwd(), '..', 'sample-data', 'sample.txt')
}

// ---------------------------------------------------------------------------
// Caption overlay
// ---------------------------------------------------------------------------

async function caption(page: Page, title: string, detail: string, placement: 'bottom' | 'top' = 'bottom'): Promise<void> {
  // Always inject directly into document.body (outside React's #root).
  // This is synchronous — the element is in the DOM the instant evaluate() returns,
  // with no React async re-render races. React never manages elements outside #root,
  // so subsequent caption() calls can safely remove and replace the element.
  await page.evaluate(
    ({ title, detail, placement }) => {
      const id = 'walkthrough-caption'

      // Remove any existing caption regardless of who created it (DOM-injected or
      // React-managed). Since we never call window.__walkthroughCaption in this
      // function, React's walkthroughCaption state stays null and the React
      // component is never mounted — so there is no React-owned node to corrupt.
      const existing = document.getElementById(id)
      if (existing) existing.remove()

      const el = document.createElement('aside')
      el.id = id
      el.setAttribute('aria-label', 'Walkthrough caption')
      el.setAttribute('role', 'complementary')

      const strong = document.createElement('strong')
      strong.textContent = title
      Object.assign(strong.style, {
        display: 'block',
        fontSize: '15px',
        lineHeight: '1.25',
        marginBottom: '5px',
      })

      const span = document.createElement('span')
      span.textContent = detail
      Object.assign(span.style, {
        display: 'block',
        fontSize: '12px',
        lineHeight: '1.45',
        color: 'rgba(226, 232, 240, 0.95)',
      })

      el.appendChild(strong)
      el.appendChild(span)

      Object.assign(el.style, {
        position: 'fixed',
        left: '16px',
        ...(placement === 'top' ? { top: '16px' } : { bottom: '48px' }),
        maxWidth: '380px',
        zIndex: '2147483647',
        padding: '12px 16px',
        borderRadius: '12px',
        background: 'rgba(15, 23, 42, 0.92)',
        color: 'white',
        boxShadow: '0 24px 60px rgba(15, 23, 42, 0.32)',
        fontFamily: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        backdropFilter: 'blur(12px)',
      })

      document.body.appendChild(el)
    },
    { title, detail, placement },
  )
  // Element is synchronously in the DOM — waitForSelector confirms Playwright's
  // own visibility check (non-zero size, in viewport) before the display timer.
  await page.waitForSelector('#walkthrough-caption', { state: 'visible', timeout: 3000 }).catch(() => null)
  await page.waitForTimeout(1400)
}

// ---------------------------------------------------------------------------
// Voice demo stub — reads transcript from window.__WALKTHROUGH_VOICE_TRANSCRIPT__
// so each demo can inject a different spoken question at runtime.
// ---------------------------------------------------------------------------

async function installVoiceDemo(page: Page): Promise<void> {
  await page.addInitScript(() => {
    class DemoSpeechRecognition {
      continuous = false
      interimResults = true
      lang = 'en-US'
      onstart: (() => void) | null = null
      onresult: ((event: unknown) => void) | null = null
      onerror: ((event: unknown) => void) | null = null
      onend: (() => void) | null = null
      start() {
        this.onstart?.()
        window.setTimeout(() => {
          type VoiceWindow = { __WALKTHROUGH_VOICE_TRANSCRIPT__?: string }
          const transcript =
            (window as unknown as VoiceWindow).__WALKTHROUGH_VOICE_TRANSCRIPT__ ??
            'What does the document say about the main topic?'
          this.onresult?.({
            results: [{ isFinal: true, 0: { transcript } }],
          })
          this.onend?.()
        }, 600)
      }
      stop() {
        this.onend?.()
      }
      abort() {
        this.onend?.()
      }
    }

    Object.defineProperty(window, 'SpeechRecognition', {
      value: DemoSpeechRecognition,
      configurable: true,
    })
    Object.defineProperty(window, 'webkitSpeechRecognition', {
      value: DemoSpeechRecognition,
      configurable: true,
    })
  })
}

/** Set the transcript that the next voice-button click will produce. */
async function setVoiceTranscript(page: Page, transcript: string): Promise<void> {
  await page.evaluate(
    (t) => {
      type VoiceWindow = { __WALKTHROUGH_VOICE_TRANSCRIPT__?: string }
      ;(window as unknown as VoiceWindow).__WALKTHROUGH_VOICE_TRANSCRIPT__ = t
    },
    transcript,
  )
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Waits for an in-flight query to fully resolve by watching for the send
 * button to re-enable (loading → false).  Returns:
 *   'found'   — a response appeared and looks like real content
 *   'empty'   — the agent replied that it could not find sufficient info
 *   'timeout' — nothing resolved within the timeout window
 */
async function waitForQueryResponse(page: Page, timeout = 35_000): Promise<'found' | 'empty' | 'timeout'> {
  // After submitting a query the input is cleared, so the send button stays
  // disabled (empty input) even once loading=false — it is not a reliable
  // signal.  Instead count copy-buttons: a new one appears for every
  // successful assistant message (both "found" answers and "not found" ones).
  const copyBtns = page.locator('[data-testid^="copy-btn-"]')
  const before = await copyBtns.count()
  try {
    await expect(copyBtns).toHaveCount(before + 1, { timeout })
    await page.waitForTimeout(500)
    const noContent = await page
      .getByText(/could not find sufficient information/i)
      .first()
      .isVisible({ timeout: 400 })
      .catch(() => false)
    return noContent ? 'empty' : 'found'
  } catch {
    return 'timeout'
  }
}

async function maybeCloseDialog(page: Page): Promise<void> {
  const dialog = page.getByRole('dialog')
  if (!(await dialog.isVisible().catch(() => false))) return

  // Prefer a visible close/cancel button; fall back to Escape.
  const closeBtn = dialog.getByRole('button', { name: /^close/i }).first()
  const cancelBtn = dialog.getByRole('button', { name: /^cancel$/i }).first()
  if (await closeBtn.isVisible().catch(() => false)) {
    await closeBtn.click()
  } else if (await cancelBtn.isVisible().catch(() => false)) {
    await cancelBtn.click()
  } else {
    await page.keyboard.press('Escape')
  }
  // Wait for the dialog to fully disappear before the next action fires.
  await expect(dialog).not.toBeVisible({ timeout: 5000 }).catch(() => {
    page.keyboard.press('Escape').catch(() => null)
  })
  await page.waitForTimeout(400)
}

/**
 * Reads suggestion button texts from the empty-state panel after upload.
 * Suggestions are LLM-generated from indexed content so they are always
 * answerable — no risk of querying outside the document.
 * Returns an empty array if suggestions don't appear within the timeout.
 */
async function fetchSuggestionsFromUI(page: Page, timeout = 30_000): Promise<string[]> {
  const btns = page.locator('[data-testid="suggestion-btn"]')
  try {
    await expect(btns.first()).toBeVisible({ timeout })
    const texts = await btns.allTextContents()
    return texts.map(t => t.trim()).filter(Boolean)
  } catch {
    return []
  }
}

/**
 * Fetches already-indexed documents from the backend and returns their chunk
 * text as DemoDoc objects.  Uses the page's authenticated session so it works
 * for both guest and admin sessions without extra credentials.
 *
 * Suggestions shown in the UI already cover all indexed docs (existing + new)
 * because the frontend passes the full document list to /documents/suggestions.
 * This helper supplements the *content-extracted fallback questions* with the
 * same coverage, so the walkthrough queries hit real indexed content even in
 * pre-seeded environments where no new upload is needed.
 */
async function fetchIndexedDocAsDemoDocs(page: Page, limit = 4): Promise<DemoDoc[]> {
  try {
    const token = await page.evaluate(() => sessionStorage.getItem('token'))
    if (!token) return []

    const metaRes = await page.request.get('/api/documents/metadata', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!metaRes.ok()) return []
    const meta = await metaRes.json() as { documents?: Array<{ name: string }> }
    const names = (meta.documents ?? []).map(d => d.name).slice(0, limit)
    if (!names.length) return []

    const docs = await Promise.all(names.map(async (name): Promise<DemoDoc | null> => {
      try {
        const res = await page.request.get(
          `/api/documents/${encodeURIComponent(name)}/chunks`,
          { headers: { Authorization: `Bearer ${token}` } },
        )
        if (!res.ok()) return null
        const data = await res.json() as { chunks?: string[] }
        const text = (data.chunks ?? []).join('\n\n')
        return text.trim().length > 50
          ? {
              name,
              mimeType: 'text/plain',
              content: text,
              topic: name.replace(/\.[^.]+$/, '').replace(/[-_]/g, ' '),
            }
          : null
      } catch { return null }
    }))
    return docs.filter((d): d is DemoDoc => d !== null)
  } catch { return [] }
}

// Pauses the recording so a human operator can update Settings in a deployed
// (remote) instance. Returns true when the operator closed the dialog,
// false when interactive mode is off or the dialog was not visible.
// Only called for remote deployments — local env-driven credentials do not
// require this pause.
async function waitForUserSettingsIfRequested(page: Page, prompt: string): Promise<boolean> {
  if (!interactiveSettings) return false

  const dialog = page.getByRole('dialog')
  try {
    await expect(dialog).toBeVisible({ timeout: 3000 })
  } catch {
    return false
  }

  await caption(page, 'Interactive settings pause', prompt)
  await page.waitForFunction(
    () => !document.querySelector('[role="dialog"]'),
    undefined,
    { timeout: interactiveTimeoutMs },
  )
  await page.waitForTimeout(1000)
  return true
}

/** Click the Simple or Agentic mode button in the toolbar. */
async function switchRagMode(page: Page, mode: 'simple' | 'agentic'): Promise<void> {
  const modeGroup = page.getByRole('group', { name: 'RAG mode selector' })
  const btn = modeGroup.getByRole('button', { name: new RegExp(mode, 'i') })
  if (await btn.isVisible().catch(() => false)) {
    await btn.click()
    await page.waitForTimeout(400)
  }
}

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------

async function loginAs(page: Page, role: 'guest' | 'admin'): Promise<void> {
  // Navigate first so the caption lands on the actual login page, not about:blank
  // (a caption injected before goto is wiped when the DOM is replaced on navigation).
  await page.goto('/login')
  await expect(page.getByText('Agentic RAG')).toBeVisible()
  await caption(
    page,
    'Capstone Walkthrough',
    'The Edureka task list drives this tour: foundation, UI, ingestion, semantic search, vector retrieval, agentic RAG, safety, deployment, and docs.',
  )

  if (role === 'admin') {
    await caption(
      page,
      'Task 1-2: Project foundation and UI',
      'Signing in as admin to show the full deployed application experience.',
    )
    await page.getByTestId('username-input').fill(username!)
    await page.getByTestId('password-input').fill(password!)
    await page.getByTestId('login-button').click()
    await expect(page.getByTestId('dropzone')).toBeVisible()
  } else {
    await caption(
      page,
      'Guest Experience',
      'Using guest mode — same chat and TXT upload path, no credentials required.',
    )
    await page.getByTestId('guest-button').click()
    await expect(page.getByTestId('dropzone')).toBeVisible()
  }
}

// ---------------------------------------------------------------------------
// Core walkthrough — runs for guest and admin
// ---------------------------------------------------------------------------

async function runWalkthrough(
  page: Page,
  role: 'guest' | 'admin',
  adminDocSet?: AdminDocSet,
  guestDoc?: DemoDoc,
): Promise<void> {
  // Questions are always derived from actual uploaded content — never hardcoded.
  // Admin: 4 in-memory DemoDoc objects (txt/csv/xlsx/pdf on distinct topics).
  // Guest: 1 in-memory TXT DemoDoc on a random enterprise topic.
  // Fallback (legacy): single file path from disk (used only if guestDoc is absent).
  let questions: WalkthroughQuestions
  if (role === 'admin' && adminDocSet) {
    questions = await generateWalkthroughQuestions(adminDocSet.docs)
  } else if (guestDoc) {
    questions = await generateWalkthroughQuestions([guestDoc])
  } else {
    const uploadFile = resolveGuestUploadFile()
    questions = await generateWalkthroughQuestions(uploadFile)
  }

  await installVoiceDemo(page)
  await loginAs(page, role)

  // ── Supplement questions with already-indexed content ─────────────────────
  // The UI suggestions (shown in the chat empty-state) already cover all
  // indexed docs (existing + newly uploaded) because the frontend sends the
  // full document list to /documents/suggestions.  This step does the same
  // for the *content-extracted fallback questions* so they also reflect
  // whatever is currently in the index, not only the newly uploaded buffers.
  // Runs after login so the auth token is available; runs before upload so
  // the fallback is ready before we need it.
  const priorDocs = await fetchIndexedDocAsDemoDocs(page, 4)
  if (priorDocs.length > 0) {
    // Exclude docs that share a name with the about-to-be-uploaded demo set
    // so we do not double-count them after indexing.
    const uploadedNames = new Set(
      role === 'admin' && adminDocSet ? adminDocSet.docs.map(d => d.name) : [],
    )
    const uniquePrior = priorDocs.filter(d => !uploadedNames.has(d.name))
    if (uniquePrior.length > 0) {
      const priorQuestions = await generateWalkthroughQuestions(uniquePrior)
      // Fill empty slots only — newly uploaded doc questions take precedence.
      questions = {
        simpleText:    questions.simpleText    || priorQuestions.simpleText,
        agenticText:   questions.agenticText   || priorQuestions.agenticText,
        voiceSimple:   questions.voiceSimple   || priorQuestions.voiceSimple,
        voiceAgentic:  questions.voiceAgentic  || priorQuestions.voiceAgentic,
        multilingual:  questions.multilingual  || priorQuestions.multilingual,
        negativeQuery: questions.negativeQuery, // always keep out-of-scope query
      }
    }
  }

  // ── Settings ──────────────────────────────────────────────────────────────
  // Local:  env vars supply credentials; ChromaDB (built-in) is the vector
  //         store; files are written to local disk. No UI input needed.
  // Remote: Settings UI is the only credential entry point. The app supports
  //         external vector stores (Pinecone) and blob storage (Vercel Blob/S3).
  //         Both require API keys entered here before the first upload or query.
  await caption(
    page,
    'Task 9: Safety controls and runtime settings',
    isRemote
      ? 'Remote deployment: enter your LLM provider key, external vector store token (Pinecone), and blob storage credentials (Vercel Blob / S3) here before first use. Storage options differ by environment.'
      : 'Local deployment: credentials come from backend/.env — ChromaDB and local file storage need no UI keys. The panel shows all configurable options and cost-impact warnings.',
    'top',
  )
  await page.getByTestId('settings-btn').click()
  await expect(page.getByRole('dialog')).toBeVisible()

  if (isRemote) {
    const userUpdatedInitialSettings = await waitForUserSettingsIfRequested(
      page,
      'Remote instance: enter your LLM provider API key, Pinecone vector store credentials, and Vercel Blob / S3 storage token in the Settings panel, then close it to resume recording.',
    )
    if (!userUpdatedInitialSettings) {
      await page.waitForTimeout(3000)
      await maybeCloseDialog(page)
    }
  } else {
    // Local: credentials come from environment variables — display for 3 s then close.
    await page.waitForTimeout(3000)
    await maybeCloseDialog(page)
  }

  // ── Upload ────────────────────────────────────────────────────────────────
  await caption(
    page,
    'Task 3-5: Ingestion, chunks, embeddings, vector store',
    role === 'admin' && adminDocSet
      ? `Uploading 4 enterprise documents (TXT · CSV · XLSX · PDF) covering: ${adminDocSet.label}. Each file is chunked, embedded, and stored in the vector store.`
      : `Uploading a plain-text file in guest mode (topic: ${guestDoc?.topic ?? 'enterprise content'}). The pipeline chunks the content, generates embeddings, and indexes them for semantic retrieval.`,
  )

  if (role === 'admin' && adminDocSet) {
    // Upload all 4 docs as in-memory buffers — no temp files on disk.
    // The test runner is always local; Playwright passes buffers to the browser
    // which uploads them over HTTP to the app (local or Vercel).
    // This is backend-agnostic: ChromaDB + local disk or Pinecone + Vercel Blob.
    await page.getByTestId('file-input').setInputFiles(
      adminDocSet.docs.map(d => ({
        name: d.name,
        mimeType: d.mimeType,
        buffer: Buffer.isBuffer(d.content) ? d.content : Buffer.from(d.content as string, 'utf-8'),
      })),
    )
  } else if (guestDoc) {
    // Guest: single in-memory TXT DemoDoc — content matches the extracted questions.
    // Works for both local and remote deployments (in-memory buffer → HTTP upload).
    await page.getByTestId('file-input').setInputFiles({
      name: guestDoc.name,
      mimeType: guestDoc.mimeType,
      buffer: Buffer.from(guestDoc.content as string, 'utf-8'),
    })
  } else {
    const uploadFile = resolveGuestUploadFile()
    await page.getByTestId('file-input').setInputFiles(uploadFile)
  }
  // Allow time for upload processing to begin. Admin multi-doc and remote
  // vector-store indexing are both slower than local single-doc ingestion.
  await page.waitForTimeout(uploadPostWaitMs(role))

  // Use waitFor so a slow remote response doesn't cause a missed dialog check.
  const settingsDialogOpened = await page.getByRole('dialog')
    .waitFor({ state: 'visible', timeout: 3_000 })
    .then(() => true)
    .catch(() => false)
  if (settingsDialogOpened) {
    if (isRemote) {
      // Remote: the app blocks indexing until provider credentials are present.
      const userUpdatedPrereqs = await waitForUserSettingsIfRequested(
        page,
        'A provider credential is required before indexing can begin. Enter the required keys, save, and close the modal — the recording will continue automatically.',
      )
      if (!userUpdatedPrereqs) {
        await caption(
          page,
          'Prerequisites check',
          'The application requires provider credentials before indexing documents. Enter credentials in the Settings panel, then re-upload to continue.',
        )
        await maybeCloseDialog(page)
      }
    } else {
      // Local: this dialog should not appear if backend/.env is configured.
      // Show a skip caption explaining the cause, then dismiss.
      await caption(
        page,
        'Prerequisites check — skipped',
        'This prompt appears when required environment variables are absent from backend/.env. Dismissing — set the required variables, restart the backend, and re-run.',
      )
      await maybeCloseDialog(page)
    }
  } else {
    await page.waitForTimeout(2500)
  }

  const queryInput = page.getByTestId('query-input')
  const voiceButton = page.getByTestId('voice-input-btn')

  // ── Resolve queries from UI suggestions ───────────────────────────────────
  // Suggestions are derived from indexed content by the backend, so they are
  // guaranteed to be answerable. Use them for all demo queries; fall back to
  // the content-extracted questions only when fewer than 5 suggestions appear.
  const suggestionTexts = await fetchSuggestionsFromUI(
    page,
    isRemote ? 45_000 : 25_000,
  )
  const or = (ui: string | undefined, extracted: string) => ui?.trim() || extracted || ''
  const resolvedQuestions: WalkthroughQuestions = {
    // Admin: suggestions[0-3] each cover a different document (TXT/CSV/XLSX/PDF).
    // The backend generates one answerable question per doc when multiple files
    // are indexed, so each demo step exercises a distinct document's content.
    // Guest: all four suggestion slots come from the single uploaded doc;
    // the per-doc extracted fallbacks (questions.*) also cover that doc.
    simpleText:   or(suggestionTexts[0], questions.simpleText),
    agenticText:  or(suggestionTexts[1], questions.agenticText),
    voiceSimple:  or(suggestionTexts[2], questions.voiceSimple),
    voiceAgentic: or(suggestionTexts[3], questions.voiceAgentic),
    // Reuse suggestion[0] for multilingual — same grounding, different output language.
    multilingual: or(suggestionTexts[0], questions.multilingual),
    // A question clearly outside the indexed content — demonstrates the pipeline's
    // honest "not found" response rather than hallucinating an answer.
    negativeQuery: questions.negativeQuery,
  }

  // Ensure the chat panel is in view and focused before any queries.
  // After admin upload the viewport may still be anchored to the document list.
  await queryInput.scrollIntoViewIfNeeded().catch(() => null)
  await queryInput.click().catch(() => null)
  await page.waitForTimeout(300)

  // ── 1. Text chat — Simple RAG ─────────────────────────────────────────────
  await caption(
    page,
    'Text chat — Simple RAG',
    'Direct one-shot retrieval: the question goes straight to the generation step with the retrieved context — lowest latency, no multi-step reasoning.',
  )
  await switchRagMode(page, 'simple')
  await queryInput.fill(resolvedQuestions.simpleText)
  await queryInput.press('Enter')
  // Wait for the actual response rather than a fixed timeout so the caption
  // and the answer are always in sync regardless of LLM latency.
  await waitForQueryResponse(page, QUERY_RESPONSE_TIMEOUT)
  await page.waitForTimeout(800)

  // Show ground source for the simple RAG response.
  // Use .first() here — simple RAG is the first message so its citation appears
  // before any agentic response is in the DOM.
  const simpleSource = page.getByTitle('Click to view document content').first()
  if (await simpleSource.isVisible({ timeout: 2500 }).catch(() => false)) {
    await caption(
      page,
      'Grounded sources',
      'Every answer cites the exact document chunk it was retrieved from. Click any source to inspect the evidence — transparency that makes the pipeline trustworthy, not just fast.',
    )
    await simpleSource.scrollIntoViewIfNeeded().catch(() => null)
    await simpleSource.click()
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5000 }).catch(() => null)
    await page.waitForTimeout(2200)
    await maybeCloseDialog(page)
  }
  await page.waitForTimeout(400)

  // ── 2. Text chat — Agentic AI ─────────────────────────────────────────────
  await caption(
    page,
    'Text chat — Agentic AI',
    'Seven-node pipeline: planner → HyDE → retrieval → grader → reranker → generator → validator, with full trace and grounded sources.',
  )
  await switchRagMode(page, 'agentic')
  await queryInput.fill(resolvedQuestions.agenticText)
  await queryInput.press('Enter')
  await waitForQueryResponse(page, QUERY_RESPONSE_TIMEOUT)
  await page.waitForTimeout(1000)

  const traceToggle = page.getByText(/Agent trace/i).first()
  if (await traceToggle.isVisible().catch(() => false)) {
    await caption(
      page,
      'Agent trace',
      'Each pipeline step — planner, retrieval, generation, validation — with token counts and latency per node, providing full explainability.',
    )
    await traceToggle.click()
    await page.waitForTimeout(400)
    // Scroll the trace panel itself into view so the recording shows the full content.
    const tracePanel = page.locator('[data-testid^="trace-panel-"]').first()
    if (await tracePanel.isVisible({ timeout: 2000 }).catch(() => false)) {
      await tracePanel.scrollIntoViewIfNeeded()
    } else {
      await page.evaluate(() => window.scrollBy({ top: 320, behavior: 'smooth' }))
    }
    await page.waitForTimeout(1500)
  } else {
    await caption(
      page,
      'Agent trace',
      'The trace panel appears after a query completes. It shows each pipeline step with per-node token counts and latency for full explainability.',
    )
    await page.waitForTimeout(1000)
  }

  // Use .last() so we target the agentic response's own citation, not the
  // simple RAG citation that was already demonstrated in step 1.
  const source = page.getByTitle('Click to view document content').last()
  if (await source.isVisible().catch(() => false)) {
    await caption(
      page,
      'Agentic grounded sources',
      'The agentic pipeline links its answer to the specific chunks that survived grading and reranking — a tighter evidence trail than simple retrieval.',
    )
    await source.scrollIntoViewIfNeeded().catch(() => null)
    await source.click()
    // Wait for the document viewer dialog to be fully open before pausing.
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5000 }).catch(() => null)
    await page.waitForTimeout(2000)
    await maybeCloseDialog(page)
  } else {
    await caption(
      page,
      'Agentic grounded sources',
      'Source citations appear once retrieval returns matching chunks. In the full pipeline they link each answer to the exact document section that grounded the response.',
    )
    await page.waitForTimeout(1000)
  }

  // ── Export conversation transcript ────────────────────────────────────────
  // Available after at least one assistant message. Works on local and remote.
  const exportBtn = page.getByTestId('export-btn')
  if (await exportBtn.isVisible().catch(() => false)) {
    const isEnabled = await exportBtn.isEnabled().catch(() => false)
    await caption(
      page,
      'Export conversation transcript',
      'Download the complete Q&A conversation — questions, answers, grounded source citations, and timestamps — as a portable text file for sharing or archiving.',
    )
    if (isEnabled) {
      // waitForEvent races against click; if download doesn't fire (remote env
      // may redirect to a data URL), we still continue gracefully.
      const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 8_000 }).catch(() => null),
        exportBtn.click(),
      ])
      await page.waitForTimeout(download ? 800 : 1_200)
    } else {
      await page.waitForTimeout(1_200)
    }
  } else {
    await caption(
      page,
      'Export conversation transcript',
      'After a conversation, the export button downloads all Q&A pairs with timestamps and grounded source citations in a portable format for sharing or archiving.',
    )
    await page.waitForTimeout(1_000)
  }

  // ── 3. Voice chat — Simple RAG ────────────────────────────────────────────
  await caption(
    page,
    'Voice chat — Simple RAG',
    'A spoken question feeds the same direct retrieval path — the mic icon transcribes speech and submits it as a normal query.',
  )
  await switchRagMode(page, 'simple')
  await setVoiceTranscript(page, resolvedQuestions.voiceSimple)
  if (await voiceButton.isVisible().catch(() => false)) {
    await voiceButton.click()
    await expect(queryInput).not.toBeEmpty({ timeout: 5000 }).catch(() => null)
    await queryInput.press('Enter')
    const voiceSimpleResult = await waitForQueryResponse(page, QUERY_RESPONSE_TIMEOUT)
    if (voiceSimpleResult === 'empty') {
      await caption(
        page,
        'Voice query — outside indexed content',
        'The spoken question fell outside the demo document\'s coverage. In production with a fully populated knowledge base, voice queries resolve identically to typed ones — the pipeline returns "I could not find sufficient information" as a safe, honest answer rather than hallucinating.',
      )
    } else {
      await caption(
        page,
        'Voice → text → retrieval',
        'Speech is transcribed client-side, sent through the same retrieval pipeline, and answered with grounded sources — no dedicated voice model needed.',
      )
    }
    await page.waitForTimeout(1000)
  } else {
    await caption(
      page,
      'Voice input — skipped',
      'Voice input is available in the live application but requires microphone access in the recording environment. The voice-to-text path is functionally identical to typed input.',
    )
    await page.waitForTimeout(1000)
  }

  // ── 4. Voice chat — Agentic AI ────────────────────────────────────────────
  await caption(
    page,
    'Voice chat — Agentic AI',
    'The spoken question enters the full seven-node pipeline with graded retrieval and self-validation — combining natural speech with explainable AI.',
  )
  await switchRagMode(page, 'agentic')
  await setVoiceTranscript(page, resolvedQuestions.voiceAgentic)
  if (await voiceButton.isVisible().catch(() => false)) {
    await voiceButton.click()
    await expect(queryInput).not.toBeEmpty({ timeout: 5000 }).catch(() => null)
    await queryInput.press('Enter')
    const voiceAgenticResult = await waitForQueryResponse(page, QUERY_RESPONSE_TIMEOUT)

    if (voiceAgenticResult === 'empty') {
      await caption(
        page,
        'Agentic voice — outside indexed content',
        'The seven-node pipeline validated that the indexed content does not cover this question and returned an honest "not found" response — demonstrating self-validation rather than hallucinating an answer. In production, a richer knowledge base would return a grounded result.',
      )
      await page.waitForTimeout(1000)
    } else {
      const agenticVoiceTrace = page.getByText(/Agent trace/i).last()
      if (await agenticVoiceTrace.isVisible().catch(() => false)) {
        await caption(
          page,
          'Agentic voice trace',
          'The voice + agentic path produces the same structured trace, combining natural speech with a fully auditable reasoning pipeline.',
        )
        await agenticVoiceTrace.click()
        await page.waitForTimeout(400)
        const voiceTracePanel = page.locator('[data-testid^="trace-panel-"]').last()
        if (await voiceTracePanel.isVisible({ timeout: 2000 }).catch(() => false)) {
          await voiceTracePanel.scrollIntoViewIfNeeded()
        } else {
          await page.evaluate(() => window.scrollBy({ top: 320, behavior: 'smooth' }))
        }
        await page.waitForTimeout(1500)
      } else {
        await page.waitForTimeout(1000)
      }
    }
  } else {
    await caption(
      page,
      'Voice input — skipped',
      'Voice input requires microphone access in the recording environment. The full agentic pipeline behaviour is identical whether the query arrives by voice or text.',
    )
    await page.waitForTimeout(1000)
  }

  // ── Multilingual RAG ──────────────────────────────────────────────────────
  // Switch response language to Spanish; the retrieval pipeline stays in
  // English — only the generated answer is translated.  Same grounding,
  // different output language.  Reset to English after the demo query.
  const languageSelect = page.getByTestId('chat-language-select')
  if (await languageSelect.isVisible().catch(() => false)) {
    await caption(
      page,
      'Captivating feature: multilingual RAG',
      'Switch the response language — the retrieval and ranking pipeline stays grounded in the original document while the LLM presents the answer in Spanish (or French, German, Hindi, and more).',
    )
    await languageSelect.selectOption('es')
    await page.waitForTimeout(400)
    await queryInput.fill(resolvedQuestions.multilingual)
    await queryInput.press('Enter')
    const multilingualResult = await waitForQueryResponse(page, QUERY_RESPONSE_TIMEOUT)
    if (multilingualResult === 'found') {
      await caption(
        page,
        'Respuesta en español',
        'The RAG pipeline retrieved English context and the LLM generated a Spanish answer — the same document grounding, a different output language. Source filenames remain visible in the original language.',
      )
    } else {
      await caption(
        page,
        'Multilingual query — outside indexed content',
        'No matching content found for this query. In a fully populated knowledge base the same pipeline would return a grounded, translated answer.',
      )
    }
    await page.waitForTimeout(1_200)
    // Reset to English so subsequent steps are unaffected
    await languageSelect.selectOption('en')
    await page.waitForTimeout(300)
  } else {
    await caption(
      page,
      'Multilingual output — skipped',
      'The language selector enables answers in Spanish, French, German, Hindi, and more while keeping retrieval grounded to the indexed document. It was not visible at this point.',
    )
    await page.waitForTimeout(1_000)
  }

  // ── Negative query — out-of-scope / honest "not found" ───────────────────
  // Demonstrates that the pipeline does not hallucinate: when the question is
  // outside indexed content it returns "could not find sufficient information".
  if (resolvedQuestions.negativeQuery) {
    await caption(
      page,
      'Safety: honest "not found" response',
      'Asking a question outside the indexed content — the pipeline returns a transparent "could not find sufficient information" rather than fabricating an answer.',
    )
    await switchRagMode(page, 'agentic')
    await queryInput.fill(resolvedQuestions.negativeQuery)
    await queryInput.press('Enter')
    await waitForQueryResponse(page, QUERY_RESPONSE_TIMEOUT)
    await page.waitForTimeout(1200)
  }

  // ── Guardrails ────────────────────────────────────────────────────────────
  await caption(
    page,
    'Task 9: Guardrails',
    'The guardrails console shows input/output safety controls and testing support for safer document Q&A.',
  )
  await page.getByTestId('guardrails-btn').click()
  await expect(page.getByText('Content Guardrails')).toBeVisible({ timeout: 5000 }).catch(() => null)
  await page.waitForTimeout(2000)
  // Scroll the inner content panel down to show all guardrail rules, then back
  // to the top — works for both guest and admin sessions.
  const guardrailsContent = page.locator('[role="dialog"] .overflow-y-auto').first()
  await guardrailsContent.evaluate(el => el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })).catch(() => null)
  await page.waitForTimeout(2000)
  await guardrailsContent.evaluate(el => el.scrollTo({ top: 0, behavior: 'smooth' })).catch(() => null)
  await page.waitForTimeout(1500)
  // Fall back to maybeCloseDialog if the explicit close button is not present
  // (e.g. guest layout variation) — prevents the modal from staying open and
  // causing a visual glitch in the next step.
  const guardrailsCloseBtn = page.getByTestId('guardrails-close')
  if (await guardrailsCloseBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await guardrailsCloseBtn.click()
  } else {
    await maybeCloseDialog(page)
  }
  await page.waitForTimeout(600)

  // ── Ragas evaluation ──────────────────────────────────────────────────────
  // Show caption BEFORE opening the dialog so no DOM injection occurs while
  // the modal is open (avoids potential focus-trap disruption).
  // Available for both guest and admin as long as documents are indexed.
  await caption(
    page,
    'Task 9: RAG evaluation — Ragas metrics',
    'Ragas measures retrieval quality with four automated metrics: Faithfulness, Answer Relevancy, Context Precision, and Context Recall. Click Run to evaluate indexed documents.',
    'top',
  )
  const ragasDashboardBtn = page.getByTestId('ragas-dashboard-btn')
  if (await ragasDashboardBtn.isVisible().catch(() => false)) {
    await ragasDashboardBtn.click()
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5000 }).catch(() => null)
    // Let the dashboard load and stay clearly visible before closing.
    await page.waitForTimeout(5500)
    await maybeCloseDialog(page)
  } else {
    await caption(
      page,
      'Ragas evaluation — not available',
      'The Ragas dashboard button was not visible at this point. It requires at least one indexed document and a configured provider key.',
    )
    await page.waitForTimeout(1000)
  }

  // ── Final ─────────────────────────────────────────────────────────────────
  await caption(
    page,
    'Task 10: Deployed and documented',
    'The final package includes deployment guidance, architecture notes, coverage evidence, and this repeatable walkthrough recorder.',
  )
  await page.waitForTimeout(1200)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('guest mode walkthrough', async ({ page }) => {
  // Generate a fresh enterprise TXT at test-start time (never cached/hardcoded).
  // Questions are derived from this same content — indexed doc always matches queries.
  const guestDoc = await getGuestDocSet()
  await runWalkthrough(page, 'guest', undefined, guestDoc)
})

test('admin mode walkthrough', async ({ page }) => {
  test.skip(
    !username || !password,
    'Set WALKTHROUGH_USERNAME and WALKTHROUGH_PASSWORD to record admin mode.',
  )
  // Generate 4 diverse demo docs at test-start time (never cached/hardcoded).
  // Works for both local (ChromaDB + disk) and remote (Pinecone + Vercel Blob)
  // deployments — Playwright sends in-memory buffers over HTTP to whichever backend.
  const adminDocSet = await getWalkthroughDocSet()
  await runWalkthrough(page, 'admin', adminDocSet)
})

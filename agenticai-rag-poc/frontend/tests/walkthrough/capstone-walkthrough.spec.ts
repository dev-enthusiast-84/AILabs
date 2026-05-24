import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'
import { generateWalkthroughQuestions, type WalkthroughQuestions } from './questions'

const username = process.env.WALKTHROUGH_USERNAME
const password = process.env.WALKTHROUGH_PASSWORD
const interactiveSettings = process.env.WALKTHROUGH_INTERACTIVE_SETTINGS === 'true'
const interactiveTimeoutMs = Number(process.env.WALKTHROUGH_INTERACTIVE_TIMEOUT_MS ?? 600_000)

// Local deployments read credentials from environment variables — no UI settings
// prompt needed. Remote (Vercel/deployed) deployments block env-based credentials
// in production and require all provider keys to be entered through the Settings UI.
const isRemote = (process.env.WALKTHROUGH_ENV ?? 'local') === 'remote'

function resolveUploadFile(role: 'guest' | 'admin'): string {
  if (process.env.WALKTHROUGH_UPLOAD_FILE) {
    return path.resolve(process.env.WALKTHROUGH_UPLOAD_FILE)
  }
  return path.resolve(process.cwd(), '..', 'sample-data', role === 'admin' ? 'sample.pdf' : 'sample.txt')
}

// ---------------------------------------------------------------------------
// Caption overlay
// ---------------------------------------------------------------------------

async function caption(page: Page, title: string, detail: string): Promise<void> {
  await page.evaluate(
    ({ title, detail }) => {
      const id = 'walkthrough-caption'
      document.getElementById(id)?.remove()
      const el = document.createElement('aside')
      el.id = id
      el.setAttribute('aria-label', 'Walkthrough caption')
      el.innerHTML = `<strong>${title}</strong><span>${detail}</span>`
      Object.assign(el.style, {
        position: 'fixed',
        left: '32px',
        bottom: '32px',
        maxWidth: '560px',
        zIndex: '2147483647',
        padding: '18px 22px',
        borderRadius: '16px',
        background: 'rgba(15, 23, 42, 0.92)',
        color: 'white',
        boxShadow: '0 24px 60px rgba(15, 23, 42, 0.32)',
        fontFamily: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        backdropFilter: 'blur(12px)',
      })
      const strong = el.querySelector('strong') as HTMLElement
      Object.assign(strong.style, {
        display: 'block',
        fontSize: '18px',
        lineHeight: '1.25',
        marginBottom: '6px',
      })
      const span = el.querySelector('span') as HTMLElement
      Object.assign(span.style, {
        display: 'block',
        fontSize: '14px',
        lineHeight: '1.45',
        color: 'rgba(226, 232, 240, 0.95)',
      })
      document.body.appendChild(el)
    },
    { title, detail },
  )
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
  await caption(
    page,
    'Capstone Walkthrough',
    'The Edureka task list drives this tour: foundation, UI, ingestion, semantic search, vector retrieval, agentic RAG, safety, deployment, and docs.',
  )
  await page.goto('/login')
  await expect(page.getByText('Agentic RAG')).toBeVisible()

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
// Core walkthrough — runs identically for guest and admin
// ---------------------------------------------------------------------------

async function runWalkthrough(page: Page, role: 'guest' | 'admin'): Promise<void> {
  const uploadFile = resolveUploadFile(role)
  const questions: WalkthroughQuestions = generateWalkthroughQuestions(uploadFile)

  await installVoiceDemo(page)
  await loginAs(page, role)

  // ── Settings ──────────────────────────────────────────────────────────────
  // Local: credentials are provided via environment variables — the Settings
  // panel is shown briefly for demonstration but requires no operator input.
  // Remote: the deployed app blocks environment-based credentials; provider
  // keys and storage tokens must be entered through the Settings UI before
  // the first upload or query.
  await caption(
    page,
    'Task 9: Safety controls and runtime settings',
    isRemote
      ? 'Deployed instances require provider credentials to be entered here before first use. Storage configuration and cost-impact warnings are also managed through this panel.'
      : 'The settings panel provides runtime configuration. For local deployments, credentials are read from environment variables — no UI input needed.',
  )
  await page.getByTestId('settings-btn').click()
  await expect(page.getByRole('dialog')).toBeVisible()

  if (isRemote) {
    const userUpdatedInitialSettings = await waitForUserSettingsIfRequested(
      page,
      'Deployed instance: enter your provider API key and any required storage credentials (vector store key, file store token) in the Settings panel, then close it to resume recording.',
    )
    if (!userUpdatedInitialSettings) {
      await page.waitForTimeout(1800)
      await maybeCloseDialog(page)
    }
  } else {
    // Local: credentials come from environment variables — display briefly then close.
    await page.waitForTimeout(1800)
    await maybeCloseDialog(page)
  }

  // ── Upload ────────────────────────────────────────────────────────────────
  await caption(
    page,
    'Task 3-5: Ingestion, chunks, embeddings, vector store',
    `${role === 'admin' ? 'Uploading a sample PDF' : 'Uploading a guest TXT file'} to process enterprise content into retrievable chunks.`,
  )
  await page.getByTestId('file-input').setInputFiles(uploadFile)
  await page.waitForTimeout(2500)

  const settingsDialogOpened = await page.getByRole('dialog').isVisible().catch(() => false)
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

  // ── 1. Text chat — Simple RAG ─────────────────────────────────────────────
  await caption(
    page,
    'Text chat — Simple RAG',
    'Direct one-shot retrieval: the question goes straight to the generation step with the retrieved context — lowest latency, no multi-step reasoning.',
  )
  await switchRagMode(page, 'simple')
  await queryInput.fill(questions.simpleText)
  await queryInput.press('Enter')
  await page.waitForTimeout(7000)

  // ── 2. Text chat — Agentic AI ─────────────────────────────────────────────
  await caption(
    page,
    'Text chat — Agentic AI',
    'Seven-node pipeline: planner → HyDE → retrieval → grader → reranker → generator → validator, with full trace and grounded sources.',
  )
  await switchRagMode(page, 'agentic')
  await queryInput.fill(questions.agenticText)
  await queryInput.press('Enter')
  await page.waitForTimeout(7000)

  const traceToggle = page.getByText(/Agent trace/i).first()
  if (await traceToggle.isVisible().catch(() => false)) {
    await caption(
      page,
      'Agent trace',
      'Each pipeline step — planner, retrieval, generation, validation — with token counts and latency per node, providing full explainability.',
    )
    await traceToggle.click()
    await page.waitForTimeout(2200)
  } else {
    await caption(
      page,
      'Agent trace',
      'The trace panel appears after a query completes. It shows each pipeline step with per-node token counts and latency for full explainability.',
    )
    await page.waitForTimeout(1400)
  }

  const source = page.getByTitle('Click to view document content').first()
  if (await source.isVisible().catch(() => false)) {
    await caption(
      page,
      'Grounded sources',
      'Source links open the indexed document preview so viewers can inspect the evidence behind every answer.',
    )
    await source.click()
    // Wait for the document viewer dialog to be fully open before pausing.
    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5000 }).catch(() => null)
    await page.waitForTimeout(2200)
    await maybeCloseDialog(page)
  } else {
    await caption(
      page,
      'Grounded sources',
      'Source citations link each answer back to the document chunk that grounded the response. They appear once a query returns results with matching context.',
    )
    await page.waitForTimeout(1400)
  }

  // ── 3. Voice chat — Simple RAG ────────────────────────────────────────────
  await caption(
    page,
    'Voice chat — Simple RAG',
    'A spoken question feeds the same direct retrieval path — the mic icon transcribes speech and submits it as a normal query.',
  )
  await switchRagMode(page, 'simple')
  await setVoiceTranscript(page, questions.voiceSimple)
  if (await voiceButton.isVisible().catch(() => false)) {
    await voiceButton.click()
    await expect(queryInput).not.toBeEmpty({ timeout: 5000 }).catch(() => null)
    await queryInput.press('Enter')
    await page.waitForTimeout(7000)
  } else {
    await caption(
      page,
      'Voice input — skipped',
      'Voice input is available in the live application but requires microphone access in the recording environment. The voice-to-text path is functionally identical to typed input.',
    )
    await page.waitForTimeout(1400)
  }

  // ── 4. Voice chat — Agentic AI ────────────────────────────────────────────
  await caption(
    page,
    'Voice chat — Agentic AI',
    'The spoken question enters the full seven-node pipeline with graded retrieval and self-validation — combining natural speech with explainable AI.',
  )
  await switchRagMode(page, 'agentic')
  await setVoiceTranscript(page, questions.voiceAgentic)
  if (await voiceButton.isVisible().catch(() => false)) {
    await voiceButton.click()
    await expect(queryInput).not.toBeEmpty({ timeout: 5000 }).catch(() => null)
    await queryInput.press('Enter')
    await page.waitForTimeout(7000)

    const agenticVoiceTrace = page.getByText(/Agent trace/i).last()
    if (await agenticVoiceTrace.isVisible().catch(() => false)) {
      await caption(
        page,
        'Agentic voice trace',
        'The voice + agentic path produces the same structured trace, combining natural speech with a fully auditable reasoning pipeline.',
      )
      await agenticVoiceTrace.click()
      await page.waitForTimeout(2200)
    }
  } else {
    await caption(
      page,
      'Voice input — skipped',
      'Voice input requires microphone access in the recording environment. The full agentic pipeline behaviour is identical whether the query arrives by voice or text.',
    )
    await page.waitForTimeout(1400)
  }

  // ── Multilingual ──────────────────────────────────────────────────────────
  const languageSelect = page.getByTestId('chat-language-select')
  if (await languageSelect.isVisible().catch(() => false)) {
    await caption(
      page,
      'Captivating feature: multilingual RAG',
      'The same retrieval path can present answers in another language while keeping source filenames grounded.',
    )
    await languageSelect.selectOption('es')
    await queryInput.fill(questions.multilingual)
    await queryInput.press('Enter')
    await page.waitForTimeout(7000)
  } else {
    await caption(
      page,
      'Multilingual output — skipped',
      'The language selector enables answers in additional languages while keeping retrieval grounded to the indexed document. It was not visible at this stage of the walkthrough.',
    )
    await page.waitForTimeout(1400)
  }

  // ── Guardrails ────────────────────────────────────────────────────────────
  await caption(
    page,
    'Task 9: Guardrails',
    'The guardrails console shows input/output safety controls and testing support for safer document Q&A.',
  )
  await page.getByTestId('guardrails-btn').click()
  await expect(page.getByText('Content Guardrails')).toBeVisible()
  await page.waitForTimeout(2200)
  await page.getByTestId('guardrails-close').click()

  // ── Ragas evaluation (admin only) ─────────────────────────────────────────
  if (role === 'admin') {
    await caption(
      page,
      'Task 9: RAG evaluation — Ragas metrics',
      'Ragas measures retrieval quality with four automated metrics: Faithfulness, Answer Relevancy, Context Precision, and Context Recall.',
    )
    await page.getByTestId('settings-btn').click()
    await expect(page.getByRole('dialog')).toBeVisible()

    // Expand the Ragas accordion section
    const ragasToggle = page.getByRole('button', { name: /ragas evaluation/i })
    if (await ragasToggle.isVisible().catch(() => false)) {
      await ragasToggle.scrollIntoViewIfNeeded()
      await ragasToggle.click()
      await page.waitForTimeout(800)

      const triggerBtn = page.getByTestId('ragas-trigger-btn')
      await triggerBtn.scrollIntoViewIfNeeded()

      const hasScores = await page.locator('.bg-white.border.border-slate-200.rounded-lg.p-3').first().isVisible().catch(() => false)
      if (hasScores) {
        await caption(
          page,
          'Ragas quality scores',
          'Live evaluation results: Faithfulness, Answer Relevancy, Context Precision, and Context Recall — each scored 0–100% against sample queries.',
        )
      } else {
        await caption(
          page,
          'Ragas evaluation panel',
          'Click "Run Evaluation" to execute Ragas against indexed documents. Scores update in the panel after the run completes.',
        )
      }
      await page.waitForTimeout(2500)
    } else {
      await caption(
        page,
        'Ragas evaluation — not available',
        'The Ragas evaluation panel was not found in Settings. It requires at least one indexed document and a configured provider key.',
      )
      await page.waitForTimeout(1400)
    }

    await maybeCloseDialog(page)
  }

  // ── Final ─────────────────────────────────────────────────────────────────
  await caption(
    page,
    'Task 10: Deployed and documented',
    'The final package includes deployment guidance, architecture notes, coverage evidence, and this repeatable walkthrough recorder.',
  )
  await page.waitForTimeout(1800)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('guest mode walkthrough', async ({ page }) => {
  test.skip(
    !process.env.WALKTHROUGH_BASE_URL,
    'Set WALKTHROUGH_BASE_URL to a local or Vercel deployment before recording.',
  )
  await runWalkthrough(page, 'guest')
})

test('admin mode walkthrough', async ({ page }) => {
  test.skip(
    !process.env.WALKTHROUGH_BASE_URL,
    'Set WALKTHROUGH_BASE_URL to a local or Vercel deployment before recording.',
  )
  test.skip(
    !username || !password,
    'Set WALKTHROUGH_USERNAME and WALKTHROUGH_PASSWORD to record admin mode.',
  )
  await runWalkthrough(page, 'admin')
})

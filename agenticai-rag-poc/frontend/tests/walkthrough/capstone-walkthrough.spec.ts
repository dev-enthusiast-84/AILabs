import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

const username = process.env.WALKTHROUGH_USERNAME
const password = process.env.WALKTHROUGH_PASSWORD
const interactiveSettings = process.env.WALKTHROUGH_INTERACTIVE_SETTINGS === 'true'
const interactiveTimeoutMs = Number(process.env.WALKTHROUGH_INTERACTIVE_TIMEOUT_MS ?? 600_000)

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
            'What does the document say about RAG ingestion?'
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
  if (await dialog.isVisible().catch(() => false)) {
    const close = page.getByRole('button', { name: /^close/i }).first()
    if (await close.isVisible().catch(() => false)) {
      await close.click()
      await expect(dialog).not.toBeVisible()
    } else {
      await page.keyboard.press('Escape')
    }
  }
}

async function waitForUserSettingsIfRequested(page: Page, prompt: string): Promise<boolean> {
  if (!interactiveSettings) return false

  // Use a retrying assertion instead of a snapshot isVisible() call so that
  // any micro-timing gap between the caller opening the dialog and this check
  // does not silently skip the interactive pause.
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

  await installVoiceDemo(page)
  await loginAs(page, role)

  // ── Settings ──────────────────────────────────────────────────────────────
  await caption(
    page,
    'Task 9: Reliability and safety controls',
    'Settings centralize provider keys, model choices, cost-impact notices, guest locks, and deployment prerequisites.',
  )
  await page.getByTestId('settings-btn').click()
  await expect(page.getByRole('dialog')).toBeVisible()
  const userUpdatedInitialSettings = await waitForUserSettingsIfRequested(
    page,
    'Update provider keys, vector/blob settings, or model choices now if the deployed app needs them. Close Settings to resume recording.',
  )
  if (!userUpdatedInitialSettings) {
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
    const userUpdatedPrereqs = await waitForUserSettingsIfRequested(
      page,
      'A prerequisite prompt opened during upload. Enter the required settings, save, close the modal, and the recorder will continue.',
    )
    if (!userUpdatedPrereqs) {
      await caption(
        page,
        'Prerequisite prompt',
        'The app blocks indexing until required runtime settings are provided through the UI, avoiding accidental account spend.',
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
    'Direct one-shot retrieval: the question goes straight to the LLM with the retrieved context — lowest latency, no multi-step reasoning.',
  )
  await switchRagMode(page, 'simple')
  await queryInput.fill('What is the main topic of this document?')
  await queryInput.press('Enter')
  await page.waitForTimeout(7000)

  // ── 2. Text chat — Agentic AI ─────────────────────────────────────────────
  await caption(
    page,
    'Text chat — Agentic AI',
    'Seven-node LangGraph pipeline: planner → HyDE → retrieval → grader → reranker → generator → validator, with full trace and grounded sources.',
  )
  await switchRagMode(page, 'agentic')
  await queryInput.fill('What is RAG and how does it work?')
  await queryInput.press('Enter')
  await page.waitForTimeout(7000)

  const traceToggle = page.getByText(/Agent trace/i).first()
  if (await traceToggle.isVisible().catch(() => false)) {
    await caption(
      page,
      'Agent trace',
      'Planner, HyDE, retrieval, generation, validation, token counts, and latency are visible for explainability.',
    )
    await traceToggle.click()
    await page.waitForTimeout(2200)
  }

  const source = page.getByTitle('Click to view document content').first()
  if (await source.isVisible().catch(() => false)) {
    await caption(
      page,
      'Grounded sources',
      'Source links open the indexed document preview so viewers can inspect the evidence behind every answer.',
    )
    await source.click()
    await page.waitForTimeout(2200)
    await maybeCloseDialog(page)
  }

  // ── 3. Voice chat — Simple RAG ────────────────────────────────────────────
  await caption(
    page,
    'Voice chat — Simple RAG',
    'A spoken question feeds the same direct retrieval path — the mic icon transcribes speech and submits it as a normal query.',
  )
  await switchRagMode(page, 'simple')
  await setVoiceTranscript(page, 'What are the key concepts explained in this document?')
  if (await voiceButton.isVisible().catch(() => false)) {
    await voiceButton.click()
    await expect(queryInput).toHaveValue(/key concepts/i)
    await queryInput.press('Enter')
    await page.waitForTimeout(7000)
  }

  // ── 4. Voice chat — Agentic AI ────────────────────────────────────────────
  await caption(
    page,
    'Voice chat — Agentic AI',
    'The spoken question enters the full seven-node pipeline with graded retrieval and self-validation — combining natural speech with explainable AI.',
  )
  await switchRagMode(page, 'agentic')
  await setVoiceTranscript(page, 'What does the document say about RAG ingestion?')
  if (await voiceButton.isVisible().catch(() => false)) {
    await voiceButton.click()
    await expect(queryInput).toHaveValue(/RAG ingestion/i)
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
  }

  // ── Multilingual ──────────────────────────────────────────────────────────
  await caption(
    page,
    'Captivating feature: multilingual RAG',
    'The same retrieval path can present answers in another language while keeping source filenames grounded.',
  )
  const languageSelect = page.getByTestId('chat-language-select')
  if (await languageSelect.isVisible().catch(() => false)) {
    await languageSelect.selectOption('es')
    await queryInput.fill('What does the document say about ingestion?')
    await queryInput.press('Enter')
    await page.waitForTimeout(7000)
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

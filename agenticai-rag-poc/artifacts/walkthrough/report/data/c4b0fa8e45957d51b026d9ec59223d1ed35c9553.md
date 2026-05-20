# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: capstone-walkthrough.spec.ts >> admin mode walkthrough
- Location: tests/walkthrough/capstone-walkthrough.spec.ts:435:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByTestId('dropzone')
Expected: visible
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 15000ms
  - waiting for getByTestId('dropzone')

```

# Test source

```ts
  94  |       }
  95  |       abort() {
  96  |         this.onend?.()
  97  |       }
  98  |     }
  99  | 
  100 |     Object.defineProperty(window, 'SpeechRecognition', {
  101 |       value: DemoSpeechRecognition,
  102 |       configurable: true,
  103 |     })
  104 |     Object.defineProperty(window, 'webkitSpeechRecognition', {
  105 |       value: DemoSpeechRecognition,
  106 |       configurable: true,
  107 |     })
  108 |   })
  109 | }
  110 | 
  111 | /** Set the transcript that the next voice-button click will produce. */
  112 | async function setVoiceTranscript(page: Page, transcript: string): Promise<void> {
  113 |   await page.evaluate(
  114 |     (t) => {
  115 |       type VoiceWindow = { __WALKTHROUGH_VOICE_TRANSCRIPT__?: string }
  116 |       ;(window as unknown as VoiceWindow).__WALKTHROUGH_VOICE_TRANSCRIPT__ = t
  117 |     },
  118 |     transcript,
  119 |   )
  120 | }
  121 | 
  122 | // ---------------------------------------------------------------------------
  123 | // Helpers
  124 | // ---------------------------------------------------------------------------
  125 | 
  126 | async function maybeCloseDialog(page: Page): Promise<void> {
  127 |   const dialog = page.getByRole('dialog')
  128 |   if (await dialog.isVisible().catch(() => false)) {
  129 |     const close = page.getByRole('button', { name: /^close/i }).first()
  130 |     if (await close.isVisible().catch(() => false)) {
  131 |       await close.click()
  132 |       await expect(dialog).not.toBeVisible()
  133 |     } else {
  134 |       await page.keyboard.press('Escape')
  135 |     }
  136 |   }
  137 | }
  138 | 
  139 | async function waitForUserSettingsIfRequested(page: Page, prompt: string): Promise<boolean> {
  140 |   if (!interactiveSettings) return false
  141 | 
  142 |   // Use a retrying assertion instead of a snapshot isVisible() call so that
  143 |   // any micro-timing gap between the caller opening the dialog and this check
  144 |   // does not silently skip the interactive pause.
  145 |   const dialog = page.getByRole('dialog')
  146 |   try {
  147 |     await expect(dialog).toBeVisible({ timeout: 3000 })
  148 |   } catch {
  149 |     return false
  150 |   }
  151 | 
  152 |   await caption(page, 'Interactive settings pause', prompt)
  153 |   await page.waitForFunction(
  154 |     () => !document.querySelector('[role="dialog"]'),
  155 |     undefined,
  156 |     { timeout: interactiveTimeoutMs },
  157 |   )
  158 |   await page.waitForTimeout(1000)
  159 |   return true
  160 | }
  161 | 
  162 | /** Click the Simple or Agentic mode button in the toolbar. */
  163 | async function switchRagMode(page: Page, mode: 'simple' | 'agentic'): Promise<void> {
  164 |   const modeGroup = page.getByRole('group', { name: 'RAG mode selector' })
  165 |   const btn = modeGroup.getByRole('button', { name: new RegExp(mode, 'i') })
  166 |   if (await btn.isVisible().catch(() => false)) {
  167 |     await btn.click()
  168 |     await page.waitForTimeout(400)
  169 |   }
  170 | }
  171 | 
  172 | // ---------------------------------------------------------------------------
  173 | // Login
  174 | // ---------------------------------------------------------------------------
  175 | 
  176 | async function loginAs(page: Page, role: 'guest' | 'admin'): Promise<void> {
  177 |   await caption(
  178 |     page,
  179 |     'Capstone Walkthrough',
  180 |     'The Edureka task list drives this tour: foundation, UI, ingestion, semantic search, vector retrieval, agentic RAG, safety, deployment, and docs.',
  181 |   )
  182 |   await page.goto('/login')
  183 |   await expect(page.getByText('Agentic RAG')).toBeVisible()
  184 | 
  185 |   if (role === 'admin') {
  186 |     await caption(
  187 |       page,
  188 |       'Task 1-2: Project foundation and UI',
  189 |       'Signing in as admin to show the full deployed application experience.',
  190 |     )
  191 |     await page.getByTestId('username-input').fill(username!)
  192 |     await page.getByTestId('password-input').fill(password!)
  193 |     await page.getByTestId('login-button').click()
> 194 |     await expect(page.getByTestId('dropzone')).toBeVisible()
      |                                                ^ Error: expect(locator).toBeVisible() failed
  195 |   } else {
  196 |     await caption(
  197 |       page,
  198 |       'Guest Experience',
  199 |       'Using guest mode — same chat and TXT upload path, no credentials required.',
  200 |     )
  201 |     await page.getByTestId('guest-button').click()
  202 |     await expect(page.getByTestId('dropzone')).toBeVisible()
  203 |   }
  204 | }
  205 | 
  206 | // ---------------------------------------------------------------------------
  207 | // Core walkthrough — runs identically for guest and admin
  208 | // ---------------------------------------------------------------------------
  209 | 
  210 | async function runWalkthrough(page: Page, role: 'guest' | 'admin'): Promise<void> {
  211 |   const uploadFile = resolveUploadFile(role)
  212 | 
  213 |   await installVoiceDemo(page)
  214 |   await loginAs(page, role)
  215 | 
  216 |   // ── Settings ──────────────────────────────────────────────────────────────
  217 |   await caption(
  218 |     page,
  219 |     'Task 9: Reliability and safety controls',
  220 |     'Settings centralize provider keys, model choices, cost-impact notices, guest locks, and deployment prerequisites.',
  221 |   )
  222 |   await page.getByTestId('settings-btn').click()
  223 |   await expect(page.getByRole('dialog')).toBeVisible()
  224 |   const userUpdatedInitialSettings = await waitForUserSettingsIfRequested(
  225 |     page,
  226 |     'Update provider keys, vector/blob settings, or model choices now if the deployed app needs them. Close Settings to resume recording.',
  227 |   )
  228 |   if (!userUpdatedInitialSettings) {
  229 |     await page.waitForTimeout(1800)
  230 |     await maybeCloseDialog(page)
  231 |   }
  232 | 
  233 |   // ── Upload ────────────────────────────────────────────────────────────────
  234 |   await caption(
  235 |     page,
  236 |     'Task 3-5: Ingestion, chunks, embeddings, vector store',
  237 |     `${role === 'admin' ? 'Uploading a sample PDF' : 'Uploading a guest TXT file'} to process enterprise content into retrievable chunks.`,
  238 |   )
  239 |   await page.getByTestId('file-input').setInputFiles(uploadFile)
  240 |   await page.waitForTimeout(2500)
  241 | 
  242 |   const settingsDialogOpened = await page.getByRole('dialog').isVisible().catch(() => false)
  243 |   if (settingsDialogOpened) {
  244 |     const userUpdatedPrereqs = await waitForUserSettingsIfRequested(
  245 |       page,
  246 |       'A prerequisite prompt opened during upload. Enter the required settings, save, close the modal, and the recorder will continue.',
  247 |     )
  248 |     if (!userUpdatedPrereqs) {
  249 |       await caption(
  250 |         page,
  251 |         'Prerequisite prompt',
  252 |         'The app blocks indexing until required runtime settings are provided through the UI, avoiding accidental account spend.',
  253 |       )
  254 |       await maybeCloseDialog(page)
  255 |     }
  256 |   } else {
  257 |     await page.waitForTimeout(2500)
  258 |   }
  259 | 
  260 |   const queryInput = page.getByTestId('query-input')
  261 |   const voiceButton = page.getByTestId('voice-input-btn')
  262 | 
  263 |   // ── 1. Text chat — Simple RAG ─────────────────────────────────────────────
  264 |   await caption(
  265 |     page,
  266 |     'Text chat — Simple RAG',
  267 |     'Direct one-shot retrieval: the question goes straight to the LLM with the retrieved context — lowest latency, no multi-step reasoning.',
  268 |   )
  269 |   await switchRagMode(page, 'simple')
  270 |   await queryInput.fill('What is the main topic of this document?')
  271 |   await queryInput.press('Enter')
  272 |   await page.waitForTimeout(7000)
  273 | 
  274 |   // ── 2. Text chat — Agentic AI ─────────────────────────────────────────────
  275 |   await caption(
  276 |     page,
  277 |     'Text chat — Agentic AI',
  278 |     'Seven-node LangGraph pipeline: planner → HyDE → retrieval → grader → reranker → generator → validator, with full trace and grounded sources.',
  279 |   )
  280 |   await switchRagMode(page, 'agentic')
  281 |   await queryInput.fill('What is RAG and how does it work?')
  282 |   await queryInput.press('Enter')
  283 |   await page.waitForTimeout(7000)
  284 | 
  285 |   const traceToggle = page.getByText(/Agent trace/i).first()
  286 |   if (await traceToggle.isVisible().catch(() => false)) {
  287 |     await caption(
  288 |       page,
  289 |       'Agent trace',
  290 |       'Planner, HyDE, retrieval, generation, validation, token counts, and latency are visible for explainability.',
  291 |     )
  292 |     await traceToggle.click()
  293 |     await page.waitForTimeout(2200)
  294 |   }
```
# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: capstone-walkthrough.spec.ts >> guest mode walkthrough
- Location: tests/walkthrough/capstone-walkthrough.spec.ts:427:1

# Error details

```
Error: locator.fill: Target page, context or browser has been closed
Call log:
  - waiting for getByTestId('query-input')
    - locator resolved to <input disabled value="" type="text" maxlength="1000" class="input flex-1" data-testid="query-input" aria-label="Question input" placeholder="Upload a document first…"/>
    - fill("What is the main topic of this document?")
  - attempting fill action
    2 × waiting for element to be visible, enabled and editable
      - element is not enabled
    - retrying fill action
    - waiting 20ms
    2 × waiting for element to be visible, enabled and editable
      - element is not enabled
    - retrying fill action
      - waiting 100ms
    5 × waiting for element to be visible, enabled and editable
      - element is not enabled
    - retrying fill action
      - waiting 500ms

```

# Test source

```ts
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
  194 |     await expect(page.getByTestId('dropzone')).toBeVisible()
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
> 270 |   await queryInput.fill('What is the main topic of this document?')
      |                    ^ Error: locator.fill: Target page, context or browser has been closed
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
  295 | 
  296 |   const source = page.getByTitle('Click to view document content').first()
  297 |   if (await source.isVisible().catch(() => false)) {
  298 |     await caption(
  299 |       page,
  300 |       'Grounded sources',
  301 |       'Source links open the indexed document preview so viewers can inspect the evidence behind every answer.',
  302 |     )
  303 |     await source.click()
  304 |     await page.waitForTimeout(2200)
  305 |     await maybeCloseDialog(page)
  306 |   }
  307 | 
  308 |   // ── 3. Voice chat — Simple RAG ────────────────────────────────────────────
  309 |   await caption(
  310 |     page,
  311 |     'Voice chat — Simple RAG',
  312 |     'A spoken question feeds the same direct retrieval path — the mic icon transcribes speech and submits it as a normal query.',
  313 |   )
  314 |   await switchRagMode(page, 'simple')
  315 |   await setVoiceTranscript(page, 'What are the key concepts explained in this document?')
  316 |   if (await voiceButton.isVisible().catch(() => false)) {
  317 |     await voiceButton.click()
  318 |     await expect(queryInput).toHaveValue(/key concepts/i)
  319 |     await queryInput.press('Enter')
  320 |     await page.waitForTimeout(7000)
  321 |   }
  322 | 
  323 |   // ── 4. Voice chat — Agentic AI ────────────────────────────────────────────
  324 |   await caption(
  325 |     page,
  326 |     'Voice chat — Agentic AI',
  327 |     'The spoken question enters the full seven-node pipeline with graded retrieval and self-validation — combining natural speech with explainable AI.',
  328 |   )
  329 |   await switchRagMode(page, 'agentic')
  330 |   await setVoiceTranscript(page, 'What does the document say about RAG ingestion?')
  331 |   if (await voiceButton.isVisible().catch(() => false)) {
  332 |     await voiceButton.click()
  333 |     await expect(queryInput).toHaveValue(/RAG ingestion/i)
  334 |     await queryInput.press('Enter')
  335 |     await page.waitForTimeout(7000)
  336 | 
  337 |     const agenticVoiceTrace = page.getByText(/Agent trace/i).last()
  338 |     if (await agenticVoiceTrace.isVisible().catch(() => false)) {
  339 |       await caption(
  340 |         page,
  341 |         'Agentic voice trace',
  342 |         'The voice + agentic path produces the same structured trace, combining natural speech with a fully auditable reasoning pipeline.',
  343 |       )
  344 |       await agenticVoiceTrace.click()
  345 |       await page.waitForTimeout(2200)
  346 |     }
  347 |   }
  348 | 
  349 |   // ── Multilingual ──────────────────────────────────────────────────────────
  350 |   await caption(
  351 |     page,
  352 |     'Captivating feature: multilingual RAG',
  353 |     'The same retrieval path can present answers in another language while keeping source filenames grounded.',
  354 |   )
  355 |   const languageSelect = page.getByTestId('chat-language-select')
  356 |   if (await languageSelect.isVisible().catch(() => false)) {
  357 |     await languageSelect.selectOption('es')
  358 |     await queryInput.fill('What does the document say about ingestion?')
  359 |     await queryInput.press('Enter')
  360 |     await page.waitForTimeout(7000)
  361 |   }
  362 | 
  363 |   // ── Guardrails ────────────────────────────────────────────────────────────
  364 |   await caption(
  365 |     page,
  366 |     'Task 9: Guardrails',
  367 |     'The guardrails console shows input/output safety controls and testing support for safer document Q&A.',
  368 |   )
  369 |   await page.getByTestId('guardrails-btn').click()
  370 |   await expect(page.getByText('Content Guardrails')).toBeVisible()
```
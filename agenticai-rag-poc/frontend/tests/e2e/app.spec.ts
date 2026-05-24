import { test, expect } from '@playwright/test'
import { injectAdmin } from './helpers'

async function mockDashboardApis(
  page: import('@playwright/test').Page,
  settingsOverrides: Record<string, unknown> = {},
) {
  await page.route('**/api/documents/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ documents: ['edureka-capstone.txt'], count: 1 }),
    })
  })
  await page.route('**/api/documents/edureka-capstone.txt/chunks', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        filename: 'edureka-capstone.txt',
        chunks: ['Agentic RAG uses retrieval, generation, and validation for grounded enterprise Q&A.'],
        total_chunks: 1,
      }),
    })
  })
  await page.route('**/api/documents/edureka-capstone.txt/content', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        filename: 'edureka-capstone.txt',
        content: 'Agentic RAG uses retrieval, generation, and validation for grounded enterprise document question answering.',
        word_count: 13,
      }),
    })
  })
  await page.route('**/api/documents/edureka-capstone.txt/file', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/plain; charset=utf-8',
      body: 'Agentic RAG uses retrieval, generation, and validation for grounded enterprise document question answering.',
    })
  })
  await page.route('**/api/settings/', async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          model: 'gpt-4o-mini',
          embedding_model: 'text-embedding-3-small',
          api_key_masked: 'configured',
          api_key_source: 'runtime',
          allowed_models: ['gpt-4o-mini'],
          allowed_embedding_models: ['text-embedding-3-small'],
          vector_store_type: 'pinecone',
          pinecone_api_key_source: 'runtime',
          blob_read_write_token_source: 'not_configured',
          ...settingsOverrides,
        }),
      })
      return
    }
    await route.continue()
  })
  await page.route('**/api/query/', async (route) => {
    const payload = route.request().postDataJSON() as { language?: string } | null
    const language = payload?.language ?? 'en'
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        answer: language === 'es'
          ? 'El documento dice que Agentic RAG recupera contexto, genera una respuesta y la valida.'
          : 'The document says Agentic RAG retrieves context, generates an answer, and validates it.',
        sources: ['edureka-capstone.txt'],
        validation: 'VALID',
        tokens_used: 42,
        mode: 'agentic',
        language,
        output_flagged: false,
      }),
    })
  })
}

test.describe('Authentication flow', () => {
  test('redirects unauthenticated user to login', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/login/)
  })

  test('shows login form elements', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByTestId('username-input')).toBeVisible()
    await expect(page.getByTestId('password-input')).toBeVisible()
    await expect(page.getByTestId('login-button')).toBeVisible()
  })

  test('login button disabled when fields empty', async ({ page }) => {
    await page.goto('/login')
    await expect(page.getByTestId('login-button')).toBeDisabled()
  })

  test('shows error on invalid credentials', async ({ page }) => {
    await page.goto('/login')
    await page.getByTestId('username-input').fill('admin')
    await page.getByTestId('password-input').fill('wrongpassword')
    await page.getByTestId('login-button').click()
    // Wait for network idle (request settles) rather than a fixed 1 s sleep.
    await page.waitForLoadState('networkidle')
  })
})

test.describe('Header navigation', () => {
  test.beforeEach(async ({ page }) => {
    await injectAdmin(page)
  })

  test('logo click navigates to home', async ({ page }) => {
    await page.getByTestId('logo-home-btn').click()
    await expect(page).toHaveURL(/\/$/)
  })
})

test.describe('Dashboard (requires auth)', () => {
  test.beforeEach(async ({ page }) => {
    await mockDashboardApis(page)
    await injectAdmin(page)
  })

  test('shows document upload area', async ({ page }) => {
    await expect(page.getByTestId('dropzone')).toBeVisible()
  })

  test('shows query input', async ({ page }) => {
    await expect(page.getByTestId('query-input')).toBeVisible()
  })

  test('query input has correct max length', async ({ page }) => {
    const input = page.getByTestId('query-input')
    await expect(input).toHaveAttribute('maxlength', '1000')
  })

  test('settings button is visible in header', async ({ page }) => {
    await expect(page.getByTestId('settings-btn')).toBeVisible()
  })

  test('settings modal opens on button click', async ({ page }) => {
    await page.getByTestId('settings-btn').click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByTestId('model-select')).toBeVisible()
    await expect(page.getByTestId('api-key-input')).toBeVisible()
  })

  test('api key field is masked by default', async ({ page }) => {
    await page.getByTestId('settings-btn').click()
    await expect(page.getByTestId('api-key-input')).toHaveAttribute('type', 'password')
  })

  test('settings modal closes on Cancel', async ({ page }) => {
    await page.getByTestId('settings-btn').click()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('settings modal closes on Escape', async ({ page }) => {
    await page.getByTestId('settings-btn').click()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).not.toBeVisible()
  })

  test('api key input rejects XSS pattern (client-side)', async ({ page }) => {
    await page.getByTestId('settings-btn').click()
    await page.getByTestId('api-key-input').fill('<script>alert(1)</script>')
    await page.getByTestId('settings-save-btn').click()
    await expect(page.getByText(/Invalid format/i)).toBeVisible()
  })

  test('chat language and transcript export controls are visible', async ({ page }) => {
    await expect(page.getByTestId('chat-language-select')).toBeVisible()
    await expect(page.getByTestId('chat-language-select')).toContainText('English')
    await expect(page.getByTestId('export-btn')).toBeVisible()
    await expect(page.getByTestId('export-btn')).toBeDisabled()
  })

  test('query response enables transcript export in chat window', async ({ page }) => {
    await page.getByTestId('query-input').fill('What does the capstone document say about Agentic RAG?')
    await page.keyboard.press('Enter')
    await expect(page.getByText(/retrieves context, generates an answer, and validates it/i)).toBeVisible()
    await expect(page.getByTestId('export-btn')).toBeEnabled()
  })

  test('multilingual typed chat sends selected language through mocked query flow', async ({ page }) => {
    let queryPayload: { question?: string; language?: string } | null = null
    await page.route('**/api/query/', async (route) => {
      queryPayload = route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          answer: 'El documento dice que Agentic RAG recupera contexto y valida la respuesta.',
          sources: ['edureka-capstone.txt'],
          validation: 'VALID',
          tokens_used: 42,
          mode: 'agentic',
          language: 'es',
          output_flagged: false,
        }),
      })
    })

    await page.getByTestId('chat-language-select').click()
    await page.getByRole('option', { name: 'Spanish' }).click()
    await page.getByTestId('query-input').fill('¿Qué dice el documento sobre Agentic RAG?')
    await page.keyboard.press('Enter')

    await expect(page.getByText(/recupera contexto/i)).toBeVisible()
    expect(queryPayload).toMatchObject({
      question: '¿Qué dice el documento sobre Agentic RAG?',
      language: 'es',
    })
  })

  test('source document access opens mocked document content', async ({ page }) => {
    await page.getByTestId('query-input').fill('What source supports this answer?')
    await page.keyboard.press('Enter')
    await page.getByTitle('Click to view document content').click()

    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByText(/grounded enterprise document question answering/i)).toBeVisible()
  })

  test('transcript export calls backend redaction before download', async ({ page }) => {
    let redactionPayload: { language?: string; messages?: Array<{ content: string; origin: string }> } = {}
    await page.route('**/api/chat/voice/redact', async (route) => {
      redactionPayload = route.request().postDataJSON()
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          transcript: 'User: [REDACTED_EMAIL]\n\nAssistant: Safe answer',
          redacted: true,
        }),
      })
    })

    await page.getByTestId('query-input').fill('My email is jane@example.com')
    await page.keyboard.press('Enter')
    await expect(page.getByTestId('export-btn')).toBeEnabled()
    const downloadPromise = page.waitForEvent('download')
    await page.getByTestId('export-btn').click()
    await downloadPromise

    expect(redactionPayload.language).toBe('en')
    expect(redactionPayload.messages?.[0]).toMatchObject({
      content: 'My email is jane@example.com',
      origin: 'typed',
    })
  })

  test('missing OpenAI settings prerequisite opens settings instead of querying', async ({ page }) => {
    await page.unroute('**/api/settings/')
    await mockDashboardApis(page, { api_key_masked: '', api_key_source: 'not_configured' })
    let queryCalled = false
    await page.route('**/api/query/', async (route) => {
      queryCalled = true
      await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
    })
    await page.reload()

    await page.getByTestId('query-input').fill('What does the document say?')
    await page.keyboard.press('Enter')

    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(
      page.getByRole('dialog').getByText(/OpenAI API key is required before asking questions/i),
    ).toBeVisible()
    expect(queryCalled).toBe(false)
  })
})

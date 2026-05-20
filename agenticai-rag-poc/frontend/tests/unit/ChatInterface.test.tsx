/**
 * Unit tests for ChatInterface.
 * Covers: empty/loaded doc states, suggestion chips, mode toggle,
 * validation badge copy, latency and retry display, agent trace accordion.
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import ChatInterface from '@/components/ChatInterface'
import type { AgentTrace } from '@/types'
import type { ComponentProps } from 'react'
import toast from 'react-hot-toast'

// jsdom doesn't implement scrollIntoView — stub it globally
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
  URL.createObjectURL = vi.fn(() => 'blob:mock')
  URL.revokeObjectURL = vi.fn()
  HTMLAnchorElement.prototype.click = vi.fn()
})

// Ensure getContent always returns a resolved Promise so the useEffect's
// Promise.allSettled().then() microtask settles inside act() for every test.
// Suites that need specific content override this in their own beforeEach.
beforeEach(async () => {
  const { documentsApi, settingsApi, voiceApi } = await import('@/services/api')
  vi.mocked(documentsApi.getContent).mockResolvedValue({
    filename: '',
    content: '',
    word_count: 0,
  })
  vi.mocked(settingsApi.get).mockResolvedValue({
    api_key_source: 'runtime',
    vector_store_type: 'chroma',
    pinecone_api_key_source: 'not_configured',
  } as never)
  vi.mocked(voiceApi.redactTranscript).mockRejectedValue({ response: { status: 404 } })
})

vi.mock('@/services/api', () => ({
  documentsApi: {
    getContent: vi.fn(),
  },
  queryApi: { ask: vi.fn() },
  voiceApi: { exportAudio: vi.fn(), redactTranscript: vi.fn() },
  settingsApi: { get: vi.fn() },
  extractErrorMessage: (e: unknown) => String(e),
}))

vi.mock('react-hot-toast', () => ({ default: { error: vi.fn(), success: vi.fn() } }))

const renderChat = async (
  documents: string[] = ['test.txt'],
  props: Partial<ComponentProps<typeof ChatInterface>> = {},
) => {
  const result = render(<ChatInterface documents={documents} {...props} />)
  if (documents.length > 0) {
    // Drain the suggestions effect. Suggestions are content-derived and may be
    // empty, so wait for the loading hint to leave rather than a specific chip.
    await waitFor(() => expect(screen.queryByText('Reading uploaded content…')).toBeNull())
    await act(async () => { await new Promise(r => setTimeout(r, 0)) })
  }
  return result
}

/** Helper: submit a query and drain sendMessage's async continuation.
 *  The mock queryApi.ask resolves as a microtask between fireEvent.submit
 *  returning and waitFor starting — wrapping both in act() + setTimeout(0)
 *  ensures setMessages/setLoading state updates land inside act(). */
async function submitQuery(question: string) {
  const input = screen.getByTestId('query-input')
  fireEvent.change(input, { target: { value: question } })
  await act(async () => {
    fireEvent.submit(input.closest('form')!)
    await new Promise(r => setTimeout(r, 0))
  })
}

async function readBlobText(blob: Blob): Promise<string> {
  if ('text' in blob && typeof blob.text === 'function') return blob.text()
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(blob)
  })
}

/** Build a minimal AgentTrace for testing */
const makeTrace = (overrides: Partial<AgentTrace> = {}): AgentTrace => ({
  original_question: 'Test question',
  refined_query: 'refined test query',
  chunks_found: 3,
  validation_reason: 'Answer is grounded in the provided context.',
  retries: 0,
  chunks_after_grading: 3,
  chunks_after_rerank: 3,
  hyde_tokens: 0,
  hyde_latency_ms: 0,
  grader_tokens: 0,
  grader_latency_ms: 0,
  reranker_latency_ms: 0,
  planner_tokens: 50,
  generator_tokens: 200,
  validator_tokens: 80,
  planner_latency_ms: 400,
  generator_latency_ms: 1200,
  validator_latency_ms: 350,
  planner_model: 'gpt-4o-mini',
  generator_model: 'gpt-4o',
  validator_model: 'gpt-4o-mini',
  hypothetical_answer: '',
  query_variants: [],
  ...overrides,
})

// ── Empty / loaded document state ────────────────────────────────────────────

describe('ChatInterface — empty doc state', () => {
  it('shows "no documents" prompt when document list is empty', async () => {
    await renderChat([])
    expect(screen.getByText(/no documents indexed yet/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /summarize/i })).toBeNull()
  })

  it('disables the query input when no documents are loaded', async () => {
    await renderChat([])
    expect(screen.getByTestId('query-input')).toBeDisabled()
  })

  it('disables the send button when no documents are loaded', async () => {
    await renderChat([])
    expect(screen.getByRole('button', { name: /send question/i })).toBeDisabled()
  })
})

describe('ChatInterface — with loaded documents', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    const { documentsApi } = await import('@/services/api')
    vi.mocked(documentsApi.getContent).mockResolvedValue({
      filename: 'test.txt',
      content: 'Quarterly revenue improved because customer retention and onboarding completion improved. Customer retention is the strongest theme. Support response time decreased while renewal risk stayed low.',
      word_count: 12,
    })
  })

  it('shows content-based suggestion chips when documents are present', async () => {
    await renderChat(['annual_report.pdf', 'hr_policy.txt'])
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /customer retention/i })).toBeInTheDocument(),
    )
    expect(screen.getAllByRole('button', { name: /what details does the document provide about/i }).length).toBeGreaterThanOrEqual(3)
    expect(screen.queryByText(/summarize annual_report/i)).toBeNull()
    expect(screen.queryByText(/summarize hr_policy/i)).toBeNull()
    expect(screen.queryByText(/summarize the uploaded content/i)).toBeNull()
    expect(screen.queryByText(/related to|compare/i)).toBeNull()
  })

  it('does NOT show hardcoded generic or filename-based queries', async () => {
    await renderChat(['report.pdf'])
    expect(screen.queryByText(/remote work policy/i)).toBeNull()
    expect(screen.queryByText(/top performing departments/i)).toBeNull()
    expect(screen.queryByText(/uploaded content/i)).toBeNull()
    expect(screen.queryByText(/report\.pdf/i)).toBeNull()
  })

  it('does not load sample queries when content cannot produce relevant questions', async () => {
    const { documentsApi } = await import('@/services/api')
    vi.mocked(documentsApi.getContent).mockResolvedValue({
      filename: 'thin.txt',
      content: 'ok yes',
      word_count: 2,
    })
    await renderChat(['thin.txt'])
    expect(screen.getByText(/Start by asking about a topic/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /what details does the document provide about|document say|related|important details|compare|summarize/i })).toBeNull()
  })

  it('enables the query input when documents are present', async () => {
    await renderChat(['doc.txt'])
    expect(screen.getByTestId('query-input')).not.toBeDisabled()
  })

  it('clicking a suggestion chip sends the query', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Test answer',
      sources: ['doc.txt'],
      validation: 'VALID',
      tokens_used: 5,
      mode: 'agentic',
    })
    await renderChat(['report.txt'])
    const chip = await screen.findByRole('button', { name: /customer retention/i })
    fireEvent.click(chip)
    await waitFor(() => expect(queryApi.ask).toHaveBeenCalledOnce())
    const call = vi.mocked(queryApi.ask).mock.calls[0][0]
    expect(call.question).toMatch(/retention/i)
  })

  it('sends recent chat history so follow-up questions keep context', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask)
      .mockResolvedValueOnce({
        answer: 'RAG includes ingestion, retrieval, generation, and validation.',
        sources: ['doc.txt'],
        validation: 'VALID',
        tokens_used: 100,
        mode: 'agentic',
      })
      .mockResolvedValueOnce({
        answer: 'Ingestion prepares uploaded documents for retrieval.',
        sources: ['doc.txt'],
        validation: 'VALID',
        tokens_used: 80,
        mode: 'agentic',
      })

    await renderChat(['doc.txt'])
    await submitQuery('What is RAG?')
    await waitFor(() => expect(screen.getByText(/RAG includes ingestion/i)).toBeInTheDocument())
    await submitQuery('Ingestion')

    await waitFor(() => expect(queryApi.ask).toHaveBeenCalledTimes(2))
    const followUp = vi.mocked(queryApi.ask).mock.calls[1][0]
    expect(followUp.question).toBe('Ingestion')
    expect(followUp.history).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ role: 'user', content: 'What is RAG?' }),
        expect.objectContaining({ role: 'assistant', content: expect.stringMatching(/RAG includes ingestion/i) }),
      ]),
    )
  })

  it('shows query failures as an assistant message without a toast', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockRejectedValue(new Error('No documents have been indexed yet.'))
    await renderChat(['report.txt'])
    await submitQuery('What can I ask?')
    await waitFor(() => screen.getByText('Error: No documents have been indexed yet.'))
    expect(screen.queryByText('🤖 Agentic RAG')).not.toBeInTheDocument()
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('opens settings when OpenAI key is missing before chat', async () => {
    const { settingsApi, queryApi } = await import('@/services/api')
    vi.mocked(settingsApi.get).mockResolvedValue({
      api_key_source: 'not_configured',
      vector_store_type: 'chroma',
      pinecone_api_key_source: 'not_configured',
    } as never)
    const onOpenSettings = vi.fn()
    await renderChat(['report.txt'], { onOpenSettings })
    await submitQuery('What changed?')
    await waitFor(() =>
      expect(onOpenSettings).toHaveBeenCalledWith(expect.stringMatching(/OpenAI API key is required before asking questions/)),
    )
    expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/OpenAI API key is required before asking questions/))
    expect(queryApi.ask).not.toHaveBeenCalled()
  })

  it('opens settings when Pinecone is selected without a key before chat', async () => {
    const { settingsApi, queryApi } = await import('@/services/api')
    vi.mocked(settingsApi.get).mockResolvedValue({
      api_key_source: 'runtime',
      vector_store_type: 'pinecone',
      pinecone_api_key_source: 'not_configured',
    } as never)
    const onOpenSettings = vi.fn()
    await renderChat(['report.txt'], { onOpenSettings })
    await submitQuery('What changed?')
    await waitFor(() =>
      expect(onOpenSettings).toHaveBeenCalledWith(expect.stringMatching(/Pinecone API key is required before asking questions/)),
    )
    expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/Pinecone API key is required before asking questions/))
    expect(queryApi.ask).not.toHaveBeenCalled()
  })

  it('opens settings when Blob storage is selected without a token before chat', async () => {
    const { settingsApi, queryApi } = await import('@/services/api')
    vi.mocked(settingsApi.get).mockResolvedValue({
      api_key_source: 'runtime',
      vector_store_type: 'chroma',
      file_store_type: 'blob',
      pinecone_api_key_source: 'not_configured',
      blob_read_write_token_source: 'not_configured',
    } as never)
    const onOpenSettings = vi.fn()
    await renderChat(['report.txt'], { onOpenSettings })
    await submitQuery('What changed?')
    await waitFor(() =>
      expect(onOpenSettings).toHaveBeenCalledWith(expect.stringMatching(/Blob read\/write token is required before asking questions/)),
    )
    expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/Blob read\/write token is required before asking questions/))
    expect(queryApi.ask).not.toHaveBeenCalled()
  })

  it('suggestion chips are capped at 4 regardless of doc count', async () => {
    await renderChat(['a.txt', 'b.txt', 'c.txt', 'd.txt', 'e.txt'])
    await screen.findByRole('button', { name: /customer retention/i })
    const chips = screen.getAllByRole('button', { name: /what details does the document provide about/i })
    expect(chips.length).toBeLessThanOrEqual(4)
  })
})

// ── Mode toggle ───────────────────────────────────────────────────────────────

describe('ChatInterface — mode toggle', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders mode toggle with Agentic selected by default', async () => {
    await renderChat()
    const simpleBtn = screen.getByRole('button', { name: /⚡ Simple/i })
    const agenticBtn = screen.getByRole('button', { name: /🤖 Agentic/i })
    expect(simpleBtn).toBeInTheDocument()
    expect(agenticBtn).toBeInTheDocument()
    expect(agenticBtn).toHaveAttribute('aria-pressed', 'true')
    expect(simpleBtn).toHaveAttribute('aria-pressed', 'false')
  })

  it('clicking Simple sets mode to simple and passes it in query request', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Simple answer',
      sources: ['test.txt'],
      validation: 'VALID',
      mode: 'simple',
      tokens_used: 50,
    })

    await renderChat()
    fireEvent.click(screen.getByRole('button', { name: /⚡ Simple/i }))
    await submitQuery('What is this?')

    await waitFor(() => expect(queryApi.ask).toHaveBeenCalledOnce())
    const callArg = vi.mocked(queryApi.ask).mock.calls[0][0]
    expect(callArg.mode).toBe('simple')
    expect(callArg.question).toBe('What is this?')
  })

  it('simple-mode response shows mode label and no validation badge', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Quick answer without agent',
      sources: ['test.txt'],
      validation: 'VALID',
      mode: 'simple',
      tokens_used: 30,
    })

    await renderChat()
    fireEvent.click(screen.getByRole('button', { name: /⚡ Simple/i }))
    await submitQuery('Tell me something')

    await waitFor(() =>
      expect(screen.getByText('⚡ Simple RAG')).toBeInTheDocument()
    )
    expect(screen.queryByText('Verified')).toBeNull()
    expect(screen.queryByText('Unverified')).toBeNull()
  })

  it('agentic-mode response shows validation badge', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Agentic answer with validation',
      sources: ['test.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 200,
    })

    await renderChat()
    await submitQuery('Explain something')

    await waitFor(() =>
      expect(screen.getByText('Verified')).toBeInTheDocument()
    )
    expect(screen.getByText('🤖 Agentic RAG')).toBeInTheDocument()
  })
})

// ── Multilingual chat ────────────────────────────────────────────────────────

describe('ChatInterface — multilingual chat', () => {
  beforeEach(() => vi.clearAllMocks())

  it('sends the selected chat language with typed questions', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Respuesta en español',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      language: 'es',
      tokens_used: 100,
    })

    await renderChat()
    fireEvent.change(screen.getByRole('combobox', { name: /chat language/i }), {
      target: { value: 'es' },
    })
    await submitQuery('¿Cuál es la política?')

    await waitFor(() => expect(queryApi.ask).toHaveBeenCalledOnce())
    expect(vi.mocked(queryApi.ask).mock.calls[0][0]).toMatchObject({
      language: 'es',
      question: '¿Cuál es la política?',
    })
  })

  it('includes language metadata in transcript export', async () => {
    let exportedBlob: Blob | null = null
    vi.mocked(URL.createObjectURL).mockImplementation((blob) => {
      exportedBlob = blob as Blob
      return 'blob:multilingual-transcript'
    })
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Réponse en français',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      language: 'fr',
      tokens_used: 100,
    })

    await renderChat()
    fireEvent.change(screen.getByRole('combobox', { name: /chat language/i }), {
      target: { value: 'fr' },
    })
    await submitQuery('Quelle est la politique?')
    fireEvent.click(await screen.findByRole('button', { name: /export transcript/i }))

    await waitFor(() => expect(exportedBlob).not.toBeNull())
    const text = await readBlobText(exportedBlob!)
    expect(text).toContain('[language: French]')
    expect(text).toContain('Quelle est la politique?')
  })
})

// ── Validation badge copy ─────────────────────────────────────────────────────

describe('ChatInterface — validation badge copy', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows "Verified" badge for VALID response', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'An answer',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
    })

    await renderChat()
    await submitQuery('A question')

    await waitFor(() => expect(screen.getByText('Verified')).toBeInTheDocument())
    expect(screen.queryByText('VALID')).toBeNull()
  })

  it('shows "Unverified" badge for NEEDS_REVISION response', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'An uncertain answer',
      sources: ['doc.txt'],
      validation: 'NEEDS_REVISION',
      mode: 'agentic',
      tokens_used: 120,
    })

    await renderChat()
    await submitQuery('A question')

    await waitFor(() => expect(screen.getByText('Unverified')).toBeInTheDocument())
    expect(screen.queryByText('NEEDS_REVISION')).toBeNull()
  })

  it('shows validation badge even when there are no sources', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Answer with no sources',
      sources: [],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 80,
    })

    await renderChat()
    await submitQuery('Another question')

    await waitFor(() => expect(screen.getByText('Verified')).toBeInTheDocument())
    expect(screen.queryByText('Sources:')).toBeNull()
  })
})

// ── Latency and retry display ─────────────────────────────────────────────────

describe('ChatInterface — latency and retry display', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows latency in seconds when latency_ms is provided', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'An answer',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
      latency_ms: 2100,
    })

    await renderChat()
    await submitQuery('Show me latency')

    await waitFor(() => expect(screen.getByText('2.1s')).toBeInTheDocument())
  })

  it('shows "revised N×" hint when retry_count > 1', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'A revised answer',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 150,
      retry_count: 2,
    })

    await renderChat()
    await submitQuery('Show me retries')

    await waitFor(() => expect(screen.getByText('revised 1×')).toBeInTheDocument())
  })

  it('does not show retry hint when retry_count is 1', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'First-pass answer',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
      retry_count: 1,
    })

    await renderChat()
    await submitQuery('No retries here')

    await waitFor(() => expect(screen.getByText('Verified')).toBeInTheDocument())
    expect(screen.queryByText(/revised/)).toBeNull()
  })
})

// ── Agent trace accordion ─────────────────────────────────────────────────────

describe('ChatInterface — agent trace accordion', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows and hides trace panel when toggle is clicked', async () => {
    const { queryApi } = await import('@/services/api')
    const trace = makeTrace()
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Agentic answer',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 300,
      trace,
    })

    await renderChat()
    await submitQuery('Tell me something')

    const toggleBtn = await waitFor(() => screen.getByText('Agent trace'))

    expect(screen.queryByText('refined test query')).toBeNull()

    fireEvent.click(toggleBtn)
    await waitFor(() =>
      expect(screen.getByText('refined test query')).toBeInTheDocument()
    )

    fireEvent.click(toggleBtn)
    await waitFor(() =>
      expect(screen.queryByText('refined test query')).toBeNull()
    )
  })

  it('does not show trace toggle in simple mode', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Simple answer',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'simple',
      tokens_used: 50,
      trace: null,
    })

    await renderChat()
    fireEvent.click(screen.getByRole('button', { name: /⚡ Simple/i }))
    await submitQuery('Simple question')

    await waitFor(() => expect(screen.getByText('⚡ Simple RAG')).toBeInTheDocument())
    expect(screen.queryByText('Agent trace')).toBeNull()
  })

  it('does not show trace toggle when trace is null in agentic mode', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Agentic answer without trace',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 200,
      trace: null,
    })

    await renderChat()
    await submitQuery('No trace here')

    await waitFor(() => expect(screen.getByText('Verified')).toBeInTheDocument())
    expect(screen.queryByText('Agent trace')).toBeNull()
  })

  it('renders trace row details correctly when expanded', async () => {
    const { queryApi } = await import('@/services/api')
    const trace = makeTrace({ chunks_found: 1, retries: 2 })
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Answer with trace details',
      sources: ['report.pdf'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 400,
      trace,
    })

    await renderChat()
    await submitQuery('Details please')

    const toggleBtn = await waitFor(() => screen.getByText('Agent trace'))
    fireEvent.click(toggleBtn)

    await waitFor(() =>
      expect(screen.getByText(/1 chunk from: report\.pdf/)).toBeInTheDocument()
    )
    expect(screen.getByText(/answered · 2 revisions/)).toBeInTheDocument()
    expect(screen.getByText('Answer is grounded in the provided context.')).toBeInTheDocument()
  })
})

// ── Copy button ───────────────────────────────────────────────────────────────

describe('ChatInterface — copy button', () => {
  beforeEach(() => vi.clearAllMocks())

  it('calls clipboard.writeText with message content when copy button is clicked', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText },
      writable: true,
      configurable: true,
    })

    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Copy this response text',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
    })

    await renderChat()
    await submitQuery('A question')

    const copyBtn = await waitFor(() =>
      screen.getByRole('button', { name: /copy response/i })
    )
    fireEvent.click(copyBtn)

    expect(writeText).toHaveBeenCalledWith('Copy this response text')
  })
})

// ── Export button ─────────────────────────────────────────────────────────────

describe('ChatInterface — export button', () => {
  beforeEach(() => vi.clearAllMocks())

  it('export button is enabled when messages exist', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Some answer',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
    })

    await renderChat()
    await submitQuery('A question')

    await waitFor(() =>
      expect(screen.getByTestId('export-btn')).toBeInTheDocument()
    )
    expect(screen.getByRole('button', { name: /export transcript/i })).not.toBeDisabled()
  })

  it('export button remains visible but disabled when no messages exist', async () => {
    await renderChat()
    expect(screen.getByRole('button', { name: /export transcript/i })).toBeDisabled()
  })

  it('redacts sensitive values from transcript export', async () => {
    let exportedBlob: Blob | null = null
    vi.mocked(URL.createObjectURL).mockImplementation((blob) => {
      exportedBlob = blob as Blob
      return 'blob:redacted-transcript'
    })
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Contact jane@example.com or call 416-555-0199.',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
    })

    await renderChat()
    await submitQuery('Use sk-proj-' + 'a'.repeat(30))
    fireEvent.click(await screen.findByRole('button', { name: /export transcript/i }))

    await waitFor(() => expect(exportedBlob).not.toBeNull())
    const text = await readBlobText(exportedBlob!)
    expect(text).toContain('[REDACTED_API_KEY]')
    expect(text).toContain('[REDACTED_EMAIL]')
    expect(text).toContain('[REDACTED_PHONE]')
    expect(text).not.toContain('jane@example.com')
    expect(text).not.toContain('416-555-0199')
  })

  it('uses backend-redacted transcript export when the service is available', async () => {
    let exportedBlob: Blob | null = null
    vi.mocked(URL.createObjectURL).mockImplementation((blob) => {
      exportedBlob = blob as Blob
      return 'blob:backend-redacted-transcript'
    })
    const { queryApi, voiceApi } = await import('@/services/api')
    vi.mocked(voiceApi.redactTranscript).mockResolvedValue({
      transcript: 'User: [BACKEND_REDACTED]\n\nAssistant: Safe response',
      redacted: true,
    })
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Safe response',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
    })

    await renderChat()
    await submitQuery('My email is jane@example.com')
    fireEvent.click(await screen.findByRole('button', { name: /export transcript/i }))

    await waitFor(() => expect(voiceApi.redactTranscript).toHaveBeenCalledOnce())
    await waitFor(() => expect(exportedBlob).not.toBeNull())
    const payload = vi.mocked(voiceApi.redactTranscript).mock.calls[0][0]
    expect(payload.language).toBe('en')
    expect(payload.messages?.[0]).toMatchObject({
      role: 'user',
      content: 'My email is jane@example.com',
      origin: 'typed',
    })
    const text = await readBlobText(exportedBlob!)
    expect(text).toBe('User: [BACKEND_REDACTED]\n\nAssistant: Safe response')
  })
})

// ── Voice chat ───────────────────────────────────────────────────────────────

describe('ChatInterface — voice chat', () => {
  class MockSpeechRecognition {
    static transcript = 'What does the document say about customer retention?'
    static instances: MockSpeechRecognition[] = []
    continuous = false
    interimResults = false
    lang = ''
    onstart: (() => void) | null = null
    onresult: ((event: { results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null = null
    onerror: ((event: { error: string }) => void) | null = null
    onend: (() => void) | null = null
    constructor() {
      MockSpeechRecognition.instances.push(this)
    }
    start = vi.fn(() => {
      this.onstart?.()
      this.onresult?.({
        results: [
          { isFinal: true, 0: { transcript: MockSpeechRecognition.transcript } },
        ],
      })
      this.onend?.()
    })
    stop = vi.fn(() => this.onend?.())
    abort = vi.fn()
  }

  beforeEach(() => {
    vi.clearAllMocks()
    MockSpeechRecognition.transcript = 'What does the document say about customer retention?'
    MockSpeechRecognition.instances = []
    Object.defineProperty(window, 'SpeechRecognition', {
      value: MockSpeechRecognition,
      configurable: true,
    })
    Object.defineProperty(window, 'speechSynthesis', {
      value: { speak: vi.fn((utterance) => utterance.onend?.()), cancel: vi.fn() },
      configurable: true,
    })
    Object.defineProperty(window, 'SpeechSynthesisUtterance', {
      value: vi.fn(function SpeechSynthesisUtterance(this: { text: string }, text: string) {
        this.text = text
      }),
      configurable: true,
    })
  })

  it('captures a voice transcript and submits it through normal chat', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Retention improved.',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
    })

    await renderChat()
    await waitFor(() => expect(screen.getByRole('button', { name: /start voice input/i })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: /start voice input/i }))

    expect(await screen.findByDisplayValue(/customer retention/i)).toBeInTheDocument()
    expect(screen.getByText(/voice transcript ready/i)).toBeInTheDocument()
    fireEvent.submit(screen.getByTestId('query-input').closest('form')!)

    await waitFor(() => expect(queryApi.ask).toHaveBeenCalledOnce())
    expect(vi.mocked(queryApi.ask).mock.calls[0][0].question).toMatch(/customer retention/i)
  })

  it('configures speech recognition and playback with the selected language', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Respuesta en español.',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      language: 'es',
      tokens_used: 100,
    })
    await renderChat()
    fireEvent.change(screen.getByRole('combobox', { name: /chat language/i }), {
      target: { value: 'es' },
    })
    await waitFor(() => expect(screen.getByRole('button', { name: /start voice input/i })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: /start voice input/i }))
    await act(async () => {
      fireEvent.submit(screen.getByTestId('query-input').closest('form')!)
      await new Promise(r => setTimeout(r, 0))
    })
    const listen = await screen.findByRole('button', { name: /listen to response/i })
    fireEvent.click(listen)

    expect(MockSpeechRecognition.instances[0].lang).toBe('es-ES')
    const utterance = vi.mocked(window.SpeechSynthesisUtterance).mock.instances[0] as unknown as { lang: string }
    expect(utterance.lang).toBe('es-ES')
  })

  it('offers audio export for voice-only chat and sends structured messages for backend redaction', async () => {
    const { queryApi, voiceApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Email jane@example.com for details.',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
    })
    vi.mocked(voiceApi.exportAudio).mockResolvedValue(new Blob(['mp3'], { type: 'audio/mpeg' }))
    MockSpeechRecognition.transcript = 'My email is jane@example.com and my key is sk-proj-' + 'b'.repeat(30)

    await renderChat()
    await waitFor(() => expect(screen.getByRole('button', { name: /start voice input/i })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: /start voice input/i }))
    await act(async () => {
      fireEvent.submit(screen.getByTestId('query-input').closest('form')!)
      await new Promise(r => setTimeout(r, 0))
    })

    const exportAudio = await screen.findByRole('button', { name: /export audio/i })
    fireEvent.click(exportAudio)
    await waitFor(() => expect(voiceApi.exportAudio).toHaveBeenCalledOnce())
    const payload = vi.mocked(voiceApi.exportAudio).mock.calls[0][0]
    expect(payload.language).toBe('en')
    expect(payload.messages?.[0]).toMatchObject({
      role: 'user',
      content: expect.stringContaining('jane@example.com'),
      origin: 'voice',
    })
    expect(payload.messages?.[0].content).toContain('sk-proj-')
    expect(payload.messages?.[1]).toMatchObject({
      role: 'assistant',
      content: 'Email jane@example.com for details.',
      origin: 'typed',
    })
  })

  it('opens settings when OpenAI key is missing before audio export', async () => {
    const { queryApi, settingsApi, voiceApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Retention improved.',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
    })
    vi.mocked(settingsApi.get)
      .mockResolvedValueOnce({
        api_key_source: 'runtime',
        vector_store_type: 'chroma',
        pinecone_api_key_source: 'not_configured',
      } as never)
      .mockResolvedValueOnce({
        api_key_source: 'not_configured',
        vector_store_type: 'chroma',
        pinecone_api_key_source: 'not_configured',
      } as never)
    const onOpenSettings = vi.fn()

    await renderChat(['doc.txt'], { onOpenSettings })
    await waitFor(() => expect(screen.getByRole('button', { name: /start voice input/i })).not.toBeDisabled())
    fireEvent.click(screen.getByRole('button', { name: /start voice input/i }))
    await act(async () => {
      fireEvent.submit(screen.getByTestId('query-input').closest('form')!)
      await new Promise(r => setTimeout(r, 0))
    })

    const exportAudio = await screen.findByRole('button', { name: /export audio/i })
    fireEvent.click(exportAudio)
    await waitFor(() =>
      expect(onOpenSettings).toHaveBeenCalledWith(expect.stringMatching(/OpenAI API key is required before exporting audio/)),
    )
    expect(screen.getByText(/OpenAI API key is required before exporting audio/)).toBeInTheDocument()
    expect(voiceApi.exportAudio).not.toHaveBeenCalled()
  })

  it('plays assistant responses with redacted speech text', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'The contact is jane@example.com.',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
    })

    await renderChat()
    await submitQuery('Who is the contact?')

    const listen = await screen.findByRole('button', { name: /listen to response/i })
    fireEvent.click(listen)

    expect(window.SpeechSynthesisUtterance).toHaveBeenCalledWith('The contact is [REDACTED_EMAIL].')
    expect(window.speechSynthesis.speak).toHaveBeenCalled()
  })

  it('redacts generated answer secrets before browser playback', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Email jane@example.com with Bearer ' + 'a'.repeat(32) + ' and card 4111 1111 1111 1111.',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
    })

    await renderChat()
    await submitQuery('Read this safely')

    const listen = await screen.findByRole('button', { name: /listen to response/i })
    fireEvent.click(listen)

    const utteranceCalls = vi.mocked(window.SpeechSynthesisUtterance).mock.calls
    const spokenText = utteranceCalls[utteranceCalls.length - 1]?.[0] as string
    expect(spokenText).toContain('[REDACTED_EMAIL]')
    expect(spokenText).toContain('Bearer [REDACTED_TOKEN]')
    expect(spokenText).toContain('[REDACTED_PAYMENT_CARD]')
    expect(spokenText).not.toContain('jane@example.com')
    expect(spokenText).not.toContain('4111 1111 1111 1111')
    expect(spokenText).not.toContain('a'.repeat(32))
  })
})

// ── Guardrail flag badge ──────────────────────────────────────────────────────

describe('ChatInterface — guardrail flag badge', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows output-flagged badge when output_flagged is true', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Flagged response',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
      output_flagged: true,
    })

    await renderChat()
    await submitQuery('A question')

    await waitFor(() =>
      expect(screen.getByTestId('output-flagged-badge')).toBeInTheDocument()
    )
    expect(screen.getByText(/reviewed by content policy/i)).toBeInTheDocument()
  })

  it('does not show output-flagged badge when output_flagged is false', async () => {
    const { queryApi } = await import('@/services/api')
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Normal response',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 100,
      output_flagged: false,
    })

    await renderChat()
    await submitQuery('A question')

    await waitFor(() => expect(screen.getByText('Verified')).toBeInTheDocument())
    expect(screen.queryByTestId('output-flagged-badge')).toBeNull()
  })
})

// ── HyDE trace row ────────────────────────────────────────────────────────────

describe('ChatInterface — HyDE trace rows', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows HyDE and Variants rows in expanded trace panel', async () => {
    const { queryApi } = await import('@/services/api')
    const trace = makeTrace({
      hypothetical_answer: 'test hypothesis',
      query_variants: ['alt 1', 'alt 2'],
    })
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Agentic answer',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 300,
      trace,
    })

    await renderChat()
    await submitQuery('Tell me something')

    const toggleBtn = await waitFor(() => screen.getByText('Agent trace'))
    fireEvent.click(toggleBtn)

    await waitFor(() =>
      expect(screen.getByText('test hypothesis')).toBeInTheDocument()
    )
    expect(screen.getByText('alt 1 · alt 2')).toBeInTheDocument()
  })

  it('does not show HyDE row when hypothetical_answer is empty', async () => {
    const { queryApi } = await import('@/services/api')
    const trace = makeTrace({ hypothetical_answer: '', query_variants: [] })
    vi.mocked(queryApi.ask).mockResolvedValue({
      answer: 'Agentic answer',
      sources: ['doc.txt'],
      validation: 'VALID',
      mode: 'agentic',
      tokens_used: 300,
      trace,
    })

    await renderChat()
    await submitQuery('Tell me something')

    const toggleBtn = await waitFor(() => screen.getByText('Agent trace'))
    fireEvent.click(toggleBtn)

    await waitFor(() =>
      expect(screen.getByText('refined test query')).toBeInTheDocument()
    )
    expect(screen.queryByText('HyDE')).toBeNull()
    expect(screen.queryByText('Variants')).toBeNull()
  })
})

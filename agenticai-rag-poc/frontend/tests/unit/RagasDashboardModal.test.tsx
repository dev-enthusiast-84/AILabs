import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import RagasDashboardModal from '@/components/RagasDashboardModal'
import { useAuthStore } from '@/store/authStore'
import type { SettingsResponse, RagasScores } from '@/types'

// ── Mock @/services/api ───────────────────────────────────────────────────────
vi.mock('@/services/api', () => ({
  settingsApi: {
    get: vi.fn(),
    getRagasScores: vi.fn(),
    triggerRagas: vi.fn(),
  },
  extractErrorMessage: vi.fn((e: unknown) => {
    if (e instanceof Error) return e.message
    return String(e)
  }),
}))

// ── Mock axios ────────────────────────────────────────────────────────────────
vi.mock('axios', async () => {
  const actual = await vi.importActual<typeof import('axios')>('axios')
  return {
    ...actual,
    default: {
      ...actual.default,
      isAxiosError: vi.fn((err: unknown) => {
        return typeof err === 'object' && err !== null && '__isAxiosError' in err
      }),
    },
    isAxiosError: vi.fn((err: unknown) => {
      return typeof err === 'object' && err !== null && '__isAxiosError' in err
    }),
  }
})

// ── Mock react-hot-toast ──────────────────────────────────────────────────────
vi.mock('react-hot-toast', () => ({
  default: {
    error: vi.fn(),
    success: vi.fn(),
    __esModule: true,
  },
}))

import { settingsApi } from '@/services/api'
import toast from 'react-hot-toast'

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeSettings(overrides: Partial<SettingsResponse> = {}): SettingsResponse {
  return {
    model: 'gpt-4o-mini',
    embedding_model: 'text-embedding-3-small',
    api_key_masked: 'sk-****1234',
    api_key_source: 'environment',
    allowed_models: ['gpt-4o-mini'],
    allowed_embedding_models: ['text-embedding-3-small'],
    planner_model: 'gpt-4o-mini',
    generator_model: 'gpt-4o-mini',
    validator_model: 'gpt-4o-mini',
    retriever_k: 5,
    similarity_score_threshold: 0.7,
    retriever_use_mmr: false,
    retriever_fetch_k: 20,
    max_context_chunks: 10,
    max_completion_tokens: 1024,
    token_budget_warning_threshold: 0.8,
    langchain_tracing_v2: false,
    langchain_api_key_masked: '',
    langchain_project: '',
    vector_store_type: 'chroma',
    file_store_type: 'local',
    pinecone_api_key_masked: '',
    pinecone_api_key_source: 'not_configured',
    pinecone_index_name: '',
    pinecone_namespace: '',
    pinecone_cloud: '',
    pinecone_region: '',
    blob_read_write_token_masked: '',
    blob_read_write_token_source: 'not_configured',
    retriever_hybrid_bm25: false,
    relevance_grader_enabled: false,
    ragas_evaluation_enabled: false,
    reranker_type: 'none',
    allowed_reranker_types: ['none'],
    reranker_judge_model: 'gpt-4o-mini',
    allowed_judge_models: ['gpt-4o-mini'],
    chunker_type: 'recursive',
    chunk_size: 500,
    chunk_overlap: 50,
    allowed_chunker_types: ['recursive', 'semantic'],
    ...overrides,
  }
}

function makeScores(overrides: Partial<RagasScores> = {}): RagasScores {
  return {
    faithfulness: 0.85,
    answer_relevancy: 0.9,
    context_precision: 0.75,
    context_recall: 0.8,
    evaluated_at: '2024-01-15T12:00:00Z',
    model: 'gpt-4o-mini',
    num_samples: 10,
    has_results: true,
    ...overrides,
  }
}

function makeAxiosError(status: number) {
  return {
    __isAxiosError: true,
    response: { status },
    isAxiosError: true,
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('RagasDashboardModal', () => {
  const onClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({ isGuest: false, token: 'tok', username: 'admin', guestUploadedDocs: [], guestSettingsUsed: false })
  })

  it('renders nothing when open is false', () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings())
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())
    const { container } = render(<RagasDashboardModal open={false} onClose={onClose} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows loading state while promises are pending', async () => {
    let resolveSettings!: (v: SettingsResponse) => void
    let resolveScores!: (v: RagasScores | null) => void

    vi.mocked(settingsApi.get).mockReturnValue(new Promise((res) => { resolveSettings = res }))
    vi.mocked(settingsApi.getRagasScores).mockReturnValue(new Promise((res) => { resolveScores = res }))

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    expect(screen.getByText('Loading')).toBeTruthy()

    // Resolve inside act() so that the state updates from load()'s
    // Promise.all continuation (setSettings, setScores, setLoading) are
    // properly tracked and don't produce "not wrapped in act()" warnings.
    await act(async () => {
      resolveSettings(makeSettings())
      resolveScores(null)
    })
  })

  it('shows empty state when scores has has_results: false', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings({ ragas_evaluation_enabled: false }))
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue({ has_results: false } as RagasScores)

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => expect(screen.getByTestId('ragas-status-empty')).toBeTruthy())
    // Context-aware: auto-eval is off
    expect(screen.getByText(/Auto-evaluation is off/)).toBeTruthy()
  })

  it('shows empty state with "runs automatically" text when ragas_evaluation_enabled is true', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings({ ragas_evaluation_enabled: true }))
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue({ has_results: false } as RagasScores)

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => expect(screen.getByTestId('ragas-status-empty')).toBeTruthy())
    expect(screen.getByText(/Auto-evaluation samples/)).toBeTruthy()
  })

  it('shows 4 metric tiles when scores has valid data', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings())
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => expect(screen.getByText('Faithfulness')).toBeTruthy())
    expect(screen.getByText('Relevancy')).toBeTruthy()
    expect(screen.getByText('Precision')).toBeTruthy()
    expect(screen.getByText('Recall')).toBeTruthy()
  })

  it('metric tiles show correct percentage values', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings())
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores({
      faithfulness: 0.85,
      answer_relevancy: 0.9,
      context_precision: 0.75,
      context_recall: 0.8,
    }))

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => expect(screen.getByText('85%')).toBeTruthy())
    expect(screen.getByText('90%')).toBeTruthy()
    expect(screen.getByText('75%')).toBeTruthy()
    expect(screen.getByText('80%')).toBeTruthy()
  })

  it('ragas-auto-eval-badge shows "Auto ON" when ragas_evaluation_enabled is true', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings({ ragas_evaluation_enabled: true }))
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => expect(screen.getByTestId('ragas-auto-eval-badge')).toBeTruthy())
    expect(screen.getByTestId('ragas-auto-eval-badge').textContent).toBe('Auto ON')
  })

  it('ragas-auto-eval-badge shows "Auto OFF" when ragas_evaluation_enabled is false', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings({ ragas_evaluation_enabled: false }))
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => expect(screen.getByTestId('ragas-auto-eval-badge')).toBeTruthy())
    expect(screen.getByTestId('ragas-auto-eval-badge').textContent).toBe('Auto OFF')
  })

  it('run button calls settingsApi.triggerRagas', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings())
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())
    vi.mocked(settingsApi.triggerRagas).mockResolvedValue({ status: 'started', message: 'ok' })

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => expect(screen.getByTestId('ragas-dashboard-run-btn')).toBeTruthy())
    // Wrap in async act so that setRunning(false)/setPolling(true) microtasks
    // from runEvaluation's continuation are flushed before assertions.
    await act(async () => {
      fireEvent.click(screen.getByTestId('ragas-dashboard-run-btn'))
    })
    await waitFor(() => expect(settingsApi.triggerRagas).toHaveBeenCalledTimes(1))
  })

  it('shows rate-limit toast on 429 error from triggerRagas', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings())
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())
    vi.mocked(settingsApi.triggerRagas).mockRejectedValue(makeAxiosError(429))

    // Override isAxiosError to correctly recognize our mock error
    const axiosModule = await import('axios')
    vi.mocked(axiosModule.default.isAxiosError).mockImplementation((err: unknown) => {
      return typeof err === 'object' && err !== null && '__isAxiosError' in err
    })

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => screen.getByTestId('ragas-dashboard-run-btn'))
    await act(async () => {
      fireEvent.click(screen.getByTestId('ragas-dashboard-run-btn'))
    })
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Evaluation is already running. Please wait.'))
  })

  it('shows "upload documents" toast on 422 error from triggerRagas', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings())
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())
    vi.mocked(settingsApi.triggerRagas).mockRejectedValue(makeAxiosError(422))

    const axiosModule = await import('axios')
    vi.mocked(axiosModule.default.isAxiosError).mockImplementation((err: unknown) => {
      return typeof err === 'object' && err !== null && '__isAxiosError' in err
    })

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => screen.getByTestId('ragas-dashboard-run-btn'))
    await act(async () => {
      fireEvent.click(screen.getByTestId('ragas-dashboard-run-btn'))
    })
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('Upload documents first before running evaluation.'),
    )
  })

  it('refresh button calls settingsApi.getRagasScores again', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings())
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => expect(screen.getByTestId('ragas-dashboard-refresh-btn')).toBeTruthy())
    const callsBefore = vi.mocked(settingsApi.getRagasScores).mock.calls.length
    // Wrap in async act so that setSettings/setScores/setLoading microtasks
    // from load()'s continuation are flushed and don't leak into the next test.
    await act(async () => {
      fireEvent.click(screen.getByTestId('ragas-dashboard-refresh-btn'))
    })
    await waitFor(() =>
      expect(vi.mocked(settingsApi.getRagasScores).mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('Escape key calls onClose', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings())
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => screen.getByRole('dialog'))
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('does not fetch when open transitions from true to false', async () => {
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings())
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())

    const { rerender } = render(<RagasDashboardModal open={true} onClose={onClose} />)
    await waitFor(() => expect(settingsApi.get).toHaveBeenCalledTimes(1))

    rerender(<RagasDashboardModal open={false} onClose={onClose} />)
    expect(settingsApi.get).toHaveBeenCalledTimes(1)
  })

  it('run button is disabled and guest info is shown for guest users', async () => {
    useAuthStore.setState({ isGuest: true, token: 'gtok', username: 'guest', guestUploadedDocs: [], guestSettingsUsed: false })
    vi.mocked(settingsApi.get).mockResolvedValue(makeSettings())
    vi.mocked(settingsApi.getRagasScores).mockResolvedValue(makeScores())

    render(<RagasDashboardModal open={true} onClose={onClose} />)

    await waitFor(() => screen.getByTestId('ragas-dashboard-run-btn'))
    expect(screen.getByTestId('ragas-dashboard-run-btn')).toBeDisabled()
    expect(screen.getByTestId('ragas-guest-info')).toBeTruthy()
    expect(screen.getByTestId('ragas-guest-info').textContent).toMatch(/Admin access required/)
  })
})

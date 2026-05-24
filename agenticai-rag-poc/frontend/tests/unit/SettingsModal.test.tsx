import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import SettingsModal from '@/components/SettingsModal'
import { useAuthStore } from '@/store/authStore'

// vi.mock is hoisted to the top of the file by Vitest's transform, so any
// variables declared in module scope are not yet initialized when the factory
// runs.  Use vi.hoisted() to declare the shared fixture before the hoist point.
const mockSettings = vi.hoisted(() => ({
  // Section 1
  model: 'gpt-4o-mini',
  embedding_model: 'text-embedding-3-small',
  api_key_masked: 'sk-****...abcd',
  api_key_source: 'environment' as const,
  allowed_models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo'],
  allowed_embedding_models: ['text-embedding-3-small', 'text-embedding-3-large', 'text-embedding-ada-002'],
  // Section 2
  planner_model: '',
  generator_model: '',
  validator_model: '',
  // Section 3
  retriever_k: 4,
  similarity_score_threshold: 0.0,
  retriever_use_mmr: false,
  retriever_fetch_k: 20,
  max_context_chunks: 4,
  // Section 4
  max_completion_tokens: 1024,
  token_budget_warning_threshold: 800,
  // Section 5
  langchain_tracing_v2: false,
  langchain_api_key_masked: '',
  langchain_project: 'agenticai-rag-poc',
  // Section 6
  vector_store_type: 'chroma' as const,
  file_store_type: 'local',
  pinecone_api_key_masked: '',
  pinecone_api_key_source: 'not_configured' as const,
  pinecone_index_name: 'agenticai-rag-poc-documents',
  pinecone_namespace: 'agenticai-rag-poc',
  pinecone_cloud: 'aws',
  pinecone_region: 'us-east-1',
  blob_read_write_token_masked: '',
  blob_read_write_token_source: 'not_configured' as const,
  guest_settings_locked: false,
  guest_settings_recoverable: false,
  guest_settings_reason: 'available',
  // Section 7 — Pipeline feature flags (admin only)
  retriever_hybrid_bm25: true,
  relevance_grader_enabled: false,
  ragas_evaluation_enabled: false,
  reranker_type: 'none',
  allowed_reranker_types: ['cross-encoder', 'none'],
  reranker_judge_model: 'gpt-4o-mini',
  allowed_judge_models: ['gpt-4o-mini'],
  chunker_type: 'recursive',
  chunk_size: 800,
  chunk_overlap: 100,
  allowed_chunker_types: ['recursive', 'semantic'],
}))

vi.mock('@/services/api', () => ({
  settingsApi: {
    get: vi.fn().mockResolvedValue(mockSettings),
    update: vi.fn().mockResolvedValue({ ...mockSettings, api_key_source: 'runtime' }),
    getRagasScores: vi.fn().mockResolvedValue(null),
    triggerRagas: vi.fn().mockResolvedValue({ status: 'started', message: 'Ragas evaluation running in background' }),
  },
  extractErrorMessage: (e: unknown) => String(e),
}))

const renderModal = (open = true, isGuest = false, prerequisiteNotice: string | null = null) =>
  render(
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <SettingsModal
        open={open}
        onClose={vi.fn()}
        isGuest={isGuest}
        prerequisiteNotice={prerequisiteNotice}
      />
    </BrowserRouter>,
  )

describe('SettingsModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthStore.setState({
      token: null,
      username: null,
      isGuest: false,
      guestUploadedDocs: [],
      guestSettingsUsed: false,
    })
  })

  it('does not render when closed', () => {
    renderModal(false)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('renders model selector and api key input when open', async () => {
    renderModal()
    await waitFor(() => expect(screen.getByTestId('model-select')).toBeInTheDocument())
    expect(screen.getByTestId('api-key-input')).toBeInTheDocument()
  })

  it('displays an operation-specific prerequisite notice without hiding fields', async () => {
    renderModal(true, false, 'OpenAI API key is required before asking questions.')
    await waitFor(() => expect(screen.getByText('Settings required before continuing')).toBeInTheDocument())
    expect(screen.getByText('OpenAI API key is required before asking questions.')).toBeInTheDocument()
    expect(screen.getByTestId('model-select')).toBeInTheDocument()
    expect(screen.getByTestId('api-key-input')).toBeInTheDocument()
  })

  it('api key field is password type by default', async () => {
    renderModal()
    await waitFor(() => screen.getByTestId('api-key-input'))
    expect(screen.getByTestId('api-key-input')).toHaveAttribute('type', 'password')
  })

  it('show/hide toggle changes input type', async () => {
    renderModal()
    await waitFor(() => screen.getByTestId('api-key-input'))
    fireEvent.click(screen.getByLabelText('Show API key'))
    expect(screen.getByTestId('api-key-input')).toHaveAttribute('type', 'text')
    fireEvent.click(screen.getByLabelText('Hide API key'))
    expect(screen.getByTestId('api-key-input')).toHaveAttribute('type', 'password')
  })

  it('shows validation error for invalid api key format', async () => {
    renderModal()
    await waitFor(() => screen.getByTestId('api-key-input'))
    fireEvent.change(screen.getByTestId('api-key-input'), { target: { value: 'not-a-key' } })
    fireEvent.click(screen.getByTestId('settings-save-btn'))
    await waitFor(() =>
      expect(screen.getByText(/Invalid format/i)).toBeInTheDocument()
    )
  })

  it('calls settingsApi.update with valid data', async () => {
    const { settingsApi } = await import('@/services/api')
    renderModal()
    await waitFor(() => screen.getByTestId('api-key-input'))
    const validKey = 'sk-' + 'a'.repeat(48)
    fireEvent.change(screen.getByTestId('api-key-input'), { target: { value: validKey } })
    fireEvent.click(screen.getByTestId('settings-save-btn'))
    await waitFor(() =>
      expect(settingsApi.update).toHaveBeenCalledWith(
        expect.objectContaining({ api_key: validKey }),
      )
    )
  })

  it('current masked key is displayed', async () => {
    renderModal()
    await waitFor(() => screen.getByText(/sk-\*\*\*\*\.\.\.abcd/))
  })

  // ── New section visibility tests ────────────────────────────────────────────

  it('test_admin_sees_all_five_sections', async () => {
    renderModal(true, false) // isGuest = false → admin
    await waitFor(() => screen.getByTestId('model-select'))
    expect(screen.getByText('Advanced model settings')).toBeInTheDocument()
    expect(screen.getByText('Retrieval settings')).toBeInTheDocument()
    expect(screen.getByText('Generation limits')).toBeInTheDocument()
    expect(screen.getByText('Observability (LangSmith)')).toBeInTheDocument()
    expect(screen.getByText('Pipeline settings')).toBeInTheDocument()
    expect(screen.getByText('Storage settings')).toBeInTheDocument()
  })

  it('test_guest_sees_model_and_pinecone_settings_only', async () => {
    renderModal(true, true) // isGuest = true
    await waitFor(() => screen.getByTestId('model-select'))
    expect(screen.queryByText('Advanced model settings')).toBeNull()
    expect(screen.queryByText('Retrieval settings')).toBeNull()
    expect(screen.queryByText('Generation limits')).toBeNull()
    expect(screen.queryByText('Observability (LangSmith)')).toBeNull()
    expect(screen.getByText('Storage settings')).toBeInTheDocument()
  })

  it('shows blob token input when file store uses blob', async () => {
    const { settingsApi } = await import('@/services/api')
    vi.mocked(settingsApi.get).mockResolvedValueOnce({
      ...mockSettings,
      file_store_type: 'blob',
    })
    renderModal(true, false)
    await waitFor(() => screen.getByText('Storage settings'))
    expect(screen.getByTestId('blob-token-input')).toBeInTheDocument()
  })

  it('saves blob token when blob storage is enabled', async () => {
    const { settingsApi } = await import('@/services/api')
    vi.mocked(settingsApi.get).mockResolvedValueOnce({
      ...mockSettings,
      file_store_type: 'blob',
    })
    renderModal(true, false)
    await waitFor(() => screen.getByTestId('blob-token-input'))
    fireEvent.change(screen.getByTestId('blob-token-input'), {
      target: { value: 'vercel_blob_rw_test_token' },
    })
    fireEvent.click(screen.getByTestId('settings-save-btn'))
    await waitFor(() =>
      expect(settingsApi.update).toHaveBeenCalledWith(
        expect.objectContaining({ blob_read_write_token: 'vercel_blob_rw_test_token' }),
      )
    )
  })

  it('guest can provide blob token when blob storage is enabled', async () => {
    const { settingsApi } = await import('@/services/api')
    vi.mocked(settingsApi.get).mockResolvedValueOnce({
      ...mockSettings,
      file_store_type: 'blob',
    })
    renderModal(true, true)
    await waitFor(() => screen.getByTestId('blob-token-input'))
    expect(screen.getByTestId('blob-token-input')).not.toBeDisabled()
    fireEvent.change(screen.getByTestId('blob-token-input'), {
      target: { value: 'vercel_blob_rw_guest_token' },
    })
    fireEvent.click(screen.getByTestId('settings-save-btn'))
    await waitFor(() =>
      expect(settingsApi.update).toHaveBeenCalledWith(
        expect.objectContaining({ blob_read_write_token: 'vercel_blob_rw_guest_token' }),
      )
    )
  })

  it('guest can re-enter settings when local lock is stale after restart', async () => {
    const { settingsApi } = await import('@/services/api')
    useAuthStore.setState({
      token: 'guest-token',
      username: 'guest',
      isGuest: true,
      guestUploadedDocs: [],
      guestSettingsUsed: true,
    })
    vi.mocked(settingsApi.get).mockResolvedValueOnce({
      ...mockSettings,
      guest_settings_locked: false,
      guest_settings_recoverable: true,
      guest_settings_reason: 'settings_lost_after_restart',
    })

    renderModal(true, true)

    await waitFor(() => expect(screen.getByText('Guest settings need to be re-entered:')).toBeInTheDocument())
    expect(screen.getByTestId('api-key-input')).not.toBeDisabled()
    expect(screen.getByTestId('settings-save-btn')).not.toBeDisabled()
  })

  it('test_retrieval_section_expands_on_click', async () => {
    renderModal(true, false)
    await waitFor(() => screen.getByText('Retrieval settings'))
    // Sliders should not be visible before expanding
    expect(screen.queryByText('Top-k results')).toBeNull()
    fireEvent.click(screen.getByText('Retrieval settings'))
    await waitFor(() => expect(screen.getByText('Top-k results')).toBeInTheDocument())
    expect(screen.getByText('Min similarity score')).toBeInTheDocument()
    expect(screen.getByText('Max context chunks')).toBeInTheDocument()
  })

  it('test_langsmith_key_input_hidden_when_tracing_off', async () => {
    renderModal(true, false)
    await waitFor(() => screen.getByText('Observability (LangSmith)'))
    // Open the section
    fireEvent.click(screen.getByText('Observability (LangSmith)'))
    // Tracing is off by default, so key input should NOT be present
    await waitFor(() => screen.getByTestId('tracing-toggle'))
    expect(screen.queryByTestId('langsmith-key-input')).toBeNull()
  })

  it('test_langsmith_key_input_visible_when_tracing_on', async () => {
    renderModal(true, false)
    await waitFor(() => screen.getByText('Observability (LangSmith)'))
    fireEvent.click(screen.getByText('Observability (LangSmith)'))
    await waitFor(() => screen.getByTestId('tracing-toggle'))
    // Enable tracing
    fireEvent.click(screen.getByTestId('tracing-toggle'))
    await waitFor(() =>
      expect(screen.getByTestId('langsmith-key-input')).toBeInTheDocument()
    )
  })

  it('test_mmr_fetch_k_hidden_when_mmr_off', async () => {
    renderModal(true, false)
    await waitFor(() => screen.getByText('Retrieval settings'))
    fireEvent.click(screen.getByText('Retrieval settings'))
    await waitFor(() => screen.getByText('Use MMR diversity'))
    // MMR is off by default
    expect(screen.queryByText('MMR candidate pool')).toBeNull()
  })

  it('test_mmr_fetch_k_visible_when_mmr_on', async () => {
    renderModal(true, false)
    await waitFor(() => screen.getByText('Retrieval settings'))
    fireEvent.click(screen.getByText('Retrieval settings'))
    await waitFor(() => screen.getByText('Use MMR diversity'))
    // Toggle MMR on
    const mmrSwitch = screen.getByRole('switch', { name: '' })
    fireEvent.click(mmrSwitch)
    await waitFor(() =>
      expect(screen.getByText('MMR candidate pool')).toBeInTheDocument()
    )
  })

  it('test_save_includes_retrieval_fields_when_changed', async () => {
    const { settingsApi } = await import('@/services/api')
    renderModal(true, false)
    await waitFor(() => screen.getByText('Retrieval settings'))

    // Open retrieval section
    fireEvent.click(screen.getByText('Retrieval settings'))
    await waitFor(() => screen.getByText('Top-k results'))

    // Change the top-k slider from default 4 to 8
    const sliders = screen.getAllByRole('slider')
    const topKSlider = sliders[0] // first slider is Top-k results
    fireEvent.change(topKSlider, { target: { value: '8' } })

    // Save
    fireEvent.click(screen.getByTestId('settings-save-btn'))
    await waitFor(() =>
      expect(settingsApi.update).toHaveBeenCalledWith(
        expect.objectContaining({ retriever_k: 8 }),
      )
    )
  })

  it('shows no-evaluation message when getRagasScores returns null', async () => {
    renderModal(true, false) // admin
    await waitFor(() => screen.getByText('Ragas Evaluation'))
    fireEvent.click(screen.getByText('Ragas Evaluation'))
    await waitFor(() =>
      expect(screen.getByText('No evaluation has been run yet.')).toBeInTheDocument()
    )
  })

  it('shows metric tiles when Ragas scores exist', async () => {
    const { settingsApi } = await import('@/services/api')
    vi.mocked(settingsApi.getRagasScores).mockResolvedValueOnce({
      faithfulness: 0.82,
      answer_relevancy: 0.91,
      context_precision: 0.75,
      context_recall: 0.68,
      model: 'gpt-4o',
      num_samples: 3,
      evaluated_at: '2026-05-17T10:00:00Z',
    })
    renderModal(true, false)
    await waitFor(() => screen.getByText('Ragas Evaluation'))
    fireEvent.click(screen.getByText('Ragas Evaluation'))
    await waitFor(() => expect(screen.getByText('82%')).toBeInTheDocument())
    expect(screen.getByText('91%')).toBeInTheDocument()
    expect(screen.getByText('75%')).toBeInTheDocument()
    expect(screen.getByText('68%')).toBeInTheDocument()
    expect(screen.getByText(/gpt-4o · 3 samples/)).toBeInTheDocument()
  })

  it('Ragas section not visible for guest', async () => {
    renderModal(true, true) // isGuest = true
    await waitFor(() => screen.getByTestId('model-select'))
    expect(screen.queryByText('Ragas Evaluation')).not.toBeInTheDocument()
  })

  // ── Ragas trigger button tests ─────────────────────────────────────────────

  it('test_ragas_trigger_button_visible_for_admin', async () => {
    renderModal(true, false) // admin
    await waitFor(() => screen.getByText('Ragas Evaluation'))
    fireEvent.click(screen.getByText('Ragas Evaluation'))
    await waitFor(() => expect(screen.getByTestId('ragas-trigger-btn')).toBeInTheDocument())
  })

  it('test_ragas_trigger_button_hidden_for_guest', async () => {
    renderModal(true, true) // guest
    await waitFor(() => screen.getByTestId('model-select'))
    expect(screen.queryByTestId('ragas-trigger-btn')).not.toBeInTheDocument()
  })

  it('test_ragas_trigger_shows_loading_state', async () => {
    const { settingsApi } = await import('@/services/api')
    // Make triggerRagas hang indefinitely so we can observe the loading state
    vi.mocked(settingsApi.triggerRagas).mockImplementation(
      () => new Promise(() => {}),
    )
    renderModal(true, false)
    await waitFor(() => screen.getByText('Ragas Evaluation'))
    fireEvent.click(screen.getByText('Ragas Evaluation'))
    await waitFor(() => screen.getByTestId('ragas-trigger-btn'))
    fireEvent.click(screen.getByTestId('ragas-trigger-btn'))
    await waitFor(() =>
      expect(screen.getByTestId('ragas-trigger-btn')).toBeDisabled()
    )
    expect(screen.getByText('Running…')).toBeInTheDocument()
  })

  it('test_ragas_trigger_shows_success_toast', async () => {
    const { settingsApi } = await import('@/services/api')
    vi.mocked(settingsApi.triggerRagas).mockResolvedValueOnce({
      status: 'started',
      message: 'Ragas evaluation running in background',
    })
    renderModal(true, false)
    await waitFor(() => screen.getByText('Ragas Evaluation'))
    fireEvent.click(screen.getByText('Ragas Evaluation'))
    await waitFor(() => screen.getByTestId('ragas-trigger-btn'))
    fireEvent.click(screen.getByTestId('ragas-trigger-btn'))
    await waitFor(() =>
      expect(settingsApi.triggerRagas).toHaveBeenCalledTimes(1)
    )
  })

  it('shows a prerequisite message when Ragas evaluation is run without an OpenAI key', async () => {
    const { settingsApi } = await import('@/services/api')
    vi.mocked(settingsApi.get).mockResolvedValueOnce({
      ...mockSettings,
      api_key_masked: '',
      api_key_source: 'not_configured',
    })
    renderModal(true, false)
    await waitFor(() => screen.getByText('Ragas Evaluation'))
    fireEvent.click(screen.getByText('Ragas Evaluation'))
    await waitFor(() => screen.getByTestId('ragas-trigger-btn'))
    fireEvent.click(screen.getByTestId('ragas-trigger-btn'))
    expect(screen.getByText('OpenAI API key is required before running Ragas evaluation.')).toBeInTheDocument()
    expect(settingsApi.triggerRagas).not.toHaveBeenCalled()
  })

  // ── Pipeline section tests ──────────────────────────────────────────────────

  it('test_pipeline_section_visible_for_admin', async () => {
    renderModal(true, false) // admin
    await waitFor(() => screen.getByTestId('model-select'))
    expect(screen.getByText('Pipeline settings')).toBeInTheDocument()
  })

  it('test_pipeline_section_not_visible_for_guest', async () => {
    renderModal(true, true) // guest
    await waitFor(() => screen.getByTestId('model-select'))
    expect(screen.queryByText('Pipeline settings')).not.toBeInTheDocument()
  })

  it('test_pipeline_hybrid_bm25_toggle_present_when_expanded', async () => {
    renderModal(true, false) // admin
    await waitFor(() => screen.getByText('Pipeline settings'))
    fireEvent.click(screen.getByText('Pipeline settings'))
    await waitFor(() =>
      expect(screen.getByTestId('hybrid-bm25-toggle')).toBeInTheDocument()
    )
    expect(screen.getByText('Hybrid BM25 retrieval')).toBeInTheDocument()
  })

  it('test_pipeline_chunker_type_select_shows_current_value', async () => {
    renderModal(true, false) // admin
    await waitFor(() => screen.getByText('Pipeline settings'))
    fireEvent.click(screen.getByText('Pipeline settings'))
    await waitFor(() =>
      expect(screen.getByTestId('chunker-type-select')).toBeInTheDocument()
    )
    expect(screen.getByTestId('chunker-type-select')).toHaveValue('recursive')
  })

  it('test_pipeline_toggling_hybrid_bm25_off_includes_field_in_save_payload', async () => {
    const { settingsApi } = await import('@/services/api')
    renderModal(true, false) // admin; mockSettings has retriever_hybrid_bm25: true
    await waitFor(() => screen.getByText('Pipeline settings'))
    fireEvent.click(screen.getByText('Pipeline settings'))
    await waitFor(() => screen.getByTestId('hybrid-bm25-toggle'))
    // Toggle it off (default is true → clicking sets it to false)
    fireEvent.click(screen.getByTestId('hybrid-bm25-toggle'))
    fireEvent.click(screen.getByTestId('settings-save-btn'))
    await waitFor(() =>
      expect(settingsApi.update).toHaveBeenCalledWith(
        expect.objectContaining({ retriever_hybrid_bm25: false }),
      )
    )
  })

  it('test_pipeline_relevance_grader_toggle_present_when_expanded', async () => {
    renderModal(true, false) // admin
    await waitFor(() => screen.getByText('Pipeline settings'))
    fireEvent.click(screen.getByText('Pipeline settings'))
    await waitFor(() =>
      expect(screen.getByTestId('relevance-grader-toggle')).toBeInTheDocument()
    )
    expect(screen.getByText('Relevance grader')).toBeInTheDocument()
  })

  it('test_pipeline_reranker_type_select_present_when_expanded', async () => {
    renderModal(true, false) // admin
    await waitFor(() => screen.getByText('Pipeline settings'))
    fireEvent.click(screen.getByText('Pipeline settings'))
    await waitFor(() =>
      expect(screen.getByTestId('reranker-type-select')).toBeInTheDocument()
    )
    expect(screen.getByTestId('reranker-type-select')).toHaveValue('none')
  })
})

// ── Client-side validation unit tests (pure functions) ────────────────────────

const API_KEY_RE = /^sk(-proj)?-[A-Za-z0-9_\-]{20,}$/

describe('API key format validation', () => {
  it('accepts standard sk- key', () => {
    expect(API_KEY_RE.test('sk-' + 'a'.repeat(40))).toBe(true)
  })

  it('accepts project sk-proj- key', () => {
    expect(API_KEY_RE.test('sk-proj-' + 'B'.repeat(30))).toBe(true)
  })

  it('rejects wrong prefix', () => {
    expect(API_KEY_RE.test('pk-' + 'a'.repeat(40))).toBe(false)
  })

  it('rejects too-short key', () => {
    expect(API_KEY_RE.test('sk-short')).toBe(false)
  })

  it('rejects XSS payload', () => {
    expect(API_KEY_RE.test('<script>alert(1)</script>')).toBe(false)
  })

  it('rejects SQL injection attempt', () => {
    expect(API_KEY_RE.test("'; DROP TABLE users; --")).toBe(false)
  })
})

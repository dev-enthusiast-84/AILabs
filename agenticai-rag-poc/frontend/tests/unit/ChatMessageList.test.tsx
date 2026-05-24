import { render, screen, fireEvent } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { createRef } from 'react'
import { ChatMessageList } from '@/components/chat/ChatMessageList'
import type { ChatMessage, AgentTrace, Citation } from '@/types'

// Clipboard mock
const writeTextMock = vi.fn().mockResolvedValue(undefined)
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: writeTextMock },
  writable: true,
  configurable: true,
})

function makeBottomRef() {
  return createRef<HTMLDivElement>()
}

const baseTrace: AgentTrace = {
  original_question: 'What is the policy?',
  refined_query: 'Explain policy details',
  chunks_found: 3,
  validation_reason: 'Answer is accurate',
  retries: 0,
  chunks_after_grading: 3,
  chunks_after_rerank: 3,
  hyde_tokens: 100,
  hyde_latency_ms: 50,
  grader_tokens: 50,
  grader_latency_ms: 0,
  reranker_latency_ms: 0,
  planner_tokens: 80,
  generator_tokens: 200,
  validator_tokens: 60,
  planner_latency_ms: 100,
  generator_latency_ms: 300,
  validator_latency_ms: 80,
  planner_model: 'gpt-4o-mini',
  generator_model: 'gpt-4o-mini',
  validator_model: 'gpt-4o-mini',
  hypothetical_answer: 'The policy states that...',
  query_variants: ['What does the policy say?', 'Describe the policy'],
}

function makeUserMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'msg-user-1',
    role: 'user',
    content: 'Hello, how are you?',
    timestamp: new Date(),
    ...overrides,
  }
}

function makeAssistantMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: 'msg-assistant-1',
    role: 'assistant',
    content: 'I am doing well, thank you.',
    timestamp: new Date(),
    mode: 'agentic',
    ...overrides,
  }
}

interface RenderProps {
  messages?: ChatMessage[]
  expandedTraces?: Set<string>
  copiedId?: string | null
  playingMessageId?: string | null
  loading?: boolean
  documentsCount?: number
}

function renderList(props: RenderProps = {}) {
  const {
    messages = [],
    expandedTraces = new Set<string>(),
    copiedId = null,
    playingMessageId = null,
    loading = false,
    documentsCount = 1,
  } = props

  const onCopyResponse = vi.fn()
  const onOpenSource = vi.fn()
  const onSuggestionClick = vi.fn()
  const onTogglePlayback = vi.fn()
  const onToggleTrace = vi.fn()

  const result = render(
    <ChatMessageList
      bottomRef={makeBottomRef()}
      copiedId={copiedId}
      documentsCount={documentsCount}
      expandedTraces={expandedTraces}
      loading={loading}
      messages={messages}
      playingMessageId={playingMessageId}
      suggestions={[]}
      suggestionsLoading={false}
      onCopyResponse={onCopyResponse}
      onOpenSource={onOpenSource}
      onSuggestionClick={onSuggestionClick}
      onTogglePlayback={onTogglePlayback}
      onToggleTrace={onToggleTrace}
    />,
  )

  return { ...result, onCopyResponse, onOpenSource, onToggleTrace, onTogglePlayback }
}

describe('ChatMessageList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders empty state when messages array is empty and documentsCount is 0', () => {
    renderList({ messages: [], documentsCount: 0 })
    expect(screen.getByText(/No documents indexed yet/)).toBeTruthy()
  })

  it('renders empty state with suggestions prompt when documents exist but messages are empty', () => {
    renderList({ messages: [], documentsCount: 2 })
    expect(screen.getByText(/Ask a question about your documents/)).toBeTruthy()
  })

  it('renders a user message bubble with correct content', () => {
    const msg = makeUserMessage({ content: 'What is the capital of France?' })
    renderList({ messages: [msg] })
    expect(screen.getByText('What is the capital of France?')).toBeTruthy()
  })

  it('renders an assistant message with answer text', () => {
    const msg = makeAssistantMessage({ content: 'The capital of France is Paris.' })
    renderList({ messages: [msg] })
    expect(screen.getByText('The capital of France is Paris.')).toBeTruthy()
  })

  it('shows badge-valid class element with "Verified" when validation === "VALID"', () => {
    const msg = makeAssistantMessage({ validation: 'VALID', mode: 'agentic' })
    renderList({ messages: [msg] })
    const badge = document.querySelector('.badge-valid')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toContain('Verified')
  })

  it('shows badge-revision class element with "Unverified" when validation === "NEEDS_REVISION"', () => {
    const msg = makeAssistantMessage({ validation: 'NEEDS_REVISION', mode: 'agentic' })
    renderList({ messages: [msg] })
    const badge = document.querySelector('.badge-revision')
    expect(badge).not.toBeNull()
    expect(badge!.textContent).toContain('Unverified')
  })

  it('shows source chips when sources is non-empty', () => {
    const msg = makeAssistantMessage({ sources: ['report.pdf', 'notes.txt'] })
    renderList({ messages: [msg] })
    expect(screen.getByText('report.pdf')).toBeTruthy()
    expect(screen.getByText('notes.txt')).toBeTruthy()
  })

  it('clicking a source chip calls onOpenSource with the source filename', () => {
    const msg = makeAssistantMessage({ sources: ['report.pdf'] })
    const { onOpenSource } = renderList({ messages: [msg] })
    fireEvent.click(screen.getByText('report.pdf'))
    expect(onOpenSource).toHaveBeenCalledWith('report.pdf')
  })

  it('clicking copy button calls onCopyResponse with the message', () => {
    const msg = makeAssistantMessage({ id: 'msg-copy-1', content: 'Copy me' })
    const { onCopyResponse } = renderList({ messages: [msg] })
    fireEvent.click(screen.getByTestId('copy-btn-msg-copy-1'))
    expect(onCopyResponse).toHaveBeenCalledWith(expect.objectContaining({ id: 'msg-copy-1' }))
  })

  it('shows tokens_used count when present', () => {
    const msg = makeAssistantMessage({ tokens_used: 1234 })
    renderList({ messages: [msg] })
    expect(screen.getByText('1,234 tokens')).toBeTruthy()
  })

  it('shows output_flagged warning when output_flagged === true', () => {
    const msg = makeAssistantMessage({ output_flagged: true })
    renderList({ messages: [msg] })
    expect(screen.getByTestId('output-flagged-badge')).toBeTruthy()
    expect(screen.getByText(/Reviewed by content policy/)).toBeTruthy()
  })

  it('does not show output_flagged warning when output_flagged is false', () => {
    const msg = makeAssistantMessage({ output_flagged: false })
    renderList({ messages: [msg] })
    expect(screen.queryByTestId('output-flagged-badge')).toBeNull()
  })

  it('AgentTrace accordion shows trace panel when expandedTraces contains the message ID', () => {
    const msg = makeAssistantMessage({ id: 'msg-trace-1', mode: 'agentic', trace: baseTrace })
    renderList({ messages: [msg], expandedTraces: new Set(['msg-trace-1']) })
    expect(screen.getByTestId('trace-panel-msg-trace-1')).toBeTruthy()
    // Verify planner refined query appears in the trace panel
    expect(screen.getByText('Explain policy details')).toBeTruthy()
  })

  it('AgentTrace section is hidden when message ID is not in expandedTraces', () => {
    const msg = makeAssistantMessage({ id: 'msg-trace-2', mode: 'agentic', trace: baseTrace })
    renderList({ messages: [msg], expandedTraces: new Set<string>() })
    expect(screen.queryByTestId('trace-panel-msg-trace-2')).toBeNull()
  })

  it('clicking trace toggle calls onToggleTrace with the message id', () => {
    const msg = makeAssistantMessage({ id: 'msg-trace-toggle', mode: 'agentic', trace: baseTrace })
    const { onToggleTrace } = renderList({ messages: [msg] })
    fireEvent.click(screen.getByTestId('trace-toggle-msg-trace-toggle'))
    expect(onToggleTrace).toHaveBeenCalledWith('msg-trace-toggle')
  })

  it('does not show trace toggle for simple mode messages', () => {
    const msg = makeAssistantMessage({ id: 'msg-simple', mode: 'simple' })
    renderList({ messages: [msg] })
    expect(screen.queryByTestId('trace-toggle-msg-simple')).toBeNull()
  })

  it('renders citation cards when citations are present', () => {
    const citations: Citation[] = [
      { source: 'test.txt', chunk_index: 0, text: 'Sample text from the document.' },
    ]
    const msg = makeAssistantMessage({ citations })
    renderList({ messages: [msg] })
    const cards = document.querySelectorAll('[data-testid="citation-card"]')
    expect(cards.length).toBe(1)
    expect(screen.getByText('test.txt')).toBeTruthy()
    expect(screen.getByText('chunk 1')).toBeTruthy()
  })

  it('clicking the source name in a citation card calls onOpenSource', () => {
    const citations: Citation[] = [
      { source: 'report.pdf', chunk_index: 2, text: 'Short text.' },
    ]
    const msg = makeAssistantMessage({ citations })
    const { onOpenSource } = renderList({ messages: [msg] })
    fireEvent.click(screen.getByText('report.pdf'))
    expect(onOpenSource).toHaveBeenCalledWith('report.pdf')
  })

  it('shows expand button and toggles full text for long citations', () => {
    const longText = 'A'.repeat(150)
    const citations: Citation[] = [
      { source: 'doc.pdf', chunk_index: 0, text: longText },
    ]
    const msg = makeAssistantMessage({ citations })
    renderList({ messages: [msg] })
    // expand button should be present (▼)
    const expandBtn = screen.getByLabelText('Expand citation')
    expect(expandBtn).toBeTruthy()
    // preview text should be truncated (120 chars + ellipsis)
    expect(screen.queryByText(longText)).toBeNull()
    // click expand
    fireEvent.click(expandBtn)
    // full text should now be visible
    expect(screen.getByText(longText)).toBeTruthy()
    // collapse button should appear
    expect(screen.getByLabelText('Collapse citation')).toBeTruthy()
  })

  it('falls back to source chips when citations is empty but sources is present', () => {
    const msg = makeAssistantMessage({ sources: ['fallback.pdf'], citations: [] })
    renderList({ messages: [msg] })
    expect(screen.getByText('fallback.pdf')).toBeTruthy()
    const cards = document.querySelectorAll('[data-testid="citation-card"]')
    expect(cards.length).toBe(0)
  })

  it('renders multiple citation cards for multiple citations', () => {
    const citations: Citation[] = [
      { source: 'doc1.pdf', chunk_index: 0, text: 'First chunk text.' },
      { source: 'doc2.pdf', chunk_index: 1, text: 'Second chunk text.' },
    ]
    const msg = makeAssistantMessage({ citations })
    renderList({ messages: [msg] })
    const cards = document.querySelectorAll('[data-testid="citation-card"]')
    expect(cards.length).toBe(2)
    expect(screen.getByText('doc1.pdf')).toBeTruthy()
    expect(screen.getByText('doc2.pdf')).toBeTruthy()
  })
})

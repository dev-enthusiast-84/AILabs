import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import GuardrailsModal from '@/components/GuardrailsModal'
import type { GuardrailRule, GuardrailCheckResponse } from '@/types'

// ── fixtures ──────────────────────────────────────────────────────────────────

const ruleA: GuardrailRule = {
  id: 'rule-1',
  name: 'Block profanity',
  description: 'Blocks offensive words',
  type: 'word',
  target: 'input',
  action: 'block',
  severity: 'high',
  enabled: true,
  builtin: true,
  words: ['bad', 'awful'],
  keywords: [],
  pattern: '',
  replacement: '',
}

const ruleB: GuardrailRule = {
  id: 'rule-2',
  name: 'Flag sensitive topics',
  description: 'Flags violence keywords',
  type: 'topic',
  target: 'both',
  action: 'flag',
  severity: 'medium',
  enabled: false,
  builtin: false,
  words: [],
  keywords: ['violence', 'harm'],
  pattern: '',
  replacement: '',
}

const mockCreated: GuardrailRule = {
  id: 'rule-3',
  name: 'New regex rule',
  description: '',
  type: 'regex',
  target: 'output',
  action: 'redact',
  severity: 'low',
  enabled: true,
  builtin: false,
  words: [],
  keywords: [],
  pattern: '\\d{4}',
  replacement: '[NUM]',
}

const mockCheckAllowed: GuardrailCheckResponse = {
  allowed: true,
  modified_text: '',
  flagged: false,
  violations: [],
}

const mockCheckBlocked: GuardrailCheckResponse = {
  allowed: false,
  modified_text: 'The [REDACTED] is hidden',
  flagged: true,
  violations: [
    { rule_id: 'rule-1', rule_name: 'Block profanity', action: 'block', severity: 'high' },
  ],
}

// ── mocks ─────────────────────────────────────────────────────────────────────

// Use vi.hoisted so the mock factory can reference these before hoisting.
const mockGuardrailsApi = vi.hoisted(() => ({
  list: vi.fn(),
  get: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
  check: vi.fn(),
}))

vi.mock('@/services/api', () => ({
  guardrailsApi: mockGuardrailsApi,
  extractErrorMessage: (e: unknown) => String(e),
}))

vi.mock('react-hot-toast', () => ({
  default: { error: vi.fn(), success: vi.fn() },
}))

// ── helpers ───────────────────────────────────────────────────────────────────

const renderModal = (props: { open?: boolean; isGuest?: boolean } = {}) =>
  render(
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <GuardrailsModal open={props.open ?? true} onClose={vi.fn()} isGuest={props.isGuest} />
    </BrowserRouter>,
  )

beforeEach(() => {
  vi.clearAllMocks()
  mockGuardrailsApi.list.mockResolvedValue([ruleA, ruleB])
})

// ── tests ─────────────────────────────────────────────────────────────────────

describe('GuardrailsModal — not rendered when closed', () => {
  it('returns null when open=false', () => {
    renderModal({ open: false })
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})

describe('GuardrailsModal — Rules tab', () => {
  it('renders rule names after loading', async () => {
    renderModal()
    await waitFor(() => {
      expect(screen.getByText('Block profanity')).toBeInTheDocument()
      expect(screen.getByText('Flag sensitive topics')).toBeInTheDocument()
    })
  })

  it('calls guardrailsApi.list on open', async () => {
    renderModal()
    await waitFor(() => expect(mockGuardrailsApi.list).toHaveBeenCalledOnce())
  })

  it('shows loading indicator initially', () => {
    // list never resolves during this synchronous check
    mockGuardrailsApi.list.mockReturnValue(new Promise(() => {}))
    renderModal()
    expect(screen.getByTestId('rules-loading')).toBeInTheDocument()
  })

  it('toggle calls guardrailsApi.update with inverted enabled', async () => {
    mockGuardrailsApi.update.mockResolvedValue({ ...ruleB, enabled: true })
    renderModal()
    await waitFor(() => screen.getByTestId(`toggle-${ruleB.id}`))
    fireEvent.click(screen.getByTestId(`toggle-${ruleB.id}`))
    await waitFor(() =>
      expect(mockGuardrailsApi.update).toHaveBeenCalledWith(ruleB.id, { enabled: true }),
    )
  })

  it('delete button absent for builtin rule', async () => {
    renderModal()
    await waitFor(() => screen.getByText('Block profanity'))
    expect(screen.queryByTestId(`delete-${ruleA.id}`)).toBeNull()
  })

  it('delete button present for non-builtin rule and calls remove', async () => {
    mockGuardrailsApi.remove.mockResolvedValue(undefined)
    renderModal()
    await waitFor(() => screen.getByTestId(`delete-${ruleB.id}`))
    fireEvent.click(screen.getByTestId(`delete-${ruleB.id}`))
    await waitFor(() => expect(mockGuardrailsApi.remove).toHaveBeenCalledWith(ruleB.id))
  })

  it('delete removes rule from list', async () => {
    mockGuardrailsApi.remove.mockResolvedValue(undefined)
    renderModal()
    await waitFor(() => screen.getByText('Flag sensitive topics'))
    fireEvent.click(screen.getByTestId(`delete-${ruleB.id}`))
    await waitFor(() =>
      expect(screen.queryByText('Flag sensitive topics')).toBeNull(),
    )
  })

  it('Add Rule button opens the inline form', async () => {
    renderModal()
    await waitFor(() => screen.getByTestId('add-rule-btn'))
    fireEvent.click(screen.getByTestId('add-rule-btn'))
    expect(screen.getByTestId('add-rule-form')).toBeInTheDocument()
  })

  it('add form submits create API and appends rule to list', async () => {
    mockGuardrailsApi.create.mockResolvedValue(mockCreated)
    renderModal()
    await waitFor(() => screen.getByTestId('add-rule-btn'))
    fireEvent.click(screen.getByTestId('add-rule-btn'))

    fireEvent.change(screen.getByTestId('add-rule-name'), { target: { value: 'New regex rule' } })
    fireEvent.change(screen.getByTestId('add-rule-type'), { target: { value: 'regex' } })
    fireEvent.change(screen.getByTestId('add-rule-pattern'), { target: { value: '\\d{4}' } })
    fireEvent.change(screen.getByTestId('add-rule-replacement'), { target: { value: '[NUM]' } })

    fireEvent.click(screen.getByTestId('add-rule-save'))

    await waitFor(() =>
      expect(mockGuardrailsApi.create).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'New regex rule', type: 'regex' }),
      ),
    )
    await waitFor(() => expect(screen.getByText('New regex rule')).toBeInTheDocument())
  })
})

describe('GuardrailsModal — Test tab', () => {
  it('Test tab is hidden for guests', async () => {
    renderModal({ isGuest: true })
    await waitFor(() => screen.getByTestId('tab-rules'))
    expect(screen.queryByTestId('tab-test')).toBeNull()
  })

  it('Test tab visible for admin', async () => {
    renderModal()
    await waitFor(() => screen.getByTestId('tab-test'))
    expect(screen.getByTestId('tab-test')).toBeInTheDocument()
  })

  it('check call shows Allowed badge', async () => {
    mockGuardrailsApi.check.mockResolvedValue(mockCheckAllowed)
    renderModal()
    await waitFor(() => screen.getByTestId('tab-test'))
    fireEvent.click(screen.getByTestId('tab-test'))

    fireEvent.change(screen.getByTestId('test-text-input'), {
      target: { value: 'This is safe text.' },
    })
    fireEvent.click(screen.getByTestId('run-test-btn'))

    await waitFor(() =>
      expect(mockGuardrailsApi.check).toHaveBeenCalledWith(
        expect.objectContaining({ text: 'This is safe text.' }),
      ),
    )
    await waitFor(() =>
      expect(screen.getByText('Allowed')).toBeInTheDocument(),
    )
  })

  it('check call shows Blocked badge and violation list', async () => {
    mockGuardrailsApi.check.mockResolvedValue(mockCheckBlocked)
    renderModal()
    await waitFor(() => screen.getByTestId('tab-test'))
    fireEvent.click(screen.getByTestId('tab-test'))

    fireEvent.change(screen.getByTestId('test-text-input'), {
      target: { value: 'Some bad text here.' },
    })
    fireEvent.click(screen.getByTestId('run-test-btn'))

    await waitFor(() => expect(screen.getByText('Blocked')).toBeInTheDocument())
    expect(screen.getByText('Flagged')).toBeInTheDocument()
    expect(screen.getByText('Block profanity')).toBeInTheDocument()
  })

  it('shows redacted output when modified_text differs from input', async () => {
    mockGuardrailsApi.check.mockResolvedValue(mockCheckBlocked)
    renderModal()
    await waitFor(() => screen.getByTestId('tab-test'))
    fireEvent.click(screen.getByTestId('tab-test'))

    fireEvent.change(screen.getByTestId('test-text-input'), {
      target: { value: 'Some bad text here.' },
    })
    fireEvent.click(screen.getByTestId('run-test-btn'))

    await waitFor(() =>
      expect(screen.getByText('The [REDACTED] is hidden')).toBeInTheDocument(),
    )
  })
})

describe('GuardrailsModal — Guest mode', () => {
  it('shows read-only notice for guest', async () => {
    renderModal({ isGuest: true })
    await waitFor(() => screen.getByText(/Guest mode — view only/i))
  })

  it('Add Rule button is hidden for guest', async () => {
    renderModal({ isGuest: true })
    await waitFor(() => screen.getByText('Block profanity'))
    expect(screen.queryByTestId('add-rule-btn')).toBeNull()
  })

  it('toggle is disabled for guest', async () => {
    renderModal({ isGuest: true })
    await waitFor(() => screen.getByTestId(`toggle-${ruleA.id}`))
    expect(screen.getByTestId(`toggle-${ruleA.id}`)).toBeDisabled()
  })

  it('delete buttons are hidden for guest', async () => {
    renderModal({ isGuest: true })
    await waitFor(() => screen.getByText('Flag sensitive topics'))
    // Non-builtin rule delete should be absent in guest mode
    expect(screen.queryByTestId(`delete-${ruleB.id}`)).toBeNull()
  })
})

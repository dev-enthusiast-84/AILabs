import { render, screen, fireEvent } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { ChatToolbar } from '@/components/chat/ChatToolbar'
import { CHAT_LANGUAGES } from '@/lib/chatLanguages'
import type { ChatLanguageCode } from '@/lib/chatLanguages'

function renderToolbar(overrides: Partial<Parameters<typeof ChatToolbar>[0]> = {}) {
  const onChangeLanguage = vi.fn()
  const onChangeMode = vi.fn()
  const onExportAudio = vi.fn()
  const onExportTranscript = vi.fn()

  const props = {
    chatLanguage: 'en' as ChatLanguageCode,
    exportingAudio: false,
    exportJobStatus: null,
    messageCount: 5,
    ragMode: 'simple' as const,
    voiceOnlyConversation: false,
    onChangeLanguage,
    onChangeMode,
    onExportAudio,
    onExportTranscript,
    ...overrides,
  }

  const result = render(<ChatToolbar {...props} />)

  return { ...result, onChangeLanguage, onChangeMode, onExportAudio, onExportTranscript }
}

describe('ChatToolbar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders Simple and Agentic mode buttons', () => {
    renderToolbar()
    expect(screen.getByText(/Simple/)).toBeTruthy()
    expect(screen.getByText(/Agentic/)).toBeTruthy()
  })

  it('Simple button has aria-pressed=true when ragMode is simple', () => {
    renderToolbar({ ragMode: 'simple' })
    const simpleBtn = screen.getByRole('button', { name: /Simple/i })
    expect(simpleBtn.getAttribute('aria-pressed')).toBe('true')
    const agenticBtn = screen.getByRole('button', { name: /Agentic/i })
    expect(agenticBtn.getAttribute('aria-pressed')).toBe('false')
  })

  it('Agentic button has aria-pressed=true when ragMode is agentic', () => {
    renderToolbar({ ragMode: 'agentic' })
    const agenticBtn = screen.getByRole('button', { name: /Agentic/i })
    expect(agenticBtn.getAttribute('aria-pressed')).toBe('true')
    const simpleBtn = screen.getByRole('button', { name: /Simple/i })
    expect(simpleBtn.getAttribute('aria-pressed')).toBe('false')
  })

  it('clicking the inactive Agentic button calls onChangeMode with "agentic"', () => {
    const { onChangeMode } = renderToolbar({ ragMode: 'simple' })
    fireEvent.click(screen.getByRole('button', { name: /Agentic/i }))
    expect(onChangeMode).toHaveBeenCalledWith('agentic')
  })

  it('clicking the inactive Simple button calls onChangeMode with "simple"', () => {
    const { onChangeMode } = renderToolbar({ ragMode: 'agentic' })
    fireEvent.click(screen.getByRole('button', { name: /Simple/i }))
    expect(onChangeMode).toHaveBeenCalledWith('simple')
  })

  it('language selector renders one <option> per entry in CHAT_LANGUAGES', () => {
    renderToolbar()
    const select = screen.getByTestId('chat-language-select')
    const options = select.querySelectorAll('option')
    expect(options.length).toBe(CHAT_LANGUAGES.length)
    CHAT_LANGUAGES.forEach((lang, i) => {
      expect(options[i].value).toBe(lang.code)
      expect(options[i].textContent).toBe(lang.label)
    })
  })

  it('changing language selection calls onChangeLanguage with the new code', () => {
    const { onChangeLanguage } = renderToolbar({ chatLanguage: 'en' })
    const select = screen.getByTestId('chat-language-select')
    fireEvent.change(select, { target: { value: 'es' } })
    expect(onChangeLanguage).toHaveBeenCalledWith('es')
  })

  it('export transcript button calls onExportTranscript when clicked', () => {
    const { onExportTranscript } = renderToolbar({ messageCount: 3 })
    fireEvent.click(screen.getByTestId('export-btn'))
    expect(onExportTranscript).toHaveBeenCalledTimes(1)
  })

  it('export transcript button is disabled when messageCount === 0', () => {
    renderToolbar({ messageCount: 0 })
    const exportBtn = screen.getByTestId('export-btn') as HTMLButtonElement
    expect(exportBtn.disabled).toBe(true)
  })

  it('export transcript button is enabled when messageCount > 0', () => {
    renderToolbar({ messageCount: 5 })
    const exportBtn = screen.getByTestId('export-btn') as HTMLButtonElement
    expect(exportBtn.disabled).toBe(false)
  })

  it('does not render export audio button when voiceOnlyConversation is false', () => {
    renderToolbar({ voiceOnlyConversation: false })
    expect(screen.queryByTestId('export-audio-btn')).toBeNull()
  })

  it('renders export audio button when voiceOnlyConversation is true', () => {
    renderToolbar({ voiceOnlyConversation: true })
    expect(screen.getByTestId('export-audio-btn')).toBeTruthy()
  })

  it('export audio button is disabled while exportingAudio is true', () => {
    renderToolbar({ voiceOnlyConversation: true, exportingAudio: true, messageCount: 3 })
    const audioBtn = screen.getByTestId('export-audio-btn') as HTMLButtonElement
    expect(audioBtn.disabled).toBe(true)
  })

  it('shows "Exporting…" label on audio button while exportingAudio is true', () => {
    renderToolbar({ voiceOnlyConversation: true, exportingAudio: true, messageCount: 3 })
    expect(screen.getByText('Exporting…')).toBeTruthy()
  })

  it('shows export job status "Queued…" when exportJobStatus is queued and exporting', () => {
    renderToolbar({ voiceOnlyConversation: true, exportingAudio: true, exportJobStatus: 'queued' })
    expect(screen.getByTestId('export-job-status').textContent).toBe('Queued…')
  })

  it('shows export job status "Processing…" when exportJobStatus is running and exporting', () => {
    renderToolbar({ voiceOnlyConversation: true, exportingAudio: true, exportJobStatus: 'running' })
    expect(screen.getByTestId('export-job-status').textContent).toBe('Processing…')
  })

  it('shows cancel button while exportingAudio is true when onCancelExport is provided', () => {
    const onCancelExport = vi.fn()
    renderToolbar({ voiceOnlyConversation: true, exportingAudio: true, onCancelExport })
    expect(screen.getByTestId('cancel-export-btn')).toBeTruthy()
  })

  it('clicking cancel export button calls onCancelExport', () => {
    const onCancelExport = vi.fn()
    renderToolbar({ voiceOnlyConversation: true, exportingAudio: true, onCancelExport })
    fireEvent.click(screen.getByTestId('cancel-export-btn'))
    expect(onCancelExport).toHaveBeenCalledTimes(1)
  })
})

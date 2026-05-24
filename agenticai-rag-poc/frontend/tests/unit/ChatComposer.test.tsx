/**
 * Unit tests for ChatComposer — character counter (Fix D7).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ChatComposer } from '@/components/chat/ChatComposer'

const baseProps = {
  documentsCount: 1,
  input: '',
  isRecording: false,
  loading: false,
  voiceDraftReady: false,
  voiceError: null,
  voiceSupported: false,
  onChangeInput: vi.fn(),
  onStartRecording: vi.fn(),
  onStopRecording: vi.fn(),
  onSubmit: vi.fn(),
}

describe('ChatComposer — character counter', () => {
  it('does not render the counter when input is empty', () => {
    render(<ChatComposer {...baseProps} input="" maxQueryLength={100} />)
    expect(screen.queryByTestId('char-counter')).toBeNull()
  })

  it('renders the counter when input has characters', () => {
    render(<ChatComposer {...baseProps} input="hello" maxQueryLength={100} />)
    expect(screen.getByTestId('char-counter')).toBeInTheDocument()
    expect(screen.getByTestId('char-counter').textContent).toBe('5 / 100')
  })

  it('shows default maxQueryLength of 1000 when prop is omitted', () => {
    render(<ChatComposer {...baseProps} input="hi" />)
    expect(screen.getByTestId('char-counter').textContent).toBe('2 / 1000')
  })

  it('applies normal styling below 80% usage', () => {
    render(<ChatComposer {...baseProps} input={'a'.repeat(79)} maxQueryLength={100} />)
    const counter = screen.getByTestId('char-counter')
    expect(counter.className).toContain('text-slate-400')
    expect(counter.className).not.toContain('text-amber-600')
    expect(counter.className).not.toContain('text-rose-600')
  })

  it('applies amber styling above 80% usage', () => {
    render(<ChatComposer {...baseProps} input={'a'.repeat(85)} maxQueryLength={100} />)
    const counter = screen.getByTestId('char-counter')
    expect(counter.className).toContain('text-amber-600')
    expect(counter.className).not.toContain('text-rose-600')
  })

  it('applies red styling above 95% usage', () => {
    render(<ChatComposer {...baseProps} input={'a'.repeat(96)} maxQueryLength={100} />)
    const counter = screen.getByTestId('char-counter')
    expect(counter.className).toContain('text-rose-600')
    expect(counter.className).not.toContain('text-amber-600')
  })

  it('applies red styling exactly at 100% usage', () => {
    render(<ChatComposer {...baseProps} input={'a'.repeat(100)} maxQueryLength={100} />)
    const counter = screen.getByTestId('char-counter')
    expect(counter.className).toContain('text-rose-600')
  })

  it('calls onChangeInput when the user types', () => {
    const onChangeInput = vi.fn()
    render(<ChatComposer {...baseProps} onChangeInput={onChangeInput} />)
    const input = screen.getByTestId('query-input')
    fireEvent.change(input, { target: { value: 'test' } })
    expect(onChangeInput).toHaveBeenCalledWith('test')
  })
})

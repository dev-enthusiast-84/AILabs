import { renderHook } from '@testing-library/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useChatExport } from '@/hooks/useChatExport'
import type { ChatMessage } from '@/types'

// Mock voiceApi
vi.mock('@/services/api', () => ({
  voiceApi: {
    exportAudio: vi.fn(),
    redactTranscript: vi.fn(),
  },
}))

import { voiceApi } from '@/services/api'

function makeMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: '1',
    role: 'user',
    content: 'Hello',
    timestamp: new Date(),
    ...overrides,
  }
}

function languageByCode(code: string) {
  return { code: code as never, label: code, speech: code }
}

describe('useChatExport — exportAudio', () => {
  const mockClick = vi.fn()
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let createElementSpy: ReturnType<typeof vi.spyOn<any, any>>

  beforeEach(() => {
    vi.clearAllMocks()
    mockClick.mockReset()

    // jsdom doesn't implement URL.createObjectURL — assign directly on globalThis
    Object.defineProperty(globalThis.URL, 'createObjectURL', {
      value: vi.fn(() => 'blob:mock'),
      writable: true,
      configurable: true,
    })
    Object.defineProperty(globalThis.URL, 'revokeObjectURL', {
      value: vi.fn(),
      writable: true,
      configurable: true,
    })

    // Stub anchor click
    createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        return { href: '', download: '', click: mockClick } as unknown as HTMLAnchorElement
      }
      // Call original for other tags
      createElementSpy.mockRestore()
      const el = document.createElement(tag)
      createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((t: string) => {
        if (t === 'a') return { href: '', download: '', click: mockClick } as unknown as HTMLAnchorElement
        return document.createElement(t)
      })
      return el
    })
  })

  afterEach(() => {
    createElementSpy.mockRestore()
  })

  it('returns { redacted: false } when voiceApi.exportAudio returns redacted=false', async () => {
    const fakeBlob = new Blob(['audio'], { type: 'audio/mpeg' })
    vi.mocked(voiceApi.exportAudio).mockResolvedValue({ blob: fakeBlob, redacted: false })

    const { result } = renderHook(() => useChatExport(languageByCode))
    const outcome = await result.current.exportAudio([makeMessage()], 'en')

    expect(outcome).toEqual({ redacted: false })
    expect(mockClick).toHaveBeenCalledTimes(1)
  })

  it('returns { redacted: true } when voiceApi.exportAudio returns redacted=true', async () => {
    const fakeBlob = new Blob(['audio'], { type: 'audio/mpeg' })
    vi.mocked(voiceApi.exportAudio).mockResolvedValue({ blob: fakeBlob, redacted: true })

    const { result } = renderHook(() => useChatExport(languageByCode))
    const outcome = await result.current.exportAudio([makeMessage()], 'en')

    expect(outcome).toEqual({ redacted: true })
  })

  it('calls voiceApi.exportAudio with transformed messages', async () => {
    const fakeBlob = new Blob(['audio'], { type: 'audio/mpeg' })
    vi.mocked(voiceApi.exportAudio).mockResolvedValue({ blob: fakeBlob, redacted: false })

    const messages = [makeMessage({ content: 'Hello world', role: 'user' })]
    const { result } = renderHook(() => useChatExport(languageByCode))
    await result.current.exportAudio(messages, 'en')

    expect(voiceApi.exportAudio).toHaveBeenCalledWith(
      { messages: [{ role: 'user', content: 'Hello world', origin: 'typed' }], language: 'en' },
      undefined,
      undefined,
    )
  })

  it('propagates errors from voiceApi.exportAudio', async () => {
    vi.mocked(voiceApi.exportAudio).mockRejectedValue(new Error('Export failed'))

    const { result } = renderHook(() => useChatExport(languageByCode))
    await expect(result.current.exportAudio([makeMessage()], 'en')).rejects.toThrow('Export failed')
  })
})

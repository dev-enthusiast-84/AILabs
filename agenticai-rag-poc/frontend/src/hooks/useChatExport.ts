import { useCallback } from 'react'
import { voiceApi } from '@/services/api'
import type { ChatMessage, ChatVoiceExportMessage } from '@/types'
import type { ChatLanguageCode } from '@/lib/chatLanguages'

export interface ChatExportLanguage {
  code: ChatLanguageCode
  label: string
}

export const EXPORT_REDACTION_UNAVAILABLE = 'EXPORT_REDACTION_UNAVAILABLE'

export function redactSensitiveText(text: string): string {
  return text
    .replace(/-----BEGIN [\s\S]+? PRIVATE KEY-----[\s\S]+?-----END [\s\S]+? PRIVATE KEY-----/g, '[REDACTED_PRIVATE_KEY]')
    .replace(/\bsk(?:-proj)?-[A-Za-z0-9_-]{20,}\b/g, '[REDACTED_API_KEY]')
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]{12,}\b/gi, 'Bearer [REDACTED_TOKEN]')
    .replace(/\b(?:api[_-]?key|access[_-]?token|secret|password|pwd)\s*[:=]\s*["']?[^"'\s,;]{6,}/gi, (match) => {
      const key = match.split(/[:=]/)[0].trim()
      return `${key}: [REDACTED_SECRET]`
    })
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '[REDACTED_EMAIL]')
    .replace(/\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b/g, '[REDACTED_PHONE]')
    .replace(/\b(?:\d[ -]*?){13,19}\b/g, '[REDACTED_PAYMENT_CARD]')
    .replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[REDACTED_GOV_ID]')
}

export function toVoiceExportMessages(messages: ChatMessage[]): ChatVoiceExportMessage[] {
  return messages
    .filter((message) => message.content.trim())
    .map((message) => ({
      role: message.role,
      content: message.content,
      origin: message.input_method === 'voice' ? 'voice' : 'typed',
    }))
}

export function buildLocalExportTranscript(
  messages: ChatMessage[],
  languageByCode: (code: string) => ChatExportLanguage,
): string {
  const lines = messages.map((message) => {
    const role = message.role === 'user' ? 'You' : 'Assistant'
    const origin = message.role === 'user' && message.input_method ? ` (${message.input_method})` : ''
    const language = message.language ? ` [language: ${languageByCode(message.language).label}]` : ''
    const ts = message.timestamp.toLocaleString()
    return `[${ts}] ${role}${origin}${language}:\n${redactSensitiveText(message.content)}`
  })
  return lines.join('\n\n---\n\n')
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function isMissingRedactionEndpoint(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status
  return status === 404 || status === 405
}

function unavailableRedactionError(error: unknown): Error {
  const wrapped = new Error(EXPORT_REDACTION_UNAVAILABLE)
  ;(wrapped as Error & { cause?: unknown }).cause = error
  return wrapped
}

export function useChatExport(languageByCode: (code: string) => ChatExportLanguage) {
  const buildFallbackTranscript = useCallback(
    (messages: ChatMessage[]) => buildLocalExportTranscript(messages, languageByCode),
    [languageByCode],
  )

  const getRedactedTranscript = useCallback(async (messages: ChatMessage[], language: ChatLanguageCode) => {
    try {
      const response = await voiceApi.redactTranscript({
        messages: toVoiceExportMessages(messages),
        language,
      })
      return response.transcript
    } catch (error) {
      if (isMissingRedactionEndpoint(error)) {
        throw unavailableRedactionError(error)
      }
      throw error
    }
  }, [])

  const exportTranscript = useCallback(async (messages: ChatMessage[], language: ChatLanguageCode) => {
    let transcript: string
    try {
      transcript = await getRedactedTranscript(messages, language)
    } catch (error) {
      if ((error as Error).message !== EXPORT_REDACTION_UNAVAILABLE) throw error
      transcript = buildFallbackTranscript(messages)
    }
    downloadBlob(new Blob([transcript], { type: 'text/plain' }), `conversation-${Date.now()}.txt`)
  }, [buildFallbackTranscript, getRedactedTranscript])

  const exportAudio = useCallback(async (messages: ChatMessage[], language: ChatLanguageCode) => {
    const audio = await voiceApi.exportAudio({
      messages: toVoiceExportMessages(messages),
      language,
    })
    downloadBlob(audio, `conversation-audio-${Date.now()}.mp3`)
  }, [])

  return {
    buildFallbackTranscript,
    exportAudio,
    exportTranscript,
    getRedactedTranscript,
  }
}

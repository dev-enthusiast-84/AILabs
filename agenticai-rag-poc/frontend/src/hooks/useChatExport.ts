import { useCallback } from 'react'
import { voiceApi } from '@/services/api'
import type { ChatMessage, ChatVoiceExportMessage } from '@/types'
import type { ChatLanguageCode } from '@/lib/chatLanguages'
import { maskSensitive } from '@/lib/redact'

export interface ChatExportLanguage {
  code: ChatLanguageCode
  label: string
}

export const EXPORT_REDACTION_UNAVAILABLE = 'EXPORT_REDACTION_UNAVAILABLE'

/** Backward-compatible alias — delegates to the canonical maskSensitive() from lib/redact.ts. */
export function redactSensitiveText(text: string): string {
  return maskSensitive(text)
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

  const exportAudio = useCallback(async (
    messages: ChatMessage[],
    language: ChatLanguageCode,
    onStatusChange?: (status: string) => void,
    onJobId?: (jobId: string) => void,
  ): Promise<{ redacted: boolean }> => {
    const result = await voiceApi.exportAudio(
      { messages: toVoiceExportMessages(messages), language },
      onStatusChange,
      onJobId,
    )
    downloadBlob(result.blob, `conversation-audio-${Date.now()}.mp3`)
    return { redacted: result.redacted }
  }, [])

  return {
    buildFallbackTranscript,
    exportAudio,
    exportTranscript,
    getRedactedTranscript,
  }
}

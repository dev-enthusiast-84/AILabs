import { useCallback, useMemo, useState, useRef, useEffect } from 'react'
import toast from 'react-hot-toast'
import { documentsApi, queryApi, settingsApi, extractErrorMessage } from '@/services/api'
import type { ChatMessage } from '@/types'
import DocumentViewerModal from '@/components/DocumentViewerModal'
import { ChatComposer } from '@/components/chat/ChatComposer'
import { ChatMessageList } from '@/components/chat/ChatMessageList'
import { ChatToolbar } from '@/components/chat/ChatToolbar'
import { buildSuggestionsFromContent } from '@/components/chat/suggestions'
import { useToggleSet } from '@/hooks/useToggleSet'
import { redactSensitiveText, useChatExport } from '@/hooks/useChatExport'
import { languageByCode, type ChatLanguageCode } from '@/lib/chatLanguages'

interface Props {
  documents: string[]
  onOpenSettings?: (notice: string) => void
}

type InputMethod = 'text' | 'voice'

interface SpeechRecognitionLike {
  continuous: boolean
  interimResults: boolean
  lang: string
  onstart: (() => void) | null
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

interface SpeechRecognitionEventLike {
  results: ArrayLike<{
    isFinal: boolean
    0: { transcript: string }
  }>
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

type VoiceWindow = Window & {
  SpeechRecognition?: SpeechRecognitionConstructor
  webkitSpeechRecognition?: SpeechRecognitionConstructor
}

export default function ChatInterface({ documents, onOpenSettings }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [viewing, setViewing] = useState<string | null>(null)
  const [ragMode, setRagMode] = useState<'simple' | 'agentic'>('agentic')
  const [chatLanguage, setChatLanguage] = useState<ChatLanguageCode>('en')
  const [expandedTraces, toggleTrace] = useToggleSet()
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const [voiceSupported, setVoiceSupported] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)
  const [voiceDraftReady, setVoiceDraftReady] = useState(false)
  const [playingMessageId, setPlayingMessageId] = useState<string | null>(null)
  const [exportingAudio, setExportingAudio] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null)
  const transcriptRef = useRef('')
  const { exportAudio, exportTranscript } = useChatExport(languageByCode)

  useEffect(() => {
    let cancelled = false

    if (documents.length === 0) {
      setSuggestions([])
      setSuggestionsLoading(false)
      return
    }

    setSuggestionsLoading(true)
    Promise.allSettled(
      documents.slice(0, 3).map((filename) => documentsApi.getContent(filename)),
    )
      .then((results) => {
        if (cancelled) return
        const contents = results
          .filter((result) => result.status === 'fulfilled')
          .map((result) => result.value.content)
        setSuggestions(buildSuggestionsFromContent(contents))
      })
      .catch(() => {
        if (!cancelled) setSuggestions(buildSuggestionsFromContent([]))
      })
      .finally(() => {
        if (!cancelled) setSuggestionsLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [documents])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    const voiceWindow = window as VoiceWindow
    setVoiceSupported(Boolean(voiceWindow.SpeechRecognition || voiceWindow.webkitSpeechRecognition))
    return () => {
      recognitionRef.current?.abort()
      window.speechSynthesis?.cancel()
    }
  }, [])

  const selectedLanguage = languageByCode(chatLanguage)

  const sendMessage = useCallback(async (question: string, inputMethod: InputMethod = 'text') => {
    const trimmed = question.trim()
    if (!trimmed || loading) return

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      input_method: inputMethod,
      language: chatLanguage,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setVoiceDraftReady(false)
    setVoiceError(null)
    setLoading(true)

    try {
      const settings = await settingsApi.get()
      if (settings.api_key_source === 'not_configured') {
        const message = 'OpenAI API key is required before asking questions because answers are generated with the selected LLM model.'
        toast.error(message)
        onOpenSettings?.(message)
        setMessages((prev) => prev.filter((m) => m.id !== userMsg.id))
        return
      }
      if (settings.vector_store_type === 'pinecone' && settings.pinecone_api_key_source === 'not_configured') {
        const message = 'Pinecone API key is required before asking questions because retrieval reads indexed chunks from Pinecone.'
        toast.error(message)
        onOpenSettings?.(message)
        setMessages((prev) => prev.filter((m) => m.id !== userMsg.id))
        return
      }
      if ((settings.vector_store_type === 'blob' || settings.file_store_type === 'blob') && settings.blob_read_write_token_source === 'not_configured') {
        const message = 'Blob read/write token is required before asking questions because this deployment reads stored chunks or files from Blob storage.'
        toast.error(message)
        onOpenSettings?.(message)
        setMessages((prev) => prev.filter((m) => m.id !== userMsg.id))
        return
      }
      const history = messages
        .filter((message) => message.role === 'user' || message.role === 'assistant')
        .slice(-6)
        .map((message) => ({
          role: message.role as 'user' | 'assistant',
          content: message.content.slice(0, 700),
        }))
      const result = await queryApi.ask({ question: trimmed, mode: ragMode, language: chatLanguage, history })
      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: result.answer,
        sources: result.sources,
        validation: result.validation,
        tokens_used: result.tokens_used,
        mode: result.mode,
        language: result.language ?? chatLanguage,
        timestamp: new Date(),
        retry_count: result.retry_count,
        latency_ms: result.latency_ms,
        trace: result.trace,
        output_flagged: result.output_flagged,
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch (err) {
      const message = extractErrorMessage(err)
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: message,
          error: true,
          timestamp: new Date(),
        },
      ])
    } finally {
      setLoading(false)
    }
  }, [chatLanguage, loading, messages, onOpenSettings, ragMode])

  const exportConversation = useCallback(async () => {
    try {
      await exportTranscript(messages, chatLanguage)
    } catch (err) {
      setVoiceError(extractErrorMessage(err))
    }
  }, [chatLanguage, exportTranscript, messages])

  const voiceOnlyConversation = useMemo(() => {
    const userMessages = messages.filter((message) => message.role === 'user')
    return userMessages.length > 0 && userMessages.every((message) => message.input_method === 'voice')
  }, [messages])

  const startRecording = useCallback(() => {
    setVoiceError(null)
    if (loading || documents.length === 0) return
    const voiceWindow = window as VoiceWindow
    const Recognition = voiceWindow.SpeechRecognition || voiceWindow.webkitSpeechRecognition
    if (!Recognition) {
      setVoiceError('Voice input is not supported in this browser. Typed chat is still available.')
      return
    }

    recognitionRef.current?.abort()
    transcriptRef.current = ''
    const recognition = new Recognition()
    recognition.continuous = false
    recognition.interimResults = true
    recognition.lang = selectedLanguage.speech
    recognition.onstart = () => {
      setIsRecording(true)
      setVoiceDraftReady(false)
    }
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? '')
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim()
      transcriptRef.current = transcript
      setInput(transcript)
      setVoiceDraftReady(Boolean(transcript))
    }
    recognition.onerror = (event) => {
      const message = event.error === 'not-allowed'
        ? 'Microphone access was blocked. Allow microphone permission or continue typing.'
        : 'Voice capture failed. Try again or continue typing.'
      setVoiceError(message)
    }
    recognition.onend = () => {
      setIsRecording(false)
      if (!transcriptRef.current.trim()) {
        setVoiceDraftReady(false)
        setVoiceError((current) => current ?? 'No speech was captured. Try again or type your question.')
      }
    }
    recognitionRef.current = recognition
    recognition.start()
  }, [documents.length, loading, selectedLanguage.speech])

  const stopRecording = useCallback(() => {
    recognitionRef.current?.stop()
  }, [])

  const togglePlayback = useCallback((message: ChatMessage) => {
    setVoiceError(null)
    if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
      setVoiceError('Audio playback is not supported in this browser.')
      return
    }
    if (playingMessageId === message.id) {
      window.speechSynthesis.cancel()
      setPlayingMessageId(null)
      return
    }
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(redactSensitiveText(message.content))
    utterance.lang = languageByCode(message.language ?? chatLanguage).speech
    utterance.onend = () => setPlayingMessageId((current) => (current === message.id ? null : current))
    utterance.onerror = () => {
      setPlayingMessageId(null)
      setVoiceError('Audio playback failed. The answer text remains available in chat.')
    }
    setPlayingMessageId(message.id)
    window.speechSynthesis.speak(utterance)
  }, [chatLanguage, playingMessageId])

  const exportAudioConversation = useCallback(async () => {
    setVoiceError(null)
    if (!voiceOnlyConversation) {
      setVoiceError('Audio export is available for voice-only conversations. Transcript export is available for every chat.')
      return
    }
    setExportingAudio(true)
    try {
      const settings = await settingsApi.get()
      if (settings.api_key_source === 'not_configured') {
        const message = 'OpenAI API key is required before exporting audio because the transcript is converted to speech with OpenAI.'
        setVoiceError(message)
        onOpenSettings?.(message)
        return
      }
      await exportAudio(messages, chatLanguage)
    } catch (err) {
      setVoiceError(extractErrorMessage(err))
    } finally {
      setExportingAudio(false)
    }
  }, [chatLanguage, exportAudio, messages, onOpenSettings, voiceOnlyConversation])

  const copyResponse = useCallback((message: ChatMessage) => {
    navigator.clipboard.writeText(message.content)
    setCopiedId(message.id)
    setTimeout(() => setCopiedId((prev) => (prev === message.id ? null : prev)), 2000)
  }, [])

  return (
    <div className="card flex flex-col h-[calc(100vh-220px)] min-h-[520px] sm:h-[600px] p-5">
      <ChatToolbar
        chatLanguage={chatLanguage}
        exportingAudio={exportingAudio}
        messageCount={messages.length}
        ragMode={ragMode}
        voiceOnlyConversation={voiceOnlyConversation}
        onChangeLanguage={setChatLanguage}
        onChangeMode={setRagMode}
        onExportAudio={exportAudioConversation}
        onExportTranscript={exportConversation}
      />

      <ChatMessageList
        bottomRef={bottomRef}
        copiedId={copiedId}
        documentsCount={documents.length}
        expandedTraces={expandedTraces}
        loading={loading}
        messages={messages}
        playingMessageId={playingMessageId}
        suggestions={suggestions}
        suggestionsLoading={suggestionsLoading}
        onCopyResponse={copyResponse}
        onOpenSource={setViewing}
        onSuggestionClick={sendMessage}
        onTogglePlayback={togglePlayback}
        onToggleTrace={toggleTrace}
      />

      <ChatComposer
        documentsCount={documents.length}
        input={input}
        isRecording={isRecording}
        loading={loading}
        voiceDraftReady={voiceDraftReady}
        voiceError={voiceError}
        voiceSupported={voiceSupported}
        onChangeInput={setInput}
        onStartRecording={startRecording}
        onStopRecording={stopRecording}
        onSubmit={sendMessage}
      />

      <DocumentViewerModal filename={viewing} onClose={() => setViewing(null)} />
    </div>
  )
}

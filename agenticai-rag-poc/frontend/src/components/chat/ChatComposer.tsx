import { MicrophoneIcon, PaperAirplaneIcon } from '@heroicons/react/24/outline'

type InputMethod = 'text' | 'voice'

interface ChatComposerProps {
  documentsCount: number
  input: string
  isRecording: boolean
  loading: boolean
  voiceDraftReady: boolean
  voiceError: string | null
  voiceSupported: boolean
  onChangeInput: (value: string) => void
  onStartRecording: () => void
  onStopRecording: () => void
  onSubmit: (question: string, inputMethod: InputMethod) => void
}

export function ChatComposer({
  documentsCount,
  input,
  isRecording,
  loading,
  voiceDraftReady,
  voiceError,
  voiceSupported,
  onChangeInput,
  onStartRecording,
  onStopRecording,
  onSubmit,
}: ChatComposerProps) {
  return (
    <>
      {voiceError && (
        <p className="mb-2 text-xs text-rose-600" role="alert">
          {voiceError}
        </p>
      )}
      {isRecording && (
        <p className="mb-2 text-xs text-sky-700" aria-live="polite">
          Listening…
        </p>
      )}
      {voiceDraftReady && !isRecording && (
        <p className="mb-2 text-xs text-emerald-700" aria-live="polite">
          Voice transcript ready. Review it, edit if needed, then send.
        </p>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault()
          onSubmit(input, voiceDraftReady ? 'voice' : 'text')
        }}
        className="flex gap-2 shrink-0"
      >
        <button
          type="button"
          onClick={isRecording ? onStopRecording : onStartRecording}
          disabled={loading || documentsCount === 0 || (!voiceSupported && !isRecording)}
          className="btn-tool px-3 shrink-0"
          aria-label={isRecording ? 'Stop voice input' : 'Start voice input'}
          aria-pressed={isRecording}
          title={
            voiceSupported
              ? (isRecording ? 'Stop voice input' : 'Start voice input')
              : 'Voice input is not supported in this browser'
          }
          data-testid="voice-input-btn"
        >
          <MicrophoneIcon className={`h-5 w-5 ${isRecording ? 'text-rose-600' : ''}`} />
        </button>
        <input
          type="text"
          value={input}
          onChange={(event) => onChangeInput(event.target.value)}
          placeholder={
            documentsCount === 0
              ? 'Upload a document first…'
              : voiceSupported
                ? 'Ask a question or use the microphone…'
                : 'Ask a question about your documents…'
          }
          disabled={loading || documentsCount === 0}
          maxLength={1000}
          className="input flex-1"
          data-testid="query-input"
          aria-label="Question input"
        />
        <button
          type="submit"
          disabled={!input.trim() || loading || documentsCount === 0}
          className="btn-primary px-3 shrink-0"
          aria-label="Send question"
        >
          <PaperAirplaneIcon className="h-5 w-5" />
        </button>
      </form>
    </>
  )
}

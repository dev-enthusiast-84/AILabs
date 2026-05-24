import {
  ArrowDownTrayIcon,
  BoltIcon,
  CpuChipIcon,
  SpeakerWaveIcon,
} from '@heroicons/react/24/outline'
import { CHAT_LANGUAGES, type ChatLanguageCode } from '@/lib/chatLanguages'

interface ChatToolbarProps {
  chatLanguage: ChatLanguageCode
  exportingAudio: boolean
  exportJobStatus?: string | null
  hasVoiceMessages: boolean
  messageCount: number
  ragMode: 'simple' | 'agentic'
  onCancelExport?: () => void
  onChangeLanguage: (language: ChatLanguageCode) => void
  onChangeMode: (mode: 'simple' | 'agentic') => void
  onExportAudio: () => void
  onExportTranscript: () => void
}

export function ChatToolbar({
  chatLanguage,
  exportingAudio,
  exportJobStatus,
  hasVoiceMessages,
  messageCount,
  ragMode,
  onCancelExport,
  onChangeLanguage,
  onChangeMode,
  onExportAudio,
  onExportTranscript,
}: ChatToolbarProps) {
  return (
    <div className="shrink-0 flex flex-col gap-3 mb-4 sm:flex-row sm:items-center sm:justify-between">
      <h2 className="text-base font-semibold text-slate-900">
        Ask a Question
      </h2>
      <div className="flex flex-wrap items-center gap-2 sm:justify-end">
        <label className="sr-only" htmlFor="chat-language">
          Chat language
        </label>
        <select
          id="chat-language"
          value={chatLanguage}
          onChange={(event) => onChangeLanguage(event.target.value as ChatLanguageCode)}
          className="h-9 rounded-lg border border-slate-300 bg-white px-2 text-sm font-medium text-slate-700 shadow-sm shadow-slate-200/60 focus:outline-none focus:ring-2 focus:ring-sky-500/35"
          aria-label="Chat language"
          data-testid="chat-language-select"
        >
          {CHAT_LANGUAGES.map((language) => (
            <option key={language.code} value={language.code}>
              {language.label}
            </option>
          ))}
        </select>

        {/* RAG mode toggle — icon-only with aria-label for accessibility and tooltip via title */}
        <div
          className="flex gap-0 rounded-lg overflow-hidden border border-slate-300 text-xs bg-white shadow-sm shadow-slate-200/60"
          role="group"
          aria-label="RAG mode selector"
        >
          <button
            type="button"
            onClick={() => onChangeMode('simple')}
            aria-pressed={ragMode === 'simple'}
            aria-label="Simple mode"
            title="Simple mode — direct vector search"
            className={`w-9 h-9 flex items-center justify-center transition-colors ${
              ragMode === 'simple'
                ? 'bg-sky-500 text-white'
                : 'text-slate-500 hover:text-slate-800 bg-white hover:bg-slate-50'
            }`}
          >
            <BoltIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => onChangeMode('agentic')}
            aria-pressed={ragMode === 'agentic'}
            aria-label="Agentic mode"
            title="Agentic mode — multi-step LangGraph pipeline"
            className={`w-9 h-9 flex items-center justify-center transition-colors ${
              ragMode === 'agentic'
                ? 'bg-sky-500 text-white'
                : 'text-slate-500 hover:text-slate-800 bg-white hover:bg-slate-50'
            }`}
          >
            <CpuChipIcon className="h-4 w-4" />
          </button>
        </div>

        {/* Export transcript — icon-only */}
        <button
          type="button"
          onClick={onExportTranscript}
          disabled={messageCount === 0}
          className="btn-tool w-9 px-0"
          data-testid="export-btn"
          aria-label="Export transcript"
          title={messageCount === 0 ? 'Ask a question before exporting' : 'Export chat transcript'}
        >
          <ArrowDownTrayIcon className="h-4 w-4" />
        </button>

        {/* Export audio — always visible; enabled when conversation has voice messages */}
        <button
          type="button"
          onClick={onExportAudio}
          disabled={messageCount === 0 || !hasVoiceMessages || exportingAudio}
          className="btn-tool w-9 px-0"
          data-testid="export-audio-btn"
          aria-label="Export audio"
          title={
            !hasVoiceMessages
              ? 'Available once the conversation includes voice messages'
              : exportingAudio
              ? 'Exporting audio…'
              : 'Export voice chat audio'
          }
        >
          <SpeakerWaveIcon className="h-4 w-4" />
        </button>

        {exportingAudio && exportJobStatus && (
          <span className="text-xs text-slate-500" data-testid="export-job-status">
            {exportJobStatus === 'queued' ? 'Queued…' : exportJobStatus === 'running' ? 'Processing…' : 'Exporting…'}
          </span>
        )}
        {exportingAudio && onCancelExport && (
          <button
            type="button"
            onClick={onCancelExport}
            className="text-xs text-rose-600 underline"
            data-testid="cancel-export-btn"
          >
            Cancel
          </button>
        )}
      </div>
    </div>
  )
}

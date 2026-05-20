import {
  ArrowDownTrayIcon,
  CpuChipIcon,
  SpeakerWaveIcon,
} from '@heroicons/react/24/outline'
import { CHAT_LANGUAGES, type ChatLanguageCode } from '@/lib/chatLanguages'

interface ChatToolbarProps {
  chatLanguage: ChatLanguageCode
  exportingAudio: boolean
  messageCount: number
  ragMode: 'simple' | 'agentic'
  voiceOnlyConversation: boolean
  onChangeLanguage: (language: ChatLanguageCode) => void
  onChangeMode: (mode: 'simple' | 'agentic') => void
  onExportAudio: () => void
  onExportTranscript: () => void
}

export function ChatToolbar({
  chatLanguage,
  exportingAudio,
  messageCount,
  ragMode,
  voiceOnlyConversation,
  onChangeLanguage,
  onChangeMode,
  onExportAudio,
  onExportTranscript,
}: ChatToolbarProps) {
  return (
    <div className="shrink-0 flex flex-col gap-3 mb-4 sm:flex-row sm:items-center sm:justify-between">
      <h2 className="text-base font-semibold text-slate-900 flex items-center gap-2">
        <CpuChipIcon className="h-5 w-5 text-sky-600" />
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
        <div
          className="flex gap-0 rounded-lg overflow-hidden border border-slate-300 text-xs bg-white shadow-sm shadow-slate-200/60"
          role="group"
          aria-label="RAG mode selector"
        >
          <button
            type="button"
            onClick={() => onChangeMode('simple')}
            aria-pressed={ragMode === 'simple'}
            className={`px-3 py-2 transition-colors ${
              ragMode === 'simple'
                ? 'bg-sky-500 text-white'
                : 'text-slate-500 hover:text-slate-800 bg-white hover:bg-slate-50'
            }`}
          >
            ⚡ Simple
          </button>
          <button
            type="button"
            onClick={() => onChangeMode('agentic')}
            aria-pressed={ragMode === 'agentic'}
            className={`px-3 py-2 transition-colors ${
              ragMode === 'agentic'
                ? 'bg-sky-500 text-white'
                : 'text-slate-500 hover:text-slate-800 bg-white hover:bg-slate-50'
            }`}
          >
            🤖 Agentic
          </button>
        </div>
        <button
          type="button"
          onClick={onExportTranscript}
          disabled={messageCount === 0}
          className="btn-tool"
          data-testid="export-btn"
          title={messageCount === 0 ? 'Ask a question before exporting the chat' : 'Export chat transcript'}
        >
          <ArrowDownTrayIcon className="h-4 w-4" />
          Export transcript
        </button>
        {voiceOnlyConversation && (
          <button
            type="button"
            onClick={onExportAudio}
            disabled={messageCount === 0 || exportingAudio}
            className="btn-tool"
            data-testid="export-audio-btn"
            title="Export redacted voice chat audio"
          >
            <SpeakerWaveIcon className="h-4 w-4" />
            {exportingAudio ? 'Exporting…' : 'Export audio'}
          </button>
        )}
      </div>
    </div>
  )
}

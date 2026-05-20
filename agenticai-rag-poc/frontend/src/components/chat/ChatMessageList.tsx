import type { RefObject } from 'react'
import {
  CheckBadgeIcon,
  ChevronRightIcon,
  ClipboardDocumentIcon,
  CpuChipIcon,
  ExclamationTriangleIcon,
  SpeakerWaveIcon,
  SpeakerXMarkIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import type { ChatMessage } from '@/types'

interface ChatMessageListProps {
  bottomRef: RefObject<HTMLDivElement>
  copiedId: string | null
  documentsCount: number
  expandedTraces: Set<string>
  loading: boolean
  messages: ChatMessage[]
  playingMessageId: string | null
  suggestions: string[]
  suggestionsLoading: boolean
  onCopyResponse: (message: ChatMessage) => void
  onOpenSource: (source: string) => void
  onSuggestionClick: (question: string) => void
  onTogglePlayback: (message: ChatMessage) => void
  onToggleTrace: (messageId: string) => void
}

function TraceRow({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="grid grid-cols-[70px_1fr] gap-2">
      <span className="text-slate-400 shrink-0">{label}</span>
      <div>
        <span className="text-slate-700 break-words">{value}</span>
        {sub && <div className="text-slate-400 mt-0.5">{sub}</div>}
      </div>
    </div>
  )
}

function EmptyChatState({
  documentsCount,
  suggestions,
  suggestionsLoading,
  onSuggestionClick,
}: Pick<ChatMessageListProps, 'documentsCount' | 'suggestions' | 'suggestionsLoading' | 'onSuggestionClick'>) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-4 py-12">
      {documentsCount === 0 ? (
        <>
          <div className="w-14 h-14 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center mb-4">
            <SparklesIcon className="h-7 w-7 text-slate-400" />
          </div>
          <p className="text-sm font-medium text-slate-500">No documents indexed yet</p>
          <p className="text-xs text-slate-400 mt-1">Upload a document on the left to start asking questions.</p>
        </>
      ) : (
        <>
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-sky-100 to-indigo-100 border border-sky-200 flex items-center justify-center mb-4">
            <CpuChipIcon className="h-7 w-7 text-sky-600" />
          </div>
          <p className="text-sm text-slate-500 mb-4">Ask a question about your documents:</p>
          {suggestionsLoading ? (
            <p className="text-xs text-slate-400">Reading uploaded content…</p>
          ) : suggestions.length > 0 ? (
            <div className="flex flex-wrap gap-2 justify-center max-w-md">
              {suggestions.map((question) => (
                <button
                  key={question}
                  onClick={() => onSuggestionClick(question)}
                  className="text-xs px-3 py-1.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200 hover:bg-sky-100 hover:border-sky-300 transition-colors"
                >
                  {question}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-400 max-w-sm">
              Start by asking about a topic, term, row, section, or decision that appears in the uploaded document.
            </p>
          )}
        </>
      )}
    </div>
  )
}

function AssistantMessageFooter({
  copiedId,
  expandedTraces,
  message,
  playingMessageId,
  onCopyResponse,
  onTogglePlayback,
  onToggleTrace,
}: {
  copiedId: string | null
  expandedTraces: Set<string>
  message: ChatMessage
  playingMessageId: string | null
  onCopyResponse: (message: ChatMessage) => void
  onTogglePlayback: (message: ChatMessage) => void
  onToggleTrace: (messageId: string) => void
}) {
  return (
    <div className={`${message.sources && message.sources.length > 0 ? '' : 'mt-2.5 pt-2.5 border-t border-slate-200'}`}>
      <div className="flex items-center gap-3 flex-wrap">
        {message.validation && (message.mode === 'agentic' || !message.mode) && (
          message.validation === 'VALID' ? (
            <span className="badge-valid">
              <CheckBadgeIcon className="h-3 w-3" />
              Verified
            </span>
          ) : (
            <span className="badge-revision">
              <ExclamationTriangleIcon className="h-3 w-3" />
              Unverified
            </span>
          )
        )}
        {message.tokens_used !== undefined && (
          <span className="text-xs text-slate-400">
            {message.tokens_used.toLocaleString()} tokens
          </span>
        )}
        {message.mode === 'simple' ? (
          <span className="text-xs text-sky-600">⚡ Simple RAG</span>
        ) : (
          <span className="text-xs text-indigo-600">🤖 Agentic RAG</span>
        )}
        {message.latency_ms !== undefined && message.latency_ms > 0 && (
          <span className="text-xs text-slate-400">{(message.latency_ms / 1000).toFixed(1)}s</span>
        )}
        {message.retry_count !== undefined && message.retry_count > 1 && (
          <span className="text-xs text-amber-600">revised {message.retry_count - 1}×</span>
        )}
        <button
          onClick={() => onCopyResponse(message)}
          className="text-xs text-slate-400 hover:text-slate-700 transition-colors flex items-center gap-0.5"
          title="Copy response"
          data-testid={`copy-btn-${message.id}`}
          aria-label="Copy response"
        >
          <ClipboardDocumentIcon className="h-3.5 w-3.5" />
          {copiedId === message.id ? 'Copied!' : ''}
        </button>
        <button
          onClick={() => onTogglePlayback(message)}
          className="text-xs text-slate-400 hover:text-slate-700 transition-colors flex items-center gap-0.5"
          title={playingMessageId === message.id ? 'Stop audio' : 'Listen to response'}
          aria-label={playingMessageId === message.id ? 'Stop audio' : 'Listen to response'}
          data-testid={`listen-btn-${message.id}`}
        >
          {playingMessageId === message.id ? (
            <SpeakerXMarkIcon className="h-3.5 w-3.5" />
          ) : (
            <SpeakerWaveIcon className="h-3.5 w-3.5" />
          )}
          {playingMessageId === message.id ? 'Stop' : 'Listen'}
        </button>
        {message.output_flagged && (
          <span className="text-xs text-amber-600 flex items-center gap-1" title="Content reviewed by policy" data-testid="output-flagged-badge">
            ⚠ Reviewed by content policy
          </span>
        )}
      </div>

      {message.mode === 'agentic' && message.trace && (
        <div className="mt-2">
          <button
            onClick={() => onToggleTrace(message.id)}
            className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-700 transition-colors"
            data-testid={`trace-toggle-${message.id}`}
          >
            <ChevronRightIcon className={`h-3 w-3 transition-transform ${expandedTraces.has(message.id) ? 'rotate-90' : ''}`} />
            Agent trace
          </button>

          {expandedTraces.has(message.id) && (
            <div className="mt-2 rounded-lg bg-slate-50 border border-slate-200 p-3 text-xs font-mono space-y-1.5" data-testid={`trace-panel-${message.id}`}>
              <TraceRow label="Planner" value={message.trace.refined_query} sub={`${message.trace.planner_model} · ${message.trace.planner_tokens} tok · ${message.trace.planner_latency_ms}ms`} />
              {message.trace.hypothetical_answer && (
                <TraceRow label="HyDE" value={message.trace.hypothetical_answer} />
              )}
              {message.trace.query_variants && message.trace.query_variants.length > 0 && (
                <TraceRow
                  label="Variants"
                  value={message.trace.query_variants.join(' · ')}
                />
              )}
              <TraceRow label="Retriever" value={`${message.trace.chunks_found} chunk${message.trace.chunks_found !== 1 ? 's' : ''} from: ${message.sources?.join(', ') || '—'}`} />
              <TraceRow
                label="Generator"
                value={message.trace.retries > 0 ? `answered · ${message.trace.retries} revision${message.trace.retries > 1 ? 's' : ''}` : 'answered'}
                sub={`${message.trace.generator_model} · ${message.trace.generator_tokens} tok · ${message.trace.generator_latency_ms}ms`}
              />
              <TraceRow
                label="Validator"
                value={message.trace.validation_reason}
                sub={`${message.trace.validator_model} · ${message.trace.validator_tokens} tok · ${message.trace.validator_latency_ms}ms`}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function MessageBubble({
  copiedId,
  expandedTraces,
  message,
  playingMessageId,
  onCopyResponse,
  onOpenSource,
  onTogglePlayback,
  onToggleTrace,
}: Omit<ChatMessageListProps, 'bottomRef' | 'documentsCount' | 'loading' | 'messages' | 'suggestions' | 'suggestionsLoading' | 'onSuggestionClick'> & {
  message: ChatMessage
}) {
  const isError = message.role === 'assistant' && message.error

  return (
    <div className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] sm:max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
          message.role === 'user'
            ? 'bg-gradient-to-br from-sky-500 to-indigo-600 text-white rounded-br-sm shadow-md shadow-sky-500/20'
            : isError
              ? 'bg-rose-50 border border-rose-200 text-rose-800 rounded-bl-sm shadow-sm'
              : 'bg-white border border-slate-200 text-slate-800 rounded-bl-sm shadow-sm'
        }`}
      >
        <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>

        {message.role === 'assistant' && !isError && message.sources && message.sources.length > 0 && (
          <div className="mt-2.5 pt-2.5 border-t border-slate-200">
            <p className="text-xs text-slate-400 font-medium mb-1.5">Sources:</p>
            <div className="flex flex-wrap gap-1 mb-2">
              {message.sources.map((source) => (
                <button
                  key={source}
                  onClick={() => onOpenSource(source)}
                  className="text-xs bg-sky-50 px-2 py-0.5 rounded-md border border-sky-200 text-sky-700 hover:bg-sky-100 hover:border-sky-300 transition-colors"
                  title="Click to view document content"
                >
                  {source}
                </button>
              ))}
            </div>
          </div>
        )}

        {message.role === 'assistant' && !isError && (
          <AssistantMessageFooter
            copiedId={copiedId}
            expandedTraces={expandedTraces}
            message={message}
            playingMessageId={playingMessageId}
            onCopyResponse={onCopyResponse}
            onTogglePlayback={onTogglePlayback}
            onToggleTrace={onToggleTrace}
          />
        )}
      </div>
    </div>
  )
}

export function ChatMessageList({
  bottomRef,
  copiedId,
  documentsCount,
  expandedTraces,
  loading,
  messages,
  playingMessageId,
  suggestions,
  suggestionsLoading,
  onCopyResponse,
  onOpenSource,
  onSuggestionClick,
  onTogglePlayback,
  onToggleTrace,
}: ChatMessageListProps) {
  return (
    <div className="flex-1 overflow-y-auto space-y-4 mb-4 pr-1">
      {messages.length === 0 && (
        <EmptyChatState
          documentsCount={documentsCount}
          suggestions={suggestions}
          suggestionsLoading={suggestionsLoading}
          onSuggestionClick={onSuggestionClick}
        />
      )}

      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          copiedId={copiedId}
          expandedTraces={expandedTraces}
          message={message}
          playingMessageId={playingMessageId}
          onCopyResponse={onCopyResponse}
          onOpenSource={onOpenSource}
          onTogglePlayback={onTogglePlayback}
          onToggleTrace={onToggleTrace}
        />
      ))}

      {loading && (
        <div className="flex justify-start">
          <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
            <div className="flex gap-1.5 items-center h-4">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 bg-sky-500 rounded-full animate-bounce"
                  style={{ animationDelay: `${i * 150}ms` }}
                />
              ))}
            </div>
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  )
}
